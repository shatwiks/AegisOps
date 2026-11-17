"""Integration tests for Showcase Phase 02: queue tabs, provenance filtering, pagination & 7-step lifecycle."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.incidents import compute_lifecycle_steps
from app.config import get_settings
from app.main import create_app
from app.models.entities import ApprovalRequest, Asset, DemoRun, Incident
from app.seed.cmdb_seed import seed_cmdb


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
async def test_queue_filters_pagination_counts_and_trusted_provenance() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    demo_pw = os.environ["KEYCLOAK_DEMO_USER_PASSWORD"]
    app = create_app(settings_override=settings)
    viewer_tok = await _fetch_token("viewer@aegisops.local", demo_pw, settings)

    demo_run_id = uuid.uuid4()
    test_inc_id = uuid.uuid4()
    demo_inc_id = uuid.uuid4()
    esc_inc_id = uuid.uuid4()
    legacy_inc_id = uuid.uuid4()

    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as session, session.begin():
            await seed_cmdb(session)
            prov = (
                await session.execute(select(Asset).where(Asset.slug == "provider-directory"))
            ).scalar_one()
            session.add(
                DemoRun(
                    id=demo_run_id,
                    scenario_id="traffic_spike",
                    title="Queue Test Run",
                    target_service="provider-directory",
                    idempotency_key=f"qtest-{demo_run_id}",
                    actor_sub="op-1",
                    actor_email="operator@aegisops.local",
                    status="COMPLETED",
                )
            )
            await session.flush()
            now = datetime.now(UTC)
            session.add_all(
                [
                    Incident(
                        id=test_inc_id,
                        dedup_key=f"q-auto-{test_inc_id}",
                        alert_fingerprint="fp-auto",
                        alertname="AutoTestHidden",
                        title="AutoTestHidden",
                        summary_sanitized="Hidden by Hide Test Runs default",
                        primary_asset_id=prov.id,
                        severity="P3",
                        severity_explanation_json={},
                        state="FAILED",
                        source_provenance="automated_test",
                        ingested_at=now,
                    ),
                    Incident(
                        id=demo_inc_id,
                        dedup_key=f"q-demo-{demo_inc_id}",
                        alert_fingerprint="fp-demo",
                        alertname="ProviderDirectoryHighLatencyCpu",
                        title="DemoTrafficSpikeUniqueSearchMarker",
                        summary_sanitized="Interactive demo resolved cleanly",
                        primary_asset_id=prov.id,
                        severity="P3",
                        severity_explanation_json={"downstream_impact_slugs": ["member-portal-gateway"]},
                        state="RESOLVED",
                        source_provenance="interactive_demo",
                        demo_run_id=demo_run_id,
                        redaction_stats_json={"total_redactions": 0},
                        diagnosis_json={"citations": [{"slug": "rb-003"}], "proposal": {"root_cause_summary": "CPU saturation", "reasoning": "Load exceeded 2 slots"}},
                        proposed_playbook_id="replica_scale_out_bounded",
                        proposed_parameters_json={"target_replicas": 3},
                        triaged_at=now - timedelta(seconds=80),
                        mutated_at=now - timedelta(seconds=70),
                        first_recovered_at=now - timedelta(seconds=62),
                        resolved_at=now,
                        verification_state_json={"status": "passed", "window_seconds": 60, "sample_count": 12},
                        ingested_at=now - timedelta(seconds=120),
                    ),
                    Incident(
                        id=esc_inc_id,
                        dedup_key=f"q-esc-{esc_inc_id}",
                        alert_fingerprint="fp-esc",
                        alertname="PostgresReplicationLag",
                        title="EscalatedDbUniqueMarker",
                        summary_sanitized="Stateful DB lag escalation",
                        primary_asset_id=prov.id,
                        severity="P1",
                        severity_explanation_json={"downstream_impact_slugs": ["eligibility-api"]},
                        state="ESCALATED",
                        source_provenance="interactive_demo",
                        refusal_reason="Stateful database failover prohibited (RB-011)",
                        ingested_at=now - timedelta(seconds=100),
                    ),
                    Incident(
                        id=legacy_inc_id,
                        dedup_key=f"q-unk-{legacy_inc_id}",
                        alert_fingerprint="fp-unk",
                        alertname="LegacyAlert",
                        title="LegacyUnknownProvenanceMarker",
                        summary_sanitized="Unknown provenance preserved",
                        primary_asset_id=prov.id,
                        severity="P2",
                        severity_explanation_json={},
                        state="RESOLVED",
                        source_provenance="unknown",
                        ingested_at=now - timedelta(seconds=200),
                    ),
                ]
            )

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as api:
                headers = {"Authorization": f"Bearer {viewer_tok}"}

                # 1. Default hide_test_runs=True hides automated_test rows, keeps interactive_demo & unknown
                r_default = await api.get(
                    "/api/v1/incidents",
                    headers=headers,
                    params={"tab": "all", "search": "Hidden"},
                )
                assert r_default.status_code == 200, r_default.text
                assert r_default.json()["total_filtered"] == 0
                assert r_default.json()["tab_counts"]["hidden_test_count"] >= 1

                # 2. Toggling hide_test_runs=False reveals automated_test rows
                r_unhidden = await api.get(
                    "/api/v1/incidents",
                    headers=headers,
                    params={"tab": "all", "hide_test_runs": False, "search": "AutoTestHidden"},
                )
                assert r_unhidden.status_code == 200
                assert r_unhidden.json()["total_filtered"] >= 1
                assert r_unhidden.json()["items"][0]["source_provenance"] == "automated_test"

                # 3. Legacy unknown provenance is preserved honestly
                r_unk = await api.get(
                    "/api/v1/incidents",
                    headers=headers,
                    params={"search": "LegacyUnknownProvenanceMarker"},
                )
                assert r_unk.status_code == 200
                assert r_unk.json()["items"][0]["source_provenance"] == "unknown"

                # 4. Detail endpoint includes 7 lifecycle steps and never marks Escalated as green Resolved
                r_esc = await api.get(f"/api/v1/incidents/{esc_inc_id}", headers=headers)
                assert r_esc.status_code == 200, r_esc.text
                esc_steps = r_esc.json()["lifecycle_steps"]
                assert len(esc_steps) == 7
                assert esc_steps[-1]["status"] == "blocked"
                assert esc_steps[-1]["label"] == "Human escalation"

                r_demo = await api.get(f"/api/v1/incidents/{demo_inc_id}", headers=headers)
                assert r_demo.status_code == 200
                demo_body = r_demo.json()
                assert demo_body["lifecycle_steps"][1]["summary"] == "0 sensitive identifier patterns detected in payload."
                assert demo_body["lifecycle_steps"][6]["status"] == "completed"
                assert "ai_recommendation_hypothesis" in demo_body["why_this_action"]
                assert len(demo_body["why_this_action"]["questions"]) == 7
        finally:
            async with app.state.session_factory() as session, session.begin():
                for iid in (test_inc_id, demo_inc_id, esc_inc_id, legacy_inc_id):
                    await session.execute(delete(Incident).where(Incident.id == iid))
                await session.execute(delete(DemoRun).where(DemoRun.id == demo_run_id))


def test_lifecycle_steps_live_watchdog_and_mfa_branches() -> None:
    now = datetime.now(UTC)
    inc = Incident(
        id=uuid.uuid4(),
        dedup_key="unit-verifying",
        alert_fingerprint="fp-u",
        alertname="ClaimsProcessorMemoryPressure",
        title="OOM test",
        summary_sanitized="ERR_OOM_EXIT_137_CLAIMS_BATCH",
        severity="P2",
        severity_explanation_json={"downstream_impact_slugs": []},
        state="VERIFYING",
        source_provenance="interactive_demo",
        redaction_stats_json={"total_redactions": 2},
        diagnosis_json={
            "citations": [{"slug": "rb-001"}],
            "proposal": {"root_cause_summary": "Batch heap grew"},
            "policy_checks": {"risk_tier": "HIGH"},
        },
        proposed_playbook_id="memory_limit_increase_bounded",
        verification_state_json={
            "status": "observing",
            "elapsed_healthy_seconds": 35.0,
            "window_seconds": 60.0,
            "reset_count": 1,
        },
        ingested_at=now,
        triaged_at=now,
        approved_at=now,
        mutated_at=now,
    )
    appr = ApprovalRequest(
        id=uuid.uuid4(),
        incident_id=inc.id,
        playbook_id="memory_limit_increase_bounded",
        playbook_version="1.0.0",
        parameters_hash="abc",
        parameters_json={"memory_mi": 384},
        target_asset_slug="claims-processor",
        target_k8s_uid="uid-1",
        target_resource_version="rv-1",
        status="CONSUMED",
        expires_at=now + timedelta(minutes=10),
    )
    steps = compute_lifecycle_steps(inc, [], [appr], [])
    assert len(steps) == 7
    assert steps[1]["status"] == "completed"
    assert "2 sensitive" in steps[1]["summary"]
    assert steps[5]["status"] == "running"
    assert "35 of 60 seconds observed" in steps[5]["summary"]
    assert "reset 1x" in steps[5]["summary"]
    assert steps[6]["status"] == "pending"
