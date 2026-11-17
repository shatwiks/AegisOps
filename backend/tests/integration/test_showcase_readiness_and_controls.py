"""Integration tests for Showcase Phase 01: readiness, RBAC, pause control, baseline reset, prompt capture & watchdog ticks."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.k8s.executor import KubernetesExecutor
from app.main import create_app
from app.models.entities import (
    Asset,
    AuditRecord,
    Incident,
    IncidentEvent,
    OutboxJob,
    SystemControlFlag,
)
from app.rag.diagnosis import generate_diagnosis_with_record
from app.rag.retriever import RetrievedDocument
from app.seed.cmdb_seed import seed_cmdb
from app.worker.runner import run_worker_once
from app.worker.watchdog import HealthProbeSample, verify_sustained_recovery


async def _fetch_token(username: str, password: str, settings: Any) -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            settings.aegisops_oidc_token_url,
            data={
                "grant_type": "password",
                "client_id": settings.aegisops_oidc_client_id,
                "username": username,
                "password": password,
                "scope": "openid profile email",
            },
        )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["access_token"])


@pytest.mark.asyncio
async def test_readiness_rbac_pause_control_and_baseline_reset() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    demo_pw = os.environ["KEYCLOAK_DEMO_USER_PASSWORD"]
    app = create_app(settings_override=settings)

    viewer_tok = await _fetch_token("viewer@aegisops.local", demo_pw, settings)
    op_tok = await _fetch_token("operator@aegisops.local", demo_pw, settings)
    inc_id = uuid.uuid4()

    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as session, session.begin():
            await seed_cmdb(session)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as api:
            try:
                # 1. Visitor can view readiness and controls
                r_ready = await api.get("/api/v1/showcase/readiness")
                assert r_ready.status_code == 200, r_ready.text
                body = r_ready.json()
                assert body["global_status"] in ("Ready", "Degraded", "Blocked")
                assert "scenarios" in body
                assert set(body["scenarios"].keys()) == {
                    "traffic_spike",
                    "db_pool_freeze",
                    "bad_canary_update",
                    "oom_memory_crash",
                    "pii_leak_and_db_failure",
                }
                assert "eligibility-api" in body["checks"]["kubernetes"]["workloads"]

                # 2. Unauthenticated visitor & viewer cannot mutate controls or reset baseline
                assert (
                    await api.post(
                        "/api/v1/showcase/controls/automation",
                        json={"automation_paused": True, "reason": "anon"},
                    )
                ).status_code == 401
                assert (await api.post("/api/v1/showcase/reset/preview")).status_code == 401
                assert (
                    await api.post(
                        "/api/v1/showcase/controls/automation",
                        headers={"Authorization": f"Bearer {viewer_tok}"},
                        json={"automation_paused": True, "reason": "viewer"},
                    )
                ).status_code == 403
                assert (
                    await api.post(
                        "/api/v1/showcase/reset/execute",
                        headers={"Authorization": f"Bearer {viewer_tok}"},
                        json={"force_active_runs": False},
                    )
                ).status_code == 403

                # 3. Operator pauses automation -> READY_TO_REMEDIATE execution job is held safely
                pause_resp = await api.post(
                    "/api/v1/showcase/controls/automation",
                    headers={"Authorization": f"Bearer {op_tok}"},
                    json={"automation_paused": True, "reason": "Pause test"},
                )
                assert pause_resp.status_code == 200, pause_resp.text
                assert pause_resp.json()["automation_paused"] is True

                async with app.state.session_factory() as session, session.begin():
                    asset = (
                        await session.execute(
                            select(Asset).where(Asset.slug == "provider-directory")
                        )
                    ).scalar_one()
                    session.add(
                        Incident(
                            id=inc_id,
                            dedup_key=f"test-pause-{inc_id}",
                            alert_fingerprint="fp-pause",
                            alertname="TestPauseHold",
                            title="TestPauseHold",
                            summary_sanitized="Synthetic test pause check",
                            primary_asset_id=asset.id,
                            severity="P3",
                            severity_explanation_json={},
                            state="READY_TO_REMEDIATE",
                            proposed_playbook_id="stateless_deployment_restart",
                            proposed_parameters_json={"rollout_strategy": "RollingUpdate"},
                            source_provenance="automated_test",
                        )
                    )
                    await session.flush()
                    session.add(
                        OutboxJob(
                            incident_id=inc_id,
                            job_type="EXECUTE_REMEDIATION",
                            dedup_job_key=f"test-exec-pause-{inc_id}",
                            payload_sanitized_json={"incident_id": str(inc_id)},
                            status="PENDING",
                        )
                    )

                executor = KubernetesExecutor(settings)
                await run_worker_once(
                    worker_id="test-pause-worker",
                    session_factory=app.state.session_factory,
                    redis_client=app.state.redis,
                    settings=settings,
                    executor=executor,
                )

                async with app.state.session_factory() as session:
                    held_inc = (
                        await session.execute(select(Incident).where(Incident.id == inc_id))
                    ).scalar_one()
                    assert held_inc.state == "READY_TO_REMEDIATE"
                    hold_evt = (
                        await session.execute(
                            select(IncidentEvent).where(
                                IncidentEvent.incident_id == inc_id,
                                IncidentEvent.event_type == "AUTOMATION_PAUSED_HOLD",
                            )
                        )
                    ).scalar_one_or_none()
                    assert hold_evt is not None
                    held_job = (
                        await session.execute(
                            select(OutboxJob).where(
                                OutboxJob.dedup_job_key == f"test-exec-pause-{inc_id}"
                            )
                        )
                    ).scalar_one()
                    assert held_job.status == "PENDING"
                    assert held_job.attempts == 0

                # 4. Operator previews & runs baseline reset -> closes open test incident as manual_reset_assisted
                prev = await api.post(
                    "/api/v1/showcase/reset/preview",
                    headers={"Authorization": f"Bearer {op_tok}"},
                )
                assert prev.status_code == 200, prev.text
                assert prev.json()["scope_namespace"] == "aegisops-healthcare"

                rst = await api.post(
                    "/api/v1/showcase/reset/execute",
                    headers={"Authorization": f"Bearer {op_tok}"},
                    json={"force_active_runs": True},
                )
                assert rst.status_code == 200, rst.text
                rst_body = rst.json()
                assert rst_body["recovery_mode"] == "manual_reset_assisted"
                assert str(inc_id) in rst_body["closed_incident_ids"]

                async with app.state.session_factory() as session:
                    closed = (
                        await session.execute(select(Incident).where(Incident.id == inc_id))
                    ).scalar_one()
                    assert closed.state == "RESOLVED"
                    assert "manual_reset_assisted" in (closed.refusal_reason or "")
                    audit = (
                        await session.execute(
                            select(AuditRecord)
                            .where(AuditRecord.action_type == "DEMO_BASELINE_RESET")
                            .order_by(AuditRecord.created_at.desc())
                        )
                    ).scalars().first()
                    assert audit is not None
                    assert audit.details_json["recovery_mode"] == "manual_reset_assisted"
            finally:
                # Always restore automation_paused=False and clean test job/incident state
                await api.post(
                    "/api/v1/showcase/controls/automation",
                    headers={"Authorization": f"Bearer {op_tok}"},
                    json={"automation_paused": False, "reason": "Cleanup after Phase 01 test"},
                )
                async with app.state.session_factory() as session, session.begin():
                    flag = (
                        await session.execute(
                            select(SystemControlFlag).where(
                                SystemControlFlag.key == "automation_paused"
                            )
                        )
                    ).scalar_one_or_none()
                    if flag:
                        flag.bool_value = False
                    row = (
                        await session.execute(
                            select(OutboxJob).where(
                                OutboxJob.dedup_job_key == f"test-exec-pause-{inc_id}"
                            )
                        )
                    ).scalar_one_or_none()
                    if row:
                        row.status = "COMPLETED"
                        row.completed_at = datetime.now(UTC)
                    t_inc = (
                        await session.execute(select(Incident).where(Incident.id == inc_id))
                    ).scalar_one_or_none()
                    if t_inc and t_inc.state not in ("RESOLVED", "FAILED"):
                        t_inc.state = "FAILED"


@pytest.mark.asyncio
async def test_prompt_capture_and_watchdog_tick_callback() -> None:
    get_settings.cache_clear()
    base = get_settings()
    settings = base.model_copy(
        update={
            "aegisops_recovery_window_seconds": 1,
            "aegisops_recovery_poll_interval_seconds": 1,
        }
    )

    doc = RetrievedDocument(
        slug="rb-002-eligibility-db-pool-exhaustion",
        title="RB-002 Eligibility DB Pool Exhausted",
        doc_type="RUNBOOK",
        service_slug="eligibility-api",
        risk_tier="LOW",
        permitted_playbook_id="stateless_deployment_restart",
        applicability_json={"services": ["eligibility-api"]},
        preconditions_json={"stateless_required": True},
        evidence_requirements_json=["db_pool saturation"],
        symptoms="ERR_PG_POOL_TIMEOUT_57P03",
        body_markdown="Restart eligibility-api.",
        vector_similarity=0.91,
        lexical_score=0.5,
        rrf_score=0.03,
        vector_rank=1,
        lexical_rank=1,
    )

    proposal, prompt_rec = await generate_diagnosis_with_record(
        alertname="EligibilityDbPoolExhausted",
        asset_slug="eligibility-api",
        severity="P1",
        summary_sanitized="ERR_PG_POOL_TIMEOUT_57P03 on eligibility-api",
        blast_downstream_slugs=["claims-processor"],
        docs=[doc],
        settings=settings,
    )
    assert proposal.cited_runbook_ids
    assert prompt_rec["captured"] is True
    assert "<untrusted_telemetry>" in prompt_rec["user_prompt"]
    assert "<retrieved_runbook_data>" in prompt_rec["user_prompt"]
    assert prompt_rec["model"] == settings.aegisops_chat_model

    # Watchdog tick callback records reset_count cleanly
    seq = [True, False, True, True]
    idx = 0
    ticks: list[tuple[bool, int]] = []

    async def _probe(**_: Any) -> HealthProbeSample:
        nonlocal idx
        healthy = seq[min(idx, len(seq) - 1)]
        idx += 1
        return HealthProbeSample(
            checked_at=datetime.now(UTC),
            healthy=healthy,
            rollout_ready=healthy,
            http_probe_ok=healthy,
            metrics_fresh_and_ok=healthy,
            reasons=[] if healthy else ["simulated transient dip"],
        )

    async def _cb(*, sample: HealthProbeSample, reset_count: int, **_: Any) -> None:
        ticks.append((sample.healthy, reset_count))

    ok, _, _ = await verify_sustained_recovery(
        asset=Asset(
            slug="eligibility-api",
            name="eligibility-api",
            namespace="aegisops-healthcare",
            cluster="kind-aegisops-local",
            asset_type="SERVICE",
            criticality="TIER_1_CRITICAL",
            owner_team="core",
            stateless_eligible=True,
        ),
        settings=settings,
        executor=KubernetesExecutor(settings),
        probe_fn=_probe,
        max_wait_seconds=10,
        on_sample_callback=_cb,
    )
    assert ok is True
    assert len(ticks) >= 4
    assert any(r >= 1 for _, r in ticks)
