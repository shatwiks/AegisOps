"""Global & per-scenario readiness, scoped baseline preview/reset, and automation pause controls."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import check_postgres_ready
from app.domain.state_machine import IncidentState, transition_incident
from app.k8s.executor import KubernetesExecutor, KubernetesGuardError
from app.models.entities import AuditRecord, DemoRun, Incident, Runbook, SystemControlFlag
from app.redis_client import check_redis_ready
from app.worker.locks import RedisTargetLease

logger = logging.getLogger("aegisops.showcase.controls")

DEMO_BASELINE_SPECS: dict[str, dict[str, Any]] = {
    "claims-processor": {
        "namespace": "aegisops-healthcare",
        "replicas": 1,
        "image": "aegisops/claims-processor:v1.0.0-good",
        "memory_limit": "192Mi",
        "memory_request": "96Mi",
        "fault_url": "http://127.0.0.1:58082/internal/fault",
        "fault_reset_payload": {"working_set_mb": 64},
        "readyz_url": "http://127.0.0.1:58082/readyz",
    },
    "eligibility-api": {
        "namespace": "aegisops-healthcare",
        "replicas": 1,
        "image": "aegisops/eligibility-api:v1.0.0-good",
        "memory_limit": "256Mi",
        "memory_request": "64Mi",
        "fault_url": "http://127.0.0.1:58081/internal/fault",
        "fault_reset_payload": {"db_pool_exhausted": False},
        "readyz_url": "http://127.0.0.1:58081/readyz",
    },
    "provider-directory": {
        "namespace": "aegisops-healthcare",
        "replicas": 1,
        "image": "aegisops/provider-directory:v1.0.0-good",
        "memory_limit": "256Mi",
        "memory_request": "64Mi",
        "fault_url": "http://127.0.0.1:58083/internal/fault",
        "fault_reset_payload": {"cpu_pressure_active": False},
        "readyz_url": "http://127.0.0.1:58083/readyz",
    },
    "postgres-claims-db": {
        "namespace": "aegisops-healthcare",
        "replicas": 1,
        "image": "postgres:16-alpine",
        "memory_limit": "256Mi",
        "memory_request": "96Mi",
        "clear_annotation": "aegisops.io/simulated-fault",
    },
}

SCENARIO_META: tuple[dict[str, str], ...] = (
    {
        "scenario_id": "traffic_spike",
        "title": "Simulate Traffic Spike",
        "target_service": "provider-directory",
    },
    {
        "scenario_id": "db_pool_freeze",
        "title": "Simulate Database Pool Freeze",
        "target_service": "eligibility-api",
    },
    {
        "scenario_id": "bad_canary_update",
        "title": "Simulate Bad Software Update",
        "target_service": "eligibility-api",
    },
    {
        "scenario_id": "oom_memory_crash",
        "title": "Simulate Out-of-Memory Crash",
        "target_service": "claims-processor",
    },
    {
        "scenario_id": "pii_leak_and_db_failure",
        "title": "Simulate Sensitive Data in Logs + DB Failure",
        "target_service": "postgres-claims-db",
    },
)


async def get_automation_flag(session: AsyncSession) -> dict[str, Any]:
    flag = (
        await session.execute(
            select(SystemControlFlag).where(SystemControlFlag.key == "automation_paused")
        )
    ).scalar_one_or_none()
    if flag is None:
        return {
            "automation_paused": False,
            "reason": "",
            "updated_by_email": None,
            "updated_at": None,
        }
    return {
        "automation_paused": flag.bool_value,
        "reason": flag.reason,
        "updated_by_email": flag.updated_by_email,
        "updated_at": flag.updated_at.isoformat(),
    }


async def set_automation_flag(
    session: AsyncSession,
    *,
    paused: bool,
    reason: str,
    actor_sub: str,
    actor_email: str,
    actor_role: str,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    flag = (
        await session.execute(
            select(SystemControlFlag).where(SystemControlFlag.key == "automation_paused")
        )
    ).scalar_one_or_none()
    prev_val = flag.bool_value if flag else False
    if flag is None:
        flag = SystemControlFlag(
            key="automation_paused",
            bool_value=paused,
            reason=reason.strip(),
            updated_by_sub=actor_sub,
            updated_by_email=actor_email,
            updated_at=now,
        )
        session.add(flag)
    else:
        flag.bool_value = paused
        flag.reason = reason.strip()
        flag.updated_by_sub = actor_sub
        flag.updated_by_email = actor_email
        flag.updated_at = now

    session.add(
        AuditRecord(
            actor_sub=actor_sub,
            actor_role=actor_role,
            action_type="OPERATOR_AUTOMATION_TOGGLE",
            policy_decision="PAUSED" if paused else "RESUMED",
            before_state_json={"automation_paused": prev_val},
            after_state_json={"automation_paused": paused},
            details_json={"reason": reason.strip()},
            created_at=now,
        )
    )
    return {
        "automation_paused": paused,
        "reason": flag.reason,
        "updated_by_email": actor_email,
        "updated_at": now.isoformat(),
        "in_flight_note": (
            "Pausing automation holds queued EXECUTE_REMEDIATION jobs; in-flight Kubernetes patches and completed mutations are not rolled back."
        ),
    }


async def collect_system_readiness(
    *,
    engine: Any,
    session: AsyncSession,
    redis_client: Any,
    settings: Settings,
    executor: KubernetesExecutor,
) -> dict[str, Any]:
    """Evaluate honest global & per-scenario readiness across all runtime dependencies."""
    checked_at = datetime.now(UTC).isoformat()
    checks: dict[str, dict[str, Any]] = {}

    # 1. Postgres + pgvector
    try:
        pg = await check_postgres_ready(engine)
        checks["postgres"] = {
            "status": "Ready" if pg.get("pgvector_installed") else "Degraded",
            "detail": f"pgvector={pg.get('pgvector_version', 'missing')}",
        }
    except Exception as exc:
        checks["postgres"] = {"status": "Blocked", "detail": type(exc).__name__}

    # 2. Redis
    try:
        rd = await check_redis_ready(redis_client)
        checks["redis"] = {
            "status": "Ready" if rd.get("connected") else "Blocked",
            "detail": "Connected" if rd.get("connected") else "Unavailable",
        }
    except Exception as exc:
        checks["redis"] = {"status": "Blocked", "detail": type(exc).__name__}

    # 3. Worker heartbeat
    try:
        hb_keys = [k async for k in redis_client.scan_iter("aegisops:worker:heartbeat:*", count=20)]
        checks["worker"] = {
            "status": "Ready" if hb_keys else "Degraded",
            "detail": f"{len(hb_keys)} active worker heartbeat(s)"
            if hb_keys
            else "No standalone outbox worker heartbeat detected",
        }
    except Exception as exc:
        checks["worker"] = {"status": "Unknown", "detail": type(exc).__name__}

    # 4. Runbook index
    try:
        ready_docs = (
            await session.execute(
                select(func.count(Runbook.id)).where(Runbook.indexing_status == "READY")
            )
        ).scalar_one()
        checks["knowledge_base"] = {
            "status": "Ready" if ready_docs >= 1 else "Blocked",
            "detail": f"{ready_docs} READY indexed document(s)",
            "ready_count": int(ready_docs),
        }
    except Exception as exc:
        checks["knowledge_base"] = {"status": "Unknown", "detail": type(exc).__name__, "ready_count": 0}

    # 5. Control flags & active runs
    auto_flag = await get_automation_flag(session)
    active_runs = (
        (
            await session.execute(
                select(DemoRun).where(
                    DemoRun.status.notin_(["COMPLETED", "ESCALATED", "FAILED", "CANCELLED"])
                )
            )
        )
        .scalars()
        .all()
    )
    active_by_service = {r.target_service: str(r.id) for r in active_runs}

    # 6. External HTTP services (Ollama, Prometheus, Keycloak)
    async with httpx.AsyncClient(timeout=3.0) as client:
        try:
            oll = await client.get(f"{settings.aegisops_ollama_base_url.rstrip('/')}/api/tags")
            if oll.status_code == 200:
                names = {str(m.get("name", "")) for m in oll.json().get("models", [])}
                has_chat = settings.aegisops_chat_model in names
                has_embed = settings.aegisops_embedding_model in names
                if has_chat and has_embed:
                    checks["ollama"] = {
                        "status": "Ready",
                        "detail": f"{settings.aegisops_chat_model} & {settings.aegisops_embedding_model} loaded",
                    }
                else:
                    checks["ollama"] = {
                        "status": "Degraded",
                        "detail": f"Missing model(s): chat={has_chat}, embed={has_embed}",
                    }
            else:
                checks["ollama"] = {"status": "Degraded", "detail": f"HTTP {oll.status_code}"}
        except Exception as exc:
            checks["ollama"] = {"status": "Degraded", "detail": type(exc).__name__}

        try:
            prom = await client.get(
                f"{settings.aegisops_prometheus_url.rstrip('/')}/api/v1/query",
                params={"query": "up"},
            )
            if prom.status_code == 200 and prom.json().get("data", {}).get("result"):
                checks["prometheus"] = {"status": "Ready", "detail": "Scrape telemetry active"}
            else:
                checks["prometheus"] = {"status": "Degraded", "detail": f"HTTP {prom.status_code}"}
        except Exception as exc:
            checks["prometheus"] = {"status": "Unknown", "detail": type(exc).__name__}

        try:
            kc = await client.get(settings.aegisops_oidc_jwks_url)
            checks["keycloak"] = {
                "status": "Ready" if kc.status_code == 200 else "Degraded",
                "detail": "JWKS reachable" if kc.status_code == 200 else f"HTTP {kc.status_code}",
            }
        except Exception as exc:
            checks["keycloak"] = {"status": "Degraded", "detail": type(exc).__name__}

    # 7. Kubernetes workloads & baseline match check
    workloads: dict[str, dict[str, Any]] = {}
    k8s_ok = True
    for svc, spec in DEMO_BASELINE_SPECS.items():
        try:
            snap = await executor.read_deployment_snapshot(
                cluster=settings.aegisops_k8s_context,
                namespace=spec["namespace"],
                deployment_name=svc,
            )
            at_baseline = (
                snap.replicas == spec["replicas"]
                and snap.image == spec["image"]
                and snap.rollout_status == "Healthy"
                and (
                    svc != "claims-processor" or snap.memory_limit == spec["memory_limit"]
                )
                and (
                    "clear_annotation" not in spec
                    or spec["clear_annotation"] not in snap.annotations
                )
            )
            workloads[svc] = {
                "status": "Ready" if snap.rollout_status == "Healthy" else "Degraded",
                "at_baseline": at_baseline,
                "rollout_status": snap.rollout_status,
                "replicas": f"{snap.ready_replicas} ready / {snap.replicas} desired",
                "image": snap.image,
                "memory_limit": snap.memory_limit,
                "container_name": snap.container_name,
            }
        except Exception as exc:
            k8s_ok = False
            workloads[svc] = {
                "status": "Blocked",
                "at_baseline": False,
                "error": f"{type(exc).__name__}: {str(exc)[:140]}",
            }

    checks["kubernetes"] = {
        "status": "Ready" if k8s_ok else "Blocked",
        "context": settings.aegisops_k8s_context,
        "namespace": settings.aegisops_k8s_allowed_namespaces[0],
        "workloads": workloads,
    }

    # Scenario readiness synthesis
    scenarios_readiness: dict[str, dict[str, Any]] = {}
    core_blocked = checks["postgres"]["status"] == "Blocked" or checks["redis"]["status"] == "Blocked"
    for meta in SCENARIO_META:
        sid = meta["scenario_id"]
        svc = meta["target_service"]
        wl = workloads.get(svc, {})
        reasons: list[str] = []
        status_val = "Ready"

        if core_blocked:
            status_val = "Blocked"
            reasons.append("Control-plane PostgreSQL or Redis unavailable")
        if checks["knowledge_base"].get("ready_count", 0) == 0:
            status_val = "Blocked"
            reasons.append("No READY runbooks indexed")
        if wl.get("status") == "Blocked":
            status_val = "Blocked"
            reasons.append(f"Target deployment '{svc}' unreachable in {settings.aegisops_k8s_context}")
        elif not wl.get("at_baseline", False):
            if status_val == "Ready":
                status_val = "Degraded"
            reasons.append(f"'{svc}' differs from baseline; Restore Demo Baseline recommended")
        if svc in active_by_service:
            status_val = "Blocked"
            reasons.append(f"Active demo run {active_by_service[svc]} holds target '{svc}'")
        if auto_flag["automation_paused"] and status_val == "Ready":
            status_val = "Degraded"
            reasons.append("Operator pause enabled; remediation will hold until resumed")
        if checks["worker"]["status"] != "Ready":
            if status_val == "Ready":
                status_val = "Degraded"
            reasons.append("No active worker heartbeat detected")

        scenarios_readiness[sid] = {
            "status": status_val,
            "target_service": svc,
            "at_baseline": bool(wl.get("at_baseline", False)),
            "blocking_run_id": active_by_service.get(svc),
            "reasons": reasons,
        }

    if core_blocked or not k8s_ok:
        global_status = "Blocked"
    elif any(c.get("status") in ("Degraded", "Unknown") for c in checks.values()):
        global_status = "Degraded"
    else:
        global_status = "Ready"

    return {
        "global_status": global_status,
        "checked_at": checked_at,
        "cluster_context": settings.aegisops_k8s_context,
        "namespace": settings.aegisops_k8s_allowed_namespaces[0],
        "automation_control": auto_flag,
        "checks": checks,
        "scenarios": scenarios_readiness,
    }


async def preview_demo_baseline_reset(
    *,
    session: AsyncSession,
    settings: Settings,
    executor: KubernetesExecutor,
) -> dict[str, Any]:
    """Compute exact preview of declared demo resources that differ from baseline."""
    active_runs = (
        (
            await session.execute(
                select(DemoRun).where(
                    DemoRun.status.notin_(["COMPLETED", "ESCALATED", "FAILED", "CANCELLED"])
                )
            )
        )
        .scalars()
        .all()
    )
    active_incidents = (
        (
            await session.execute(
                select(Incident).where(Incident.state.notin_(["RESOLVED", "FAILED"]))
            )
        )
        .scalars()
        .all()
    )

    changes: list[dict[str, Any]] = []
    for svc, spec in DEMO_BASELINE_SPECS.items():
        try:
            snap = await executor.read_deployment_snapshot(
                cluster=settings.aegisops_k8s_context,
                namespace=spec["namespace"],
                deployment_name=svc,
            )
            diffs: dict[str, Any] = {}
            if snap.replicas != spec["replicas"]:
                diffs["replicas"] = {"current": snap.replicas, "target": spec["replicas"]}
            if snap.image != spec["image"]:
                diffs["image"] = {"current": snap.image, "target": spec["image"]}
            if svc == "claims-processor" and snap.memory_limit != spec["memory_limit"]:
                diffs["memory_limit"] = {
                    "current": snap.memory_limit,
                    "target": spec["memory_limit"],
                }
            if "clear_annotation" in spec and spec["clear_annotation"] in snap.annotations:
                diffs["annotations"] = {
                    "remove": spec["clear_annotation"],
                    "current": snap.annotations[spec["clear_annotation"]],
                }
            changes.append(
                {
                    "deployment": svc,
                    "namespace": spec["namespace"],
                    "needs_k8s_patch": bool(diffs),
                    "diffs": diffs,
                    "will_reset_fault_flags": "fault_url" in spec,
                }
            )
        except Exception as exc:
            changes.append(
                {
                    "deployment": svc,
                    "namespace": spec["namespace"],
                    "needs_k8s_patch": False,
                    "error": f"{type(exc).__name__}: {str(exc)[:140]}",
                }
            )

    return {
        "scope_namespace": settings.aegisops_k8s_allowed_namespaces[0],
        "cluster_context": settings.aegisops_k8s_context,
        "preserves_history": True,
        "preserves_unrelated_namespaces": True,
        "active_demo_runs_count": len(active_runs),
        "active_incidents_to_close_count": len(active_incidents),
        "resources": changes,
    }


async def execute_demo_baseline_reset(
    *,
    session_factory: Any,
    redis_client: Any,
    settings: Settings,
    executor: KubernetesExecutor,
    actor_sub: str,
    actor_email: str,
    actor_role: str,
    force_active_runs: bool = False,
) -> dict[str, Any]:
    """Idempotently restore declared demo workloads in aegisops-healthcare while preserving audit history."""
    async with session_factory() as session:
        active_runs = (
            (
                await session.execute(
                    select(DemoRun).where(
                        DemoRun.status.notin_(["COMPLETED", "ESCALATED", "FAILED", "CANCELLED"])
                    )
                )
            )
            .scalars()
            .all()
        )
        if active_runs and not force_active_runs:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Active demo run(s) {[str(r.id) for r in active_runs]} are running; "
                    "pass force=true to cancel active runs and restore baseline."
                ),
            )

    results: list[dict[str, Any]] = []
    partial_failures: list[str] = []
    headers = {"X-Fault-Token": settings.demo_internal_fault_token} if settings.demo_internal_fault_token else {}

    async with httpx.AsyncClient(timeout=5.0) as client:
        for svc, spec in DEMO_BASELINE_SPECS.items():
            svc_outcome: dict[str, Any] = {"deployment": svc, "fault_reset": "skipped", "k8s_patch": "noop"}
            # 1. Reset in-app synthetic fault flags if applicable
            if "fault_url" in spec:
                try:
                    resp = await client.post(
                        spec["fault_url"],
                        headers=headers,
                        json=spec["fault_reset_payload"],
                    )
                    svc_outcome["fault_reset"] = f"HTTP {resp.status_code}"
                except Exception as exc:
                    svc_outcome["fault_reset"] = f"error:{type(exc).__name__}"
                    partial_failures.append(f"{svc} fault_reset: {type(exc).__name__}")

            # 2. Coordinate with Redis target lease and patch K8s deployment baseline
            lease = RedisTargetLease(
                redis_client,
                f"{settings.aegisops_k8s_context}:{spec['namespace']}:{svc}",
                ttl_ms=settings.aegisops_lock_ttl_ms,
                owner_prefix="baseline-reset",
            )
            acquired = await lease.acquire()
            if not acquired:
                svc_outcome["k8s_patch"] = "skipped_lock_busy"
                partial_failures.append(f"{svc}: target lease busy")
                results.append(svc_outcome)
                continue

            try:
                snap = await executor.read_deployment_snapshot(
                    cluster=settings.aegisops_k8s_context,
                    namespace=spec["namespace"],
                    deployment_name=svc,
                )
                patch_body: dict[str, Any] = {}
                if snap.replicas != spec["replicas"]:
                    patch_body.setdefault("spec", {})["replicas"] = spec["replicas"]
                if "clear_annotation" in spec and spec["clear_annotation"] in snap.annotations:
                    patch_body.setdefault("metadata", {}).setdefault("annotations", {})[
                        spec["clear_annotation"]
                    ] = None

                container_patch: dict[str, Any] = {"name": snap.container_name or svc}
                needs_container = False
                if snap.image != spec["image"]:
                    container_patch["image"] = spec["image"]
                    needs_container = True
                if svc == "claims-processor" and snap.memory_limit != spec["memory_limit"]:
                    container_patch["resources"] = {
                        "limits": {"memory": spec["memory_limit"]},
                        "requests": {"memory": spec["memory_request"]},
                    }
                    needs_container = True
                if needs_container:
                    patch_body.setdefault("spec", {}).setdefault("template", {}).setdefault(
                        "spec", {}
                    )["containers"] = [container_patch]

                if patch_body:
                    after = await executor.patch_demo_workload(
                        cluster=settings.aegisops_k8s_context,
                        namespace=spec["namespace"],
                        deployment_name=svc,
                        patch_body=patch_body,
                        wait_rollout=True,
                        timeout_seconds=90,
                    )
                    svc_outcome["k8s_patch"] = f"restored:{after.rollout_status}"
            except (KubernetesGuardError, Exception) as exc:
                svc_outcome["k8s_patch"] = f"error:{type(exc).__name__}"
                partial_failures.append(f"{svc} k8s_patch: {type(exc).__name__}")
            finally:
                await lease.release()
            results.append(svc_outcome)

    # 3. Record audit + honestly close active demo/synthetic incidents as manual_reset_assisted
    closed_incident_ids: list[str] = []
    cancelled_run_ids: list[str] = []
    now = datetime.now(UTC)

    async with session_factory() as session, session.begin():
        runs = (
            (
                await session.execute(
                    select(DemoRun).where(
                        DemoRun.status.notin_(["COMPLETED", "ESCALATED", "FAILED", "CANCELLED"])
                    )
                )
            )
            .scalars()
            .all()
        )
        for run in runs:
            run.status = "CANCELLED"
            run.completed_at = now
            run.error_message = "Cancelled during operator Restore Demo Baseline"
            cancelled_run_ids.append(str(run.id))

        open_incs = (
            (
                await session.execute(
                    select(Incident).where(Incident.state.notin_(["RESOLVED", "FAILED"]))
                )
            )
            .scalars()
            .all()
        )
        for inc in open_incs:
            # Move cleanly through allowed state transitions -> ESCALATED -> RESOLVED (never fake autonomous recovery)
            if inc.state in (
                IncidentState.OPEN.value,
                IncidentState.TRIAGING.value,
                IncidentState.READY_TO_REMEDIATE.value,
                IncidentState.AWAITING_APPROVAL.value,
                IncidentState.REMEDIATING.value,
                IncidentState.VERIFYING.value,
            ):
                await transition_incident(
                    session,
                    incident_id=inc.id,
                    to_state=IncidentState.ESCALATED,
                    actor=f"user:{actor_email}",
                    actor_role=actor_role,
                    event_type="MANUAL_RESET_INITIATED",
                    policy_decision="ESCALATED",
                    details_sanitized={
                        "recovery_mode": "manual_reset_assisted",
                        "note": "Closed by operator Restore Demo Baseline; not autonomous recovery.",
                    },
                )
            await transition_incident(
                session,
                incident_id=inc.id,
                to_state=IncidentState.RESOLVED,
                actor=f"user:{actor_email}",
                actor_role=actor_role,
                event_type="BASELINE_RESET_ASSISTED_CLOSE",
                policy_decision="MANUAL_RESET_ASSISTED",
                timestamp_field="resolved_at",
                extra_updates={
                    "refusal_reason": "Resolved manually via Restore Demo Baseline (manual_reset_assisted).",
                },
                details_sanitized={
                    "recovery_mode": "manual_reset_assisted",
                    "operator_email": actor_email,
                },
            )
            closed_incident_ids.append(str(inc.id))

        session.add(
            AuditRecord(
                execution_id=uuid.uuid4(),
                actor_sub=actor_sub,
                actor_role=actor_role,
                action_type="DEMO_BASELINE_RESET",
                policy_decision="PARTIAL" if partial_failures else "RESTORED",
                before_state_json=None,
                after_state_json={"resources": results},
                details_json={
                    "scope_namespace": settings.aegisops_k8s_allowed_namespaces[0],
                    "cancelled_run_ids": cancelled_run_ids,
                    "closed_incident_ids": closed_incident_ids,
                    "partial_failures": partial_failures,
                    "recovery_mode": "manual_reset_assisted",
                },
                created_at=now,
            )
        )

    return {
        "status": "partial" if partial_failures else "restored",
        "recovery_mode": "manual_reset_assisted",
        "resources": results,
        "cancelled_run_ids": cancelled_run_ids,
        "closed_incident_ids": closed_incident_ids,
        "partial_failures": partial_failures,
        "restored_at": now.isoformat(),
    }
