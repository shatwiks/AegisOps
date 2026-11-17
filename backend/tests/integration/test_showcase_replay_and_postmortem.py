"""Integration tests for Showcase Phase 05: Recorded Incident Replay & Postmortem Exports (.md + .pdf)."""

from __future__ import annotations

import os
import re
import uuid
import zlib
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.config import get_settings
from app.main import create_app
from app.models.entities import (
    ApprovalRequest,
    Asset,
    BusinessProbeSample,
    ExecutionAttempt,
    Incident,
    IncidentEvent,
)
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


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Decompress FlateDecode streams inside generated %PDF-1.4 bytes for content inspection."""
    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, flags=re.DOTALL):
        raw = match.group(1)
        try:
            chunks.append(zlib.decompress(raw).decode("latin-1", errors="replace"))
        except zlib.error:
            chunks.append(raw.decode("latin-1", errors="replace"))
    return "\n".join(chunks)


@pytest.mark.asyncio
async def test_recorded_replay_and_unified_markdown_pdf_postmortem_exports() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    demo_pw = os.environ["KEYCLOAK_DEMO_USER_PASSWORD"]
    app = create_app(settings_override=settings)
    viewer_tok = await _fetch_token("viewer@aegisops.local", demo_pw, settings)

    resolved_inc_id = uuid.uuid4()
    esc_inc_id = uuid.uuid4()
    t0 = datetime.now(UTC) - timedelta(minutes=3)

    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as session, session.begin():
            await seed_cmdb(session)
            claims = (
                await session.execute(select(Asset).where(Asset.slug == "claims-processor"))
            ).scalar_one()
            pg_db = (
                await session.execute(select(Asset).where(Asset.slug == "postgres-claims-db"))
            ).scalar_one()

            # 1. Resolved incident with long timeline, non-ASCII text, script attempt in summary, approval & execution diff
            session.add(
                Incident(
                    id=resolved_inc_id,
                    dedup_key=f"p5-res-{resolved_inc_id}",
                    alert_fingerprint=f"fp-p5-res-{resolved_inc_id}",
                    alertname="ClaimsProcessorMemoryPressure",
                    title="ClaimsProcessorMemoryPressure — batch surge → OOM",
                    summary_sanitized="Heap >= 90% on claims-processor <script>alert(1)</script> ERR_OOM_EXIT_137",
                    primary_asset_id=claims.id,
                    severity="P2",
                    severity_explanation_json={"downstream_impact_slugs": []},
                    state="RESOLVED",
                    source_provenance="interactive_demo",
                    proposed_playbook_id="memory_limit_increase_bounded",
                    proposed_parameters_json={"memory_mi": 384},
                    redaction_stats_json={"total_redactions": 3, "redaction_counts": {"ssn_dashed": 2, "bearer": 1}},
                    diagnosis_json={
                        "proposal": {
                            "root_cause_summary": "Batch surge pushed working set beyond 192Mi limit",
                            "proposed_playbook_id": "memory_limit_increase_bounded",
                            "uncertainty_level": "LOW",
                        },
                        "citations": [
                            {
                                "slug": "rb-001-claims-processor-oom",
                                "title": "RB-001: Claims Processor OOM",
                                "doc_type": "RUNBOOK",
                                "vector_similarity": 0.91,
                                "lexical_score": 0.65,
                                "rrf_score": 0.032,
                            }
                        ],
                        "policy_checks": {"risk_tier": "HIGH", "threshold_passed": True},
                    },
                    verification_state_json={"status": "passed", "window_seconds": 60, "elapsed_healthy_seconds": 60.0, "reset_count": 0},
                    fault_onset_at=t0,
                    detected_at=t0 + timedelta(seconds=6),
                    ingested_at=t0 + timedelta(seconds=7),
                    triaged_at=t0 + timedelta(seconds=14),
                    approved_at=t0 + timedelta(seconds=25),
                    mutated_at=t0 + timedelta(seconds=31),
                    first_recovered_at=t0 + timedelta(seconds=42),
                    resolved_at=t0 + timedelta(seconds=102),
                )
            )
            await session.flush()

            # Add 32 timeline events so PDF exercises automatic multi-page breaks
            for idx in range(32):
                session.add(
                    IncidentEvent(
                        incident_id=resolved_inc_id,
                        event_type="WATCHDOG_TICK" if 6 <= idx <= 29 else ("REMEDIATION_SUCCEEDED" if idx == 5 else "ALERT_INGESTED"),
                        from_state="VERIFYING" if idx > 5 else "OPEN",
                        to_state="RESOLVED" if idx == 31 else ("VERIFYING" if idx >= 5 else "TRIAGING"),
                        actor="system:outbox-worker",
                        details_sanitized_json={"step": idx, "reason": f"Observed healthy tick #{idx}"},
                        created_at=t0 + timedelta(seconds=8 + idx * 2),
                    )
                )

            session.add(
                ApprovalRequest(
                    incident_id=resolved_inc_id,
                    playbook_id="memory_limit_increase_bounded",
                    playbook_version="1.0.0",
                    parameters_hash="hash-mem-384",
                    parameters_json={"memory_mi": 384},
                    target_asset_slug="claims-processor",
                    target_k8s_uid="uid-claims-1",
                    target_resource_version="rv-100",
                    status="CONSUMED",
                    requested_at=t0 + timedelta(seconds=15),
                    expires_at=t0 + timedelta(minutes=10),
                    decided_by_sub="approver-sub",
                    decided_by_email="approver@aegisops.local",
                    decided_by_role="approver",
                    totp_timecode_used=999111222,
                    decided_at=t0 + timedelta(seconds=25),
                    consumed_at=t0 + timedelta(seconds=30),
                )
            )
            session.add(
                ExecutionAttempt(
                    incident_id=resolved_inc_id,
                    idempotency_key=f"p5-exec-{resolved_inc_id}",
                    playbook_id="memory_limit_increase_bounded",
                    playbook_version="1.0.0",
                    parameters_json={"memory_mi": 384},
                    target_cluster="kind-aegisops-local",
                    target_namespace="aegisops-healthcare",
                    target_deployment="claims-processor",
                    lock_token="lock-test",
                    status="SUCCEEDED",
                    before_state_sanitized_json={"replicas": 1, "memory_limit": "192Mi"},
                    after_state_sanitized_json={"replicas": 1, "memory_limit": "384Mi"},
                    started_at=t0 + timedelta(seconds=17),
                    completed_at=t0 + timedelta(seconds=18),
                )
            )
            session.add(
                BusinessProbeSample(
                    incident_id=resolved_inc_id,
                    target_service="claims-processor",
                    endpoint_path="/claims/adjudicate",
                    probe_type="post_recovery",
                    status="PASS",
                    http_status=200,
                    latency_ms=19.4,
                    summary_sanitized="Synthetic claim adjudication succeeded (19.4ms).",
                    checked_at=t0 + timedelta(seconds=72),
                )
            )

            # 2. Escalated incident (must NEVER claim Verified Resolution)
            session.add(
                Incident(
                    id=esc_inc_id,
                    dedup_key=f"p5-esc-{esc_inc_id}",
                    alert_fingerprint=f"fp-p5-esc-{esc_inc_id}",
                    alertname="PostgresReplicationLagHigh",
                    title="PostgresReplicationLagHigh on postgres-claims-db",
                    summary_sanitized="ERR_PG_REPLICATION_LAG_CRITICAL",
                    primary_asset_id=pg_db.id,
                    severity="P1",
                    severity_explanation_json={},
                    state="ESCALATED",
                    source_provenance="automated_test",
                    refusal_reason="Matched runbook 'rb-011-postgres-replication-lag' prohibits automated remediation.",
                    ingested_at=t0,
                )
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as api:
            try:
                # 1. Recorded Replay listing & timelines (`visitor+`, read-only)
                r_list = await api.get("/api/v1/showcase/replays")
                assert r_list.status_code == 200, r_list.text
                items = r_list.json()["items"]
                assert any(i["source_type"] == "illustrative_fixture" for i in items)
                assert any(i["replay_id"] == str(resolved_inc_id) and i["source_type"] == "captured_live_run" for i in items)

                fix_tl = await api.get("/api/v1/showcase/replays/fixture-traffic-spike-recovery")
                assert fix_tl.status_code == 200
                assert len(fix_tl.json()["replay"]["frames"]) == 5

                cap_tl = await api.get(f"/api/v1/showcase/replays/{resolved_inc_id}")
                assert cap_tl.status_code == 200, cap_tl.text
                frames = cap_tl.json()["replay"]["frames"]
                assert len(frames) == 32
                # Early frames do not show post-mutation 384Mi snapshot yet
                assert frames[0]["topology_overlay"]["historical_k8s_snapshot"] != {"replicas": 1, "memory_limit": "384Mi"}
                # Post-execution frame captures historical 384Mi transition cleanly
                assert frames[6]["topology_overlay"]["historical_k8s_snapshot"] == {"replicas": 1, "memory_limit": "384Mi"}

                # 2. Postmortem .md and .pdf exports (`viewer+` auth enforced, unified snapshot model)
                assert (await api.get(f"/api/v1/incidents/{resolved_inc_id}/postmortem.md")).status_code == 401
                assert (await api.get(f"/api/v1/incidents/{resolved_inc_id}/postmortem.pdf")).status_code == 401

                md_resp = await api.get(
                    f"/api/v1/incidents/{resolved_inc_id}/postmortem.md",
                    headers={"Authorization": f"Bearer {viewer_tok}"},
                )
                assert md_resp.status_code == 200, md_resp.text
                assert "text/markdown" in md_resp.headers["content-type"]
                assert f"aegisops-postmortem-{resolved_inc_id}.md" in md_resp.headers["content-disposition"]
                md_text = md_resp.text
                assert "Verified Resolution Postmortem" in md_text
                assert str(resolved_inc_id) in md_text
                assert "rb-001-claims-processor-oom" in md_text
                assert "approver@aegisops.local" in md_text
                assert "<script>" not in md_text
                assert "999111222" not in md_text  # TOTP timecode/codes never leaked

                pdf_resp = await api.get(
                    f"/api/v1/incidents/{resolved_inc_id}/postmortem.pdf",
                    headers={"Authorization": f"Bearer {viewer_tok}"},
                )
                assert pdf_resp.status_code == 200, pdf_resp.text
                assert pdf_resp.headers["content-type"] == "application/pdf"
                pdf_bytes = pdf_resp.content
                assert pdf_bytes.startswith(b"%PDF-1.4")
                assert pdf_bytes.rstrip().endswith(b"%%EOF")
                assert b"/Count 2" in pdf_bytes or b"/Count 3" in pdf_bytes  # Multi-page rendered cleanly
                pdf_text = _extract_pdf_text(pdf_bytes)
                assert str(resolved_inc_id) in pdf_text
                assert "rb-001-claims-processor-oom" in pdf_text
                assert "Page 1 of " in pdf_text
                assert "Page 2 of " in pdf_text
                assert "999111222" not in pdf_text

                # Escalated incident postmortem uses Escalation Report title, never Verified Resolution
                esc_md = await api.get(
                    f"/api/v1/incidents/{esc_inc_id}/postmortem.md",
                    headers={"Authorization": f"Bearer {viewer_tok}"},
                )
                assert esc_md.status_code == 200
                assert "Escalation Report" in esc_md.text
                assert "Verified Resolution Postmortem" not in esc_md.text
            finally:
                # Re-tag & close synthetic test incidents cleanly so they never block subsequent tests or interactive queues
                async with app.state.session_factory() as session, session.begin():
                    await session.execute(
                        update(Incident)
                        .where(Incident.id == resolved_inc_id)
                        .values(source_provenance="automated_test")
                    )
                    await session.execute(
                        update(Incident)
                        .where(Incident.id == esc_inc_id)
                        .values(state="FAILED", source_provenance="automated_test")
                    )
