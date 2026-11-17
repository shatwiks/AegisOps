"""Showcase API endpoints: readiness, baseline reset, automation controls, probes, scenarios, privacy, replay & evidence."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from app import __version__
from app.api.incidents import compute_lifecycle_steps
from app.auth.oidc import (
    AuthenticatedUser,
    optional_authenticate_request,
    require_role,
)
from app.k8s.executor import KubernetesExecutor
from app.models.entities import (
    ApprovalRequest,
    Asset,
    BusinessProbeSample,
    DemoRun,
    ExecutionAttempt,
    Incident,
    IncidentEvent,
)
from app.privacy.scrubber import scrub_text
from app.showcase.controls import (
    collect_system_readiness,
    execute_demo_baseline_reset,
    get_automation_flag,
    preview_demo_baseline_reset,
    set_automation_flag,
)
from app.showcase.probes import execute_business_probe, list_business_probes, serialize_probe
from app.showcase.replay import get_replay_timeline, list_available_replays
from app.showcase.scenarios import (
    SCENARIO_CATALOG,
    build_narration_from_incident,
    launch_demo_scenario,
    serialize_demo_run,
)

router = APIRouter(prefix="/api/v1/showcase", tags=["showcase"])


class AutomationControlRequest(BaseModel):
    automation_paused: bool
    reason: str = Field(default="Toggled by SRE operator", max_length=400)


class ResetExecuteRequest(BaseModel):
    force_active_runs: bool = False


class ScenarioLaunchRequest(BaseModel):
    idempotency_key: str = Field(default="", max_length=128)


class BusinessProbeRunRequest(BaseModel):
    target_service: str = Field(max_length=64)
    incident_id: uuid.UUID | None = None
    demo_run_id: uuid.UUID | None = None


@router.get("/readiness")
async def showcase_readiness(
    request: Request,
    _: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Return global & per-scenario readiness status across Postgres, Redis, Worker, Ollama, Prometheus, Keycloak & Kind."""
    settings = request.app.state.settings
    executor = KubernetesExecutor(settings)
    async with request.app.state.session_factory() as session:
        return await collect_system_readiness(
            engine=request.app.state.engine,
            session=session,
            redis_client=request.app.state.redis,
            settings=settings,
            executor=executor,
        )


@router.get("/controls")
async def showcase_get_controls(
    request: Request,
    _: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Read current backend-enforced automation control flags."""
    async with request.app.state.session_factory() as session:
        return await get_automation_flag(session)


@router.post("/controls/automation")
async def showcase_toggle_automation(
    body: AutomationControlRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_role("operator")),
) -> dict[str, Any]:
    """Pause or resume automated remediation execution (`operator+` + CSRF)."""
    async with request.app.state.session_factory() as session, session.begin():
        return await set_automation_flag(
            session,
            paused=body.automation_paused,
            reason=body.reason,
            actor_sub=user.sub,
            actor_email=user.email,
            actor_role=user.highest_role,
        )


@router.post("/reset/preview")
async def showcase_reset_preview(
    request: Request,
    _: AuthenticatedUser = Depends(require_role("operator")),
) -> dict[str, Any]:
    """Preview exact changes required to restore declared demo workloads in aegisops-healthcare."""
    settings = request.app.state.settings
    executor = KubernetesExecutor(settings)
    async with request.app.state.session_factory() as session:
        return await preview_demo_baseline_reset(
            session=session,
            settings=settings,
            executor=executor,
        )


@router.post("/reset/execute")
async def showcase_reset_execute(
    body: ResetExecuteRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_role("operator")),
) -> dict[str, Any]:
    """Execute idempotent demo baseline reset (`operator+` + CSRF) preserving audit history."""
    settings = request.app.state.settings
    executor = KubernetesExecutor(settings)
    return await execute_demo_baseline_reset(
        session_factory=request.app.state.session_factory,
        redis_client=request.app.state.redis,
        settings=settings,
        executor=executor,
        actor_sub=user.sub,
        actor_email=user.email,
        actor_role=user.highest_role,
        force_active_runs=body.force_active_runs,
    )



@router.get("/scenarios")
async def showcase_list_scenarios(
    request: Request,
    _: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Return catalog of all 5 showcase scenarios plus recent/active demo runs."""
    async with request.app.state.session_factory() as session:
        runs = (
            (
                await session.execute(
                    select(DemoRun).order_by(DemoRun.started_at.desc()).limit(20)
                )
            )
            .scalars()
            .all()
        )
    ordered = sorted(SCENARIO_CATALOG.values(), key=lambda x: int(x["order"]))
    return {
        "scenarios": ordered,
        "recent_runs": [serialize_demo_run(r) for r in runs],
    }


@router.post("/scenarios/{scenario_id}/launch")
async def showcase_launch_scenario(
    scenario_id: str,
    body: ScenarioLaunchRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_role("operator")),
) -> JSONResponse:
    """Launch a durable showcase chaos scenario (`operator+` + CSRF) returning 202 Accepted."""
    settings = request.app.state.settings
    executor = KubernetesExecutor(settings)
    idem_key = body.idempotency_key.strip() or f"{scenario_id}:{uuid.uuid4().hex[:16]}"
    async with request.app.state.session_factory() as session, session.begin():
        run, deduplicated = await launch_demo_scenario(
            session,
            scenario_id=scenario_id,
            idempotency_key=idem_key,
            actor_sub=user.sub,
            actor_email=user.email,
            actor_role=user.highest_role,
            settings=settings,
            executor=executor,
        )
        serialized = serialize_demo_run(run)
    return JSONResponse(
        status_code=status.HTTP_200_OK if deduplicated else status.HTTP_202_ACCEPTED,
        content={"demo_run": serialized, "deduplicated": deduplicated},
    )


