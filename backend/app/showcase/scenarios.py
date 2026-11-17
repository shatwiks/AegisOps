"""Five-scenario one-click Chaos Lab catalog, conflict exclusion & durable outbox runner (`Features A, I`)."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.k8s.executor import KubernetesExecutor
from app.models.entities import (
    Asset,
    AuditRecord,
    DemoRun,
    Incident,
    OutboxJob,
)
from app.showcase.probes import execute_business_probe

logger = logging.getLogger("aegisops.showcase.scenarios")

SCENARIO_CATALOG: dict[str, dict[str, Any]] = {
    "traffic_spike": {
        "scenario_id": "traffic_spike",
        "order": 1,
        "title": "Simulate Traffic Spike",
        "plain_english_explanation": "More requests overwhelm the provider-directory service",
        "expected_behavior": "Generates real concurrent search load, fires Prometheus latency alert, autonomously scales replicas 1 -> 3, and confirms 60s recovery.",
        "required_role": "operator",
        "target_namespace": "aegisops-healthcare",
        "target_service": "provider-directory",
        "target_deployment": "provider-directory",
        "preconditions": {"replicas": 1, "cpu_pressure_active": False},
        "fault_mechanism": "POST http://127.0.0.1:58083/internal/fault cpu_pressure_active=true + 6 concurrent search callers",
        "expected_signals": ["ProviderDirectoryHighLatencyCpu", "ERR_CPU_SATURATION_P95_SLOW", "http_recent_p95_latency_seconds > 0.50"],
        "policy": "ALLOW_AUTO_EXECUTE (LOW risk)",
        "playbook_id": "replica_scale_out_bounded",
        "risk_tier": "LOW",
        "recovery_assertions": ["3 ready / 3 desired replicas", "http_recent_p95_latency_seconds <= 0.50", "60s sustained probe window"],
        "timeout_seconds": 360,
        "cleanup_rule": "Stop synthetic load only after terminal outcome; restore replicas=1 via Restore Demo Baseline.",
        "repeatability": "Single active run per target asset enforced via resource lock.",
    },
    "db_pool_freeze": {
        "scenario_id": "db_pool_freeze",
        "order": 2,
        "title": "Simulate Database Pool Freeze",
        "plain_english_explanation": "eligibility-api runs out of usable database connections",
        "expected_behavior": "Injects reversible DB pool exhaustion (HTTP 503), triggers EligibilityDbPoolExhausted, autonomously restarts stateless deployment, and verifies healthy transactions.",
        "required_role": "operator",
        "target_namespace": "aegisops-healthcare",
        "target_service": "eligibility-api",
        "target_deployment": "eligibility-api",
        "preconditions": {"replicas": 1, "image": "aegisops/eligibility-api:v1.0.0-good"},
        "fault_mechanism": "POST http://127.0.0.1:58081/internal/fault db_pool_exhausted=true",
        "expected_signals": ["EligibilityDbPoolExhausted", "ERR_PG_POOL_TIMEOUT_57P03", "db_pool_active_connections=20/20"],
        "policy": "ALLOW_AUTO_EXECUTE (LOW risk)",
        "playbook_id": "stateless_deployment_restart",
        "risk_tier": "LOW",
        "recovery_assertions": ["Rolling restart completed", "/api/eligibility/check HTTP 200 semantic ok", "60s sustained recovery"],
        "timeout_seconds": 360,
        "cleanup_rule": "Pool fault clears naturally from pod restart; load stops only after terminal state.",
        "repeatability": "Resource-locked against concurrent eligibility-api / claims-processor runs.",
    },
    "bad_canary_update": {
        "scenario_id": "bad_canary_update",
        "order": 3,
        "title": "Simulate Bad Software Update",
        "plain_english_explanation": "A broken release breaks patient eligibility checks",
        "expected_behavior": "Rolls out allowlisted faulty demo image v1.9.0-broken (HTTP 500), fires High5xxErrorRate, waits for authorized approver TOTP MFA, rolls back to recorded known_good_image, and verifies recovery.",
        "required_role": "operator",
        "approval_role_required": "approver",
        "target_namespace": "aegisops-healthcare",
        "target_service": "eligibility-api",
        "target_deployment": "eligibility-api",
        "preconditions": {"replicas": 1, "image": "aegisops/eligibility-api:v1.0.0-good"},
        "fault_mechanism": "K8s SDK patch deployment image -> aegisops/eligibility-api:v1.9.0-broken",
        "expected_signals": ["High5xxErrorRate", "ERR_CANARY_IMG_SHA_BAD_9921", "HTTP 500 > 10%"],
        "policy": "REQUIRE_APPROVAL (HIGH risk — TOTP step-up bound to UID + ResourceVersion)",
        "playbook_id": "deployment_image_rollback",
        "risk_tier": "HIGH",
        "recovery_assertions": ["Image matches Asset.known_good_image (v1.0.0-good)", "0% 5xx", "60s sustained recovery"],
        "timeout_seconds": 420,
        "cleanup_rule": "No automatic rollback happens without human MFA approval; manual baseline reset always available.",
        "repeatability": "Resource-locked against concurrent eligibility-api / claims-processor runs.",
    },
    "oom_memory_crash": {
        "scenario_id": "oom_memory_crash",
        "order": 4,
        "title": "Simulate Out-of-Memory Crash",
        "plain_english_explanation": "claims-processor exceeds its 192Mi memory limit",
        "expected_behavior": "Drives 210Mi working-set batch demand against 192Mi limit (HTTP 503), fires ClaimsProcessorMemoryPressure, waits for approver TOTP MFA before bounded 192Mi -> 384Mi patch, and verifies recovery.",
        "required_role": "operator",
        "approval_role_required": "approver",
        "target_namespace": "aegisops-healthcare",
        "target_service": "claims-processor",
        "target_deployment": "claims-processor",
        "preconditions": {"replicas": 1, "memory_limit": "192Mi"},
        "fault_mechanism": "POST http://127.0.0.1:58082/internal/fault working_set_mb=210",
        "expected_signals": ["ClaimsProcessorMemoryPressure", "ERR_OOM_EXIT_137_CLAIMS_BATCH", "memory_ratio >= 0.88"],
        "policy": "REQUIRE_APPROVAL (HIGH risk — TOTP step-up required; memory_mi capped <= 512Mi)",
        "playbook_id": "memory_limit_increase_bounded",
        "risk_tier": "HIGH",
        "recovery_assertions": ["Container memory limit patched to 384Mi", "memory_ratio < 0.80", "60s sustained recovery"],
        "timeout_seconds": 420,
        "cleanup_rule": "Restore working_set_mb=64 and 192Mi baseline via Restore Demo Baseline.",
        "repeatability": "Resource-locked against concurrent claims-processor / eligibility-api runs.",
    },
    "pii_leak_and_db_failure": {
        "scenario_id": "pii_leak_and_db_failure",
        "order": 5,
        "title": "Simulate Sensitive Data in Logs + DB Failure",
        "plain_english_explanation": "Fictional identifiers appear while the demo database lags",
        "expected_behavior": "Marks demo postgres-claims-db in aegisops-healthcare degraded, fails DB probe, scrubs fictional SSN/Member/Email/Token identifiers before DB/LLM/Langfuse, matches RB-011, and escalates safely to a human DBA without mutating DB.",
        "required_role": "operator",
        "target_namespace": "aegisops-healthcare",
        "target_service": "postgres-claims-db",
        "target_deployment": "postgres-claims-db",
        "preconditions": {"replicas": 1, "stateless_eligible": False},
        "fault_mechanism": "K8s annotation aegisops.io/simulated-fault=ERR_PG_REPLICATION_LAG on demo postgres-claims-db + signed fictional-PII webhook (control-plane DB untouched)",
        "expected_signals": ["PostgresReplicationLagHigh", "ERR_PG_REPLICATION_LAG", "Redacted SSN/MEMBER_ID/EMAIL/TOKEN"],
        "policy": "REFUSE_AND_ESCALATE (RB-011 architectural boundary — stateful DB failover prohibited)",
        "playbook_id": None,
        "risk_tier": "ESCALATE_ONLY",
        "recovery_assertions": ["All fictional PHI/PII scrubbed", "State == ESCALATED", "Zero K8s DB mutation attempted"],
        "timeout_seconds": 180,
        "cleanup_rule": "Clears reversible demo DB fault annotation via Restore Demo Baseline.",
        "repeatability": "Resource-locked on postgres-claims-db.",
    },
}


def serialize_demo_run(run: DemoRun) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "scenario_id": run.scenario_id,
        "title": run.title,
        "target_service": run.target_service,
        "idempotency_key": run.idempotency_key,
        "actor_email": run.actor_email,
        "status": run.status,
        "incident_id": str(run.incident_id) if run.incident_id else None,
        "baseline_snapshot": run.baseline_snapshot_json,
        "narration_state": run.narration_state_json,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "updated_at": run.updated_at.isoformat(),
    }


def build_narration_from_incident(
    run: DemoRun,
    inc: Incident | None,
) -> dict[str, Any]:
    """Derive Guided Tour step and plain-English narration strictly from persisted incident/run state."""
    if inc is None:
        if run.status in ("QUEUED", "INJECTING_FAULT"):
            return {
                "stage_index": 0,
                "headline": "Injecting controlled workload fault",
                "subtext": f"Applying scenario '{run.title}' on {run.target_service} inside aegisops-healthcare...",
                "focus_panel": "chaos-lab",
            }
        return {
            "stage_index": 0,
            "headline": "Waiting for telemetry and Prometheus alert",
            "subtext": f"Requests against {run.target_service} are failing; Prometheus/Alertmanager evaluating alert rule...",
            "focus_panel": "probes",
        }

    state = inc.state
    redactions = int((inc.redaction_stats_json or {}).get("total_redactions", 0))
    verif = inc.verification_state_json or {}

    if state == "OPEN":
        return {
            "stage_index": 1,
            "headline": "Requests are failing -> Alert caught & sensitive data scrubbed.",
            "subtext": (
                f"{inc.alertname} ingested ({inc.severity}); scrubbed {redactions} sensitive token(s)."
            ),
            "focus_panel": "lifecycle",
        }
    if state == "TRIAGING":
        return {
            "stage_index": 3,
            "headline": "These services may be affected -> Consulting runbooks & AI.",
            "subtext": f"Mapping CMDB blast radius and searching Hybrid RAG for '{run.target_service}'.",
            "focus_panel": "topology",
        }
    if state == "AWAITING_APPROVAL":
        return {
            "stage_index": 4,
            "headline": f"Policy paused for human MFA approval ({inc.proposed_playbook_id}).",
            "subtext": "This sensitive change requires an authenticated approver to enter a 6-digit TOTP code.",
            "focus_panel": "approval",
        }
    if state == "READY_TO_REMEDIATE" or state == "REMEDIATING":
        return {
            "stage_index": 4,
            "headline": f"Policy permits '{inc.proposed_playbook_id}' -> Executing on Kubernetes.",
            "subtext": f"Acquiring Redis lock and patching {run.target_service} in aegisops-healthcare.",
            "focus_panel": "decision",
        }
    if state == "VERIFYING":
        elapsed = int(round(float(verif.get("elapsed_healthy_seconds", 0))))
        win = int(round(float(verif.get("window_seconds", 60))))
        return {
            "stage_index": 5,
            "headline": f"Recovery is being observed ({elapsed} of {win}s checked).",
            "subtext": "Watchdog continuously checks Kubernetes rollout, /readyz, traffic probes, and Prometheus metrics.",
            "focus_panel": "lifecycle",
        }
    if state == "RESOLVED":
        return {
            "stage_index": 6,
            "headline": "The application request succeeds again — Verified recovery.",
            "subtext": f"Sustained stability verified for {run.target_service}; before/after state recorded.",
            "focus_panel": "postmortem",
        }
    if state == "ESCALATED":
        return {
            "stage_index": 6,
            "headline": "Escalated safely to a human engineer (no unsafe mutation executed).",
            "subtext": inc.refusal_reason or "Policy blocked autonomous mutation.",
            "focus_panel": "decision",
        }
    return {
        "stage_index": 6,
        "headline": f"Scenario ended with state {state}.",
        "subtext": inc.refusal_reason or run.error_message or "Inspect timeline and logs.",
        "focus_panel": "lifecycle",
    }


def _conflicting_services(target_service: str) -> set[str]:
    if target_service == "eligibility-api":
        return {"eligibility-api", "claims-processor", "postgres-claims-db"}
    if target_service == "claims-processor":
        return {"claims-processor", "eligibility-api"}
    if target_service == "postgres-claims-db":
        return {"postgres-claims-db", "eligibility-api", "claims-processor"}
    return {target_service}


async def launch_demo_scenario(
    session: AsyncSession,
    *,
    scenario_id: str,
    idempotency_key: str,
    actor_sub: str,
    actor_email: str,
    actor_role: str,
    settings: Settings,
    executor: KubernetesExecutor,
) -> tuple[DemoRun, bool]:
    """Validate idempotency & conflicts, capture baseline, persist DemoRun + OutboxJob."""
    if scenario_id not in SCENARIO_CATALOG:
        raise HTTPException(status_code=404, detail=f"Unknown scenario '{scenario_id}'")
    if str(settings.aegisops_env) == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chaos Lab scenario launch is disabled in production environments.",
        )

    spec = SCENARIO_CATALOG[scenario_id]
    target_service = str(spec["target_service"])

    # 1. Launch idempotency check
    existing = (
        await session.execute(
            select(DemoRun).where(DemoRun.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, True

    # 2. Resource-scoped conflict exclusion
    conflicts_on = _conflicting_services(target_service)
    blocking_run = (
        await session.execute(
            select(DemoRun)
            .where(
                DemoRun.target_service.in_(conflicts_on),
                DemoRun.status.notin_(["COMPLETED", "ESCALATED", "FAILED", "CANCELLED"]),
            )
            .order_by(DemoRun.started_at.desc())
        )
    ).scalars().first()
    if blocking_run is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "scenario_conflict",
                "message": (
                    f"Cannot launch '{scenario_id}': active demo run '{blocking_run.scenario_id}' "
                    f"({blocking_run.id}) holds '{blocking_run.target_service}'."
                ),
                "blocking_run_id": str(blocking_run.id),
                "blocking_incident_id": str(blocking_run.incident_id)
                if blocking_run.incident_id
                else None,
            },
        )

    blocking_inc = (
        await session.execute(
            select(Incident, Asset.slug)
            .outerjoin(Asset, Incident.primary_asset_id == Asset.id)
            .where(
                Asset.slug.in_(conflicts_on),
                Incident.state.notin_(["RESOLVED", "FAILED"]),
                Incident.source_provenance != "automated_test",
            )
        )
    ).first()
    if blocking_inc is not None:
        b_inc, b_slug = blocking_inc
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "active_incident_conflict",
                "message": (
                    f"Cannot launch '{scenario_id}': active incident {b_inc.id} ({b_inc.state}) "
                    f"exists on '{b_slug}'."
                ),
                "blocking_incident_id": str(b_inc.id),
                "blocking_run_id": str(b_inc.demo_run_id) if b_inc.demo_run_id else None,
            },
        )

    # 3. Capture baseline K8s snapshot
    baseline_snap: dict[str, Any] = {}
    try:
        snap = await executor.read_deployment_snapshot(
            cluster=settings.aegisops_k8s_context,
            namespace=str(spec["target_namespace"]),
            deployment_name=str(spec["target_deployment"]),
        )
        baseline_snap = snap.to_sanitized_dict()
    except Exception as exc:
        baseline_snap = {"error": type(exc).__name__}

    now = datetime.now(UTC)
    run_id = uuid.uuid4()
    run = DemoRun(
        id=run_id,
        scenario_id=scenario_id,
        title=str(spec["title"]),
        target_service=target_service,
        idempotency_key=idempotency_key,
        actor_sub=actor_sub,
        actor_email=actor_email,
        status="QUEUED",
        baseline_snapshot_json=baseline_snap,
        narration_state_json={
            "stage_index": 0,
            "headline": f"Queued '{spec['title']}'",
            "subtext": "Accepted into durable worker queue...",
            "focus_panel": "chaos-lab",
        },
        started_at=now,
        updated_at=now,
    )
    session.add(run)
    await session.flush()

    session.add(
        OutboxJob(
            incident_id=None,
            job_type="RUN_DEMO_SCENARIO",
            dedup_job_key=f"RUN_DEMO_SCENARIO:{run_id}",
            payload_sanitized_json={"demo_run_id": str(run_id), "scenario_id": scenario_id},
            status="PENDING",
            available_at=now,
            created_at=now,
        )
    )
    session.add(
        AuditRecord(
            actor_sub=actor_sub,
            actor_role=actor_role,
            action_type="CHAOS_SCENARIO_LAUNCHED",
            policy_decision="QUEUED",
            after_state_json={
                "demo_run_id": str(run_id),
                "scenario_id": scenario_id,
                "target_service": target_service,
            },
            details_json={"idempotency_key": idempotency_key},
            created_at=now,
        )
    )
    return run, False


async def _drive_url_loop(
    url: str,
    stop_event: asyncio.Event,
    *,
    method: str = "GET",
    concurrency: int = 4,
) -> None:
    async with httpx.AsyncClient(timeout=4.0) as client:

        async def _one() -> None:
            while not stop_event.is_set():
                try:
                    if method == "POST":
                        await client.post(url, headers={"Connection": "close"})
                    else:
                        await client.get(url, headers={"Connection": "close"})
                except Exception:
                    pass
                await asyncio.sleep(0.08)

        await asyncio.gather(*[_one() for _ in range(concurrency)])


async def execute_demo_scenario_job(
    job: OutboxJob,
    *,
    session_factory: Any,
    settings: Settings,
    executor: KubernetesExecutor,
) -> None:
    """Durable worker handler executing any of the 5 showcase scenarios end-to-end."""
    demo_run_id = uuid.UUID(str(job.payload_sanitized_json["demo_run_id"]))
    scenario_id = str(job.payload_sanitized_json["scenario_id"])
    spec = SCENARIO_CATALOG[scenario_id]
    target_service = str(spec["target_service"])
    timeout_sec = int(spec["timeout_seconds"])
    fault_headers = (
        {"X-Fault-Token": settings.demo_internal_fault_token}
        if settings.demo_internal_fault_token
        else {}
    )

    # Pre-fault baseline business probe
    async with session_factory() as session, session.begin():
        run = (await session.execute(select(DemoRun).where(DemoRun.id == demo_run_id))).scalar_one()
        if run.status in ("COMPLETED", "ESCALATED", "FAILED", "CANCELLED"):
            return
        run.status = "INJECTING_FAULT"
        run.narration_state_json = build_narration_from_incident(run, None)
        await execute_business_probe(
            session,
            target_service=target_service,
            settings=settings,
            executor=executor,
            probe_type="scenario",
            demo_run_id=demo_run_id,
        )

    stop_traffic = asyncio.Event()
    traffic_task: asyncio.Task[None] | None = None

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            if scenario_id == "traffic_spike":
                resp = await client.post(
                    "http://127.0.0.1:58083/internal/fault",
                    headers=fault_headers,
                    json={"cpu_pressure_active": True},
                )
                resp.raise_for_status()
                traffic_task = asyncio.create_task(
                    _drive_url_loop(
                        "http://127.0.0.1:58083/api/providers/search",
                        stop_traffic,
                        concurrency=6,
                    )
                )
            elif scenario_id == "db_pool_freeze":
                resp = await client.post(
                    "http://127.0.0.1:58081/internal/fault",
                    headers=fault_headers,
                    json={"db_pool_exhausted": True},
                )
                resp.raise_for_status()
                traffic_task = asyncio.create_task(
                    _drive_url_loop(
                        "http://127.0.0.1:58081/api/eligibility/check",
                        stop_traffic,
                        concurrency=4,
                    )
                )
            elif scenario_id == "bad_canary_update":
                await executor.patch_demo_workload(
                    cluster=settings.aegisops_k8s_context,
                    namespace=str(spec["target_namespace"]),
                    deployment_name="eligibility-api",
                    patch_body={
                        "spec": {
                            "template": {
                                "spec": {
                                    "containers": [
                                        {
                                            "name": "eligibility-api",
                                            "image": "aegisops/eligibility-api:v1.9.0-broken",
                                        }
                                    ]
                                }
                            }
                        }
                    },
                    wait_rollout=True,
                )
                traffic_task = asyncio.create_task(
                    _drive_url_loop(
                        "http://127.0.0.1:58081/api/eligibility/check",
                        stop_traffic,
                        concurrency=4,
                    )
                )
            elif scenario_id == "oom_memory_crash":
                resp = await client.post(
                    "http://127.0.0.1:58082/internal/fault",
                    headers=fault_headers,
                    json={"working_set_mb": 210},
                )
                resp.raise_for_status()
                traffic_task = asyncio.create_task(
                    _drive_url_loop(
                        "http://127.0.0.1:58082/healthz",
                        stop_traffic,
                        concurrency=2,
                    )
                )
            elif scenario_id == "pii_leak_and_db_failure":
                await executor.patch_demo_workload(
                    cluster=settings.aegisops_k8s_context,
                    namespace=str(spec["target_namespace"]),
                    deployment_name="postgres-claims-db",
                    patch_body={
                        "metadata": {
                            "annotations": {
                                "aegisops.io/simulated-fault": "ERR_PG_REPLICATION_LAG"
                            }
                        }
                    },
                    wait_rollout=False,
                )
                # Send explicitly fictional identifiers via signed Alertmanager webhook
                payload = {
                    "receiver": "aegisops-showcase-scenario-5",
                    "status": "firing",
                    "alerts": [
                        {
                            "status": "firing",
                            "fingerprint": f"sc5-{demo_run_id.hex[:12]}",
                            "startsAt": datetime.now(UTC).isoformat(),
                            "labels": {
                                "alertname": "PostgresReplicationLagHigh",
                                "severity": "critical",
                                "service": "postgres-claims-db",
                                "namespace": "aegisops-healthcare",
                                "cluster": settings.aegisops_k8s_context,
                            },
                            "annotations": {
                                "summary": (
                                    "ERR_PG_REPLICATION_LAG on demo postgres-claims-db; "
                                    "fictional sample patient=Jane Fictional ssn=123-45-6789 "
                                    "member=MBR-90001234 email=jane.fictional@example.invalid "
                                    "token=Bearer eyJFictionalDemoToken999"
                                )
                            },
                        }
                    ],
                }
                raw = json.dumps(payload).encode("utf-8")
                sig = hmac.new(
                    settings.aegisops_webhook_hmac_secret.encode("utf-8"),
                    raw,
                    hashlib.sha256,
                ).hexdigest()
                hook_url = f"http://{settings.aegisops_api_host}:{settings.aegisops_api_port}/api/v1/webhooks/alertmanager"
                hook_resp = await client.post(
                    hook_url,
                    content=raw,
                    headers={
                        "Content-Type": "application/json",
                        "X-AegisOps-Signature": f"sha256={sig}",
                        "X-AegisOps-Provenance": "interactive_demo",
                    },
                )
                hook_resp.raise_for_status()

        # Brief settle so failing probe observes the genuine fault condition
        await asyncio.sleep(2.5)
        async with session_factory() as session, session.begin():
            run = (
                await session.execute(select(DemoRun).where(DemoRun.id == demo_run_id))
            ).scalar_one()
            if run.status == "CANCELLED":
                return
            run.status = "WAITING_FOR_ALERT"
            run.narration_state_json = build_narration_from_incident(run, None)
            await execute_business_probe(
                session,
                target_service=target_service,
                settings=settings,
                executor=executor,
                probe_type="scenario",
                incident_id=run.incident_id,
                demo_run_id=demo_run_id,
            )

        # Track real incident lifecycle through terminal outcome while keeping fault load running
        deadline = time.monotonic() + timeout_sec
        fault_probe_captured = False
        while time.monotonic() < deadline:
            async with session_factory() as session, session.begin():
                run = (
                    await session.execute(select(DemoRun).where(DemoRun.id == demo_run_id))
                ).scalar_one()
                if run.status == "CANCELLED":
                    return
                inc = None
                if run.incident_id is not None:
                    inc = (
                        await session.execute(
                            select(Incident).where(Incident.id == run.incident_id)
                        )
                    ).scalar_one_or_none()
                else:
                    inc = (
                        await session.execute(
                            select(Incident)
                            .where(Incident.demo_run_id == demo_run_id)
                            .order_by(Incident.ingested_at.desc())
                        )
                    ).scalars().first()
                    if inc is not None:
                        run.incident_id = inc.id

                if inc is not None:
                    run.narration_state_json = build_narration_from_incident(run, inc)
                    if not fault_probe_captured:
                        await execute_business_probe(
                            session,
                            target_service=target_service,
                            settings=settings,
                            executor=executor,
                            probe_type="scenario",
                            incident_id=inc.id,
                            demo_run_id=demo_run_id,
                        )
                        fault_probe_captured = True

                    if inc.state == "AWAITING_APPROVAL":
                        run.status = "AWAITING_APPROVAL"
                    elif inc.state == "VERIFYING":
                        run.status = "VERIFYING"
                    elif inc.state == "RESOLVED":
                        await execute_business_probe(
                            session,
                            target_service=target_service,
                            settings=settings,
                            executor=executor,
                            probe_type="scenario",
                            incident_id=inc.id,
                            demo_run_id=demo_run_id,
                        )
                        run.status = "COMPLETED"
                        run.completed_at = datetime.now(UTC)
                        return
                    elif inc.state == "ESCALATED":
                        await execute_business_probe(
                            session,
                            target_service=target_service,
                            settings=settings,
                            executor=executor,
                            probe_type="scenario",
                            incident_id=inc.id,
                            demo_run_id=demo_run_id,
                        )
                        run.status = "ESCALATED"
                        run.completed_at = datetime.now(UTC)
                        return
                    elif inc.state == "FAILED":
                        run.status = "FAILED"
                        run.completed_at = datetime.now(UTC)
                        return
                    else:
                        run.status = "ACTIVE"
            await asyncio.sleep(3.0)

        async with session_factory() as session, session.begin():
            run = (
                await session.execute(select(DemoRun).where(DemoRun.id == demo_run_id))
            ).scalar_one()
            run.status = "FAILED"
            run.error_message = f"Timed out after {timeout_sec}s waiting for terminal outcome"
            run.completed_at = datetime.now(UTC)
    finally:
        stop_traffic.set()
        if traffic_task is not None:
            with contextlib.suppress(Exception):
                await traffic_task