@router.get("/runs/{run_id}")
async def showcase_get_run(
    run_id: uuid.UUID,
    request: Request,
    user: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Fetch demo run status, event-driven narration, lifecycle milestones & correlated probes."""
    async with request.app.state.session_factory() as session:
        run = (
            await session.execute(select(DemoRun).where(DemoRun.id == run_id))
        ).scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail="Demo run not found")

        inc: Incident | None = None
        asset_slug: str | None = None
        steps: list[dict[str, Any]] = []
        if run.incident_id is not None:
            row = (
                await session.execute(
                    select(Incident, Asset.slug)
                    .outerjoin(Asset, Incident.primary_asset_id == Asset.id)
                    .where(Incident.id == run.incident_id)
                )
            ).first()
            if row is not None:
                found_inc: Incident = row[0]
                asset_slug = row[1]
                inc = found_inc
                evts = (
                    (
                        await session.execute(
                            select(IncidentEvent)
                            .where(IncidentEvent.incident_id == found_inc.id)
                            .order_by(IncidentEvent.sequence_num.asc())
                        )
                    )
                    .scalars()
                    .all()
                )
                apprs = (
                    (
                        await session.execute(
                            select(ApprovalRequest)
                            .where(ApprovalRequest.incident_id == found_inc.id)
                            .order_by(ApprovalRequest.requested_at.desc())
                        )
                    )
                    .scalars()
                    .all()
                )
                execs = (
                    (
                        await session.execute(
                            select(ExecutionAttempt)
                            .where(ExecutionAttempt.incident_id == found_inc.id)
                            .order_by(ExecutionAttempt.started_at.desc())
                        )
                    )
                    .scalars()
                    .all()
                )
                steps = compute_lifecycle_steps(found_inc, evts, apprs, execs)

        probes = await list_business_probes(session, demo_run_id=run_id, limit=25)
        narration = run.narration_state_json or build_narration_from_incident(run, inc)

    inc_summary: dict[str, Any] | None = None
    if inc is not None:
        inc_summary = {
            "id": str(inc.id),
            "title": inc.title,
            "severity": inc.severity,
            "state": inc.state,
            "asset_slug": asset_slug,
            "proposed_playbook_id": inc.proposed_playbook_id if user is not None else None,
            "redaction_total": int((inc.redaction_stats_json or {}).get("total_redactions", 0)),
            "verification_state": inc.verification_state_json or {},
        }

    return {
        "demo_run": serialize_demo_run(run),
        "narration": narration,
        "incident": inc_summary,
        "lifecycle_steps": steps,
        "probes": probes,
    }


@router.get("/probes")
async def showcase_list_probes(
    request: Request,
    target_service: str | None = Query(default=None),
    incident_id: uuid.UUID | None = Query(default=None),
    demo_run_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    _: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """List bounded history of sanitized semantic business transaction probes."""
    async with request.app.state.session_factory() as session:
        items = await list_business_probes(
            session,
            target_service=target_service,
            incident_id=incident_id,
            demo_run_id=demo_run_id,
            limit=limit,
        )
    return {"items": items}


@router.post("/probes/run")
async def showcase_run_probe(
    body: BusinessProbeRunRequest,
    request: Request,
    _: AuthenticatedUser = Depends(require_role("operator")),
) -> dict[str, Any]:
    """Execute an allowlisted synthetic business transaction probe (`operator+` + CSRF)."""
    settings = request.app.state.settings
    executor = KubernetesExecutor(settings)
    async with request.app.state.session_factory() as session, session.begin():
        try:
            sample: BusinessProbeSample = await execute_business_probe(
                session,
                target_service=body.target_service,
                settings=settings,
                executor=executor,
                probe_type="manual",
                incident_id=body.incident_id,
                demo_run_id=body.demo_run_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        data = serialize_probe(sample)
    return {"probe": data}


FICTIONAL_PRIVACY_PRESETS: list[dict[str, str]] = [
    {
        "id": "eligibility_db_fault_with_member",
        "label": "Fictional Preset 1 — Eligibility DB Timeout + Member Context",
        "text": (
            "ERR_PG_POOL_TIMEOUT_57P03 pool_size=20 active=20 on eligibility-api; "
            "Patient Name: Jane Synth; DOB=1982-06-14; SSN 123-45-6789; "
            "member_id=MBR-90817263; ICD-10=E11.9; email=jane.synth@example.test"
        ),
    },
    {
        "id": "auth_header_and_mbi_leak",
        "label": "Fictional Preset 2 — Upstream Token, IP & MBI Trace",
        "text": (
            "503 upstream timeout from 10.244.1.42 calling provider-directory; "
            "Authorization: Bearer tok_synth_live_987654321abcdef; "
            "MBI-449922881; mrn=MRN-773311; phone=+1-555-014-8821"
        ),
    },
    {
        "id": "jwt_and_claims_batch_crash",
        "label": "Fictional Preset 3 — Claims JWT & Conditional SSN Log",
        "text": (
            "Container claims-processor exited code 137 ERR_OOM_EXIT_137_CLAIMS_BATCH; "
            "header=eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJzeW50aC0wMSJ9.sigSynth9988; "
            "ssn: 987654321; ICD-10=J06.9"
        ),
    },
]

PRIVACY_COVERAGE_NOTES: dict[str, Any] = {
    "warning": "Use fictional data only. Playground text is scrubbed in memory and never persisted or logged.",
    "covered_patterns": [
        "SSN (dashed ###-##-#### and contextual ssn=...)",
        "Medicare / member / claim IDs (MBR-/MEM-/SUB-/PAT-/HICN-/MBI-/CLM- and contextual mrn/member_id/patient_id)",
        "Email addresses, US phone numbers, IPv4 pod/client addresses",
        "DOB fields (dob=..., date_of_birth=..., birth_date=...)",
        "Labeled person names (Patient Name: ..., Member Name: ...)",
        "Authorization Bearer tokens and three-segment JWT strings",
        "Webhook ingestion key-allowlisting (drops unallowlisted labels/annotations automatically)",
    ],
    "coverage_limits": [
        "Unlabeled person names in free-form prose without a key/prefix are outside deterministic regex matching.",
        "Non-US phone number formats and free-form clinical condition text (such as standalone ICD-10 diagnostic codes without patient identifiers) are preserved as operational telemetry unless paired with sensitive fields.",
        "This deterministic boundary filter reduces accidental leak surface; it does not claim formal HIPAA certification.",
    ],
}


class PrivacyPreviewRequest(BaseModel):
    text: str


@router.get("/privacy/presets")
async def showcase_privacy_presets(
    _: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Return fictional synthetic log presets and deterministic scrubber coverage boundaries."""
    return {
        "fictional_presets": FICTIONAL_PRIVACY_PRESETS,
        "coverage_notes": PRIVACY_COVERAGE_NOTES,
        "max_bytes": 8192,
        "rate_limit": "30 requests per 60 seconds",
    }


@router.post("/privacy/preview")
async def showcase_privacy_preview(
    body: PrivacyPreviewRequest,
    request: Request,
    user: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Run in-memory deterministic scrubber without persisting or logging input text."""
    encoded_len = len(body.text.encode("utf-8", errors="ignore"))
    if encoded_len > 8192:
        raise HTTPException(
            status_code=413,
            detail=f"Preview payload too large ({encoded_len} bytes); maximum is 8192 bytes (8 KiB).",
        )

    client_host = request.client.host if request.client else "anonymous"
    client_key = user.sub if user is not None else client_host
    rate_key = f"aegisops:ratelimit:privacy:{client_key}"
    now_ms = int(time.time() * 1000)
    window_ms = 60_000
    redis_client = request.app.state.redis
    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(rate_key, 0, now_ms - window_ms)
    pipe.zadd(rate_key, {f"{now_ms}:{uuid.uuid4().hex[:8]}": now_ms})
    pipe.zcard(rate_key)
    pipe.expire(rate_key, 65)
    _, _, req_count, _ = await pipe.execute()
    if int(req_count) > 30:
        raise HTTPException(
            status_code=429,
            detail="Privacy preview rate limit exceeded (30 requests per 60 seconds).",
        )

    counts: dict[str, int] = {}
    sanitized_text = scrub_text(body.text, counts)
    return {
        "sanitized_text": sanitized_text,
        "total_redactions": sum(counts.values()),
        "redactions_by_category": counts,
        "fictional_presets": FICTIONAL_PRIVACY_PRESETS,
        "coverage_notes": PRIVACY_COVERAGE_NOTES,
        "persisted": False,
    }


@router.get("/replays")
async def showcase_list_replays(
    request: Request,
    _: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """List captured local cluster incident replays + clearly labeled illustrative fixtures (`visitor+`)."""
    async with request.app.state.session_factory() as session:
        items = await list_available_replays(session)
    return {"items": items}


@router.get("/replays/{replay_id}")
async def showcase_get_replay(
    replay_id: str,
    request: Request,
    _: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Fetch read-only chronological replay frames (`visitor+`, never mutates DB/Redis/K8s)."""
    async with request.app.state.session_factory() as session:
        timeline = await get_replay_timeline(session, replay_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail=f"Replay '{replay_id}' not found")
    return {"replay": timeline}


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _read_git_meta_sync() -> dict[str, Any]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_REPO_ROOT),
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        ).decode().strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(_REPO_ROOT),
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        ).decode().strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=str(_REPO_ROOT),
                stderr=subprocess.DEVNULL,
                timeout=2.0,
            ).decode().strip()
        )
        return {"commit": commit, "branch": branch, "dirty_working_tree": dirty}
    except Exception:
        return {"commit": "unavailable", "branch": "unavailable", "dirty_working_tree": None}


def _safe_read_json(rel_path: str) -> dict[str, Any] | None:
    fp = _REPO_ROOT / rel_path
    if not fp.exists():
        return None
    try:
        data = json.loads(fp.read_text(encoding="utf-8", errors="replace"))
        return dict(data) if isinstance(data, dict) else {"raw": data}
    except Exception:
        return None


@router.get("/overview")
async def showcase_overview(
    user: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Role-aware executive summary & permission capability flags (`visitor+`)."""
    role = user.highest_role if user is not None else "visitor"
    return {
        "project_name": "AegisOps",
        "subtitle": "Autonomous AIOps, CMDB Blast-Radius & Self-Healing Kubernetes Control Plane",
        "disclaimer": (
            "Independent synthetic healthcare engineering demonstration. No affiliation with any healthcare organization "
            "and not certified for clinical production environments."
        ),
        "role": role,
        "is_visitor": user is None,
        "capabilities": {
            "can_view_public_showcase": True,
            "can_run_privacy_playground": True,
            "can_browse_and_search_runbooks": True,
            "can_view_replay": True,
            "can_view_live_incidents": user is not None,
            "can_export_postmortem": user is not None,
            "can_launch_scenarios_and_probes": role in ("operator", "approver"),
            "can_upload_runbooks": role in ("operator", "approver"),
            "can_reset_baseline": role in ("operator", "approver"),
            "can_toggle_automation": role in ("operator", "approver"),
            "can_approve_high_risk_mfa": role == "approver",
        },
        "five_pillars": [
            {"title": "1. Edge Privacy Scrubber", "detail": "Strips synthetic PHI/PII & bearer tokens before logs, PostgreSQL, or LLM prompts."},
            {"title": "2. CMDB Blast Radius", "detail": "Computes P1-P4 severity from live PostgreSQL dependency hops."},
            {"title": "3. Hybrid RAG + Policy Gate", "detail": "Fuses PostgreSQL FTS + 768-dim pgvector (cosine >= 0.78) with untrusted-input policy checks."},
            {"title": "4. Action-Bound TOTP MFA", "detail": "High-risk memory increases & rollbacks lock onto K8s UID + resourceVersion + single-use 6-digit OTP."},
            {"title": "5. 60s Sustained Watchdog", "detail": "Verifies real pod readiness & latency continuously before declaring recovery."},
        ],
    }


@router.get("/evidence")
async def showcase_engineering_evidence(
    request: Request,
    _: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Serve sanitized real build/git metadata, DB revision, benchmarks, test reports & honest boundaries (`visitor+`)."""
    settings = request.app.state.settings
    git_meta = await asyncio.to_thread(_read_git_meta_sync)

    alembic_rev = "unknown"
    async with request.app.state.session_factory() as session:
        try:
            row = (await session.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))).first()
            if row is not None:
                alembic_rev = str(row[0])
        except Exception:
            alembic_rev = "unavailable"

    ragas = _safe_read_json("docs/evidence/ragas-evaluation.json")
    k6 = _safe_read_json("docs/evidence/k6-summary.json")
    chaos_rep = _safe_read_json("docs/evidence/chaos-scenarios-report.json")

    evidence_dir = _REPO_ROOT / "docs" / "evidence"
    text_reports: list[dict[str, Any]] = []
    for fname in ("showcase-test-gate.txt", "phase-05-chaos-release.txt", "phase-04-auth-console.txt"):
        fp = evidence_dir / fname
        if fp.exists():
            stat = fp.stat()
            text_reports.append(
                {
                    "filename": fname,
                    "modified_at_utc": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                    "size_bytes": stat.st_size,
                    "excerpt": fp.read_text(encoding="utf-8", errors="replace")[-1200:],
                }
            )

    return {
        "build": {
            "app_version": __version__,
            "python_version": sys.version.split()[0],
            "alembic_revision": alembic_rev,
            "chat_model": settings.aegisops_chat_model,
            "embedding_model": settings.aegisops_embedding_model,
            "embedding_dimensions": settings.aegisops_embedding_dimensions,
            "cosine_threshold": settings.aegisops_similarity_threshold,
            "sustained_recovery_seconds": settings.aegisops_recovery_window_seconds,
            **git_meta,
        },
        "architecture_boundaries": [
            "Local Kubernetes target uses `kind-aegisops-local` namespace `aegisops-healthcare` with ServiceAccount impersonation.",
            "Control-plane PostgreSQL/Redis are logically isolated and never injected as chaos targets.",
            "Database failover is intentionally unimplemented for single-instance demo Postgres and strictly escalates (`RB-011`).",
            "Privacy scrubbing uses deterministic allowlists and regex patterns; tested on synthetic corpus, not HIPAA-certified.",
        ],
        "benchmarks": {
            "ragas": (
                {
                    "model": ragas.get("model"),
                    "embedding_model": ragas.get("embedding_model"),
                    "sample_count": ragas.get("sample_count"),
                    "metrics": ragas.get("metrics"),
                    "limitations": ragas.get("limitations"),
                }
                if ragas
                else None
            ),
            "k6": (
                {
                    "total_requests": ((k6.get("metrics") or {}).get("http_reqs") or {}).get("count"),
                    "http_req_duration_p95_ms": ((k6.get("metrics") or {}).get("http_req_duration") or {}).get("p(95)"),
                    "checks_passed": ((k6.get("metrics") or {}).get("checks") or {}).get("passes"),
                    "checks_failed": ((k6.get("metrics") or {}).get("checks") or {}).get("fails"),
                }
                if k6
                else None
            ),
            "chaos_scenarios_report_present": chaos_rep is not None,
        },
        "test_reports": text_reports,
        "documentation_links": [
            {"label": "System Working Flow (workingflow.md)", "path": "workingflow.md"},
            {"label": "Showcase Guide (docs/SHOWCASE_GUIDE.md)", "path": "docs/SHOWCASE_GUIDE.md"},
            {"label": "Showcase Test Report (docs/SHOWCASE_TEST_REPORT.md)", "path": "docs/SHOWCASE_TEST_REPORT.md"},
            {"label": "Dependency Ledger (docs/DEPENDENCIES.md)", "path": "docs/DEPENDENCIES.md"},
        ],
    }
