"""Integration tests for Alertmanager webhook auth, scrubbing, dedup, outbox, and audit immutability."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError

from app.config import get_settings
from app.main import create_app
from app.models.entities import AuditRecord, Incident, IncidentEvent, OutboxJob
from app.seed.cmdb_seed import seed_cmdb


def _sign_body(secret: str, raw: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.mark.asyncio
async def test_webhook_auth_ssrf_scrubbing_dedup_and_append_only_audit() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    app = create_app(settings_override=settings)
    fp = f"fp-{uuid.uuid4().hex[:10]}"
    unk_fp = f"unk-{uuid.uuid4().hex[:10]}"

    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as session:
            async with session.begin():
                await seed_cmdb(session)

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Unauthenticated request rejected
            unauth = await client.post("/api/v1/webhooks/alertmanager", json={"alerts": []})
            assert unauth.status_code == 401

            # 2. SSRF log_source_url rejected
            ssrf_body = json.dumps(
                {
                    "alerts": [
                        {
                            "status": "firing",
                            "labels": {"alertname": "SSRF", "service": "eligibility-api"},
                            "annotations": {"log_source_url": "http://169.254.169.254/latest"},
                        }
                    ]
                }
            ).encode("utf-8")
            ssrf_resp = await client.post(
                "/api/v1/webhooks/alertmanager",
                content=ssrf_body,
                headers={
                    "Content-Type": "application/json",
                    "X-AegisOps-Signature": _sign_body(
                        settings.aegisops_webhook_hmac_secret, ssrf_body
                    ),
                },
            )
            assert ssrf_resp.status_code == 400

            # 3. Concurrent duplicate Alertmanager delivery with PHI/credentials
            sensitive_payload = {
                "receiver": "alertmanager",
                "status": "firing",
                "alerts": [
                    {
                        "status": "firing",
                        "fingerprint": fp,
                        "startsAt": datetime.now(UTC).isoformat(),
                        "labels": {
                            "alertname": "EligibilityDbPoolExhausted",
                            "severity": "critical",
                            "service": "eligibility-api",
                            "namespace": "aegisops-healthcare",
                            "cluster": "kind-aegisops-local",
                            "patient_name": "Jane Secret Doe",
                        },
                        "annotations": {
                            "summary": "DB timeout for MBR-77665544 SSN 123-45-6789 from 10.244.0.99",
                            "description": "ERR_PG_POOL_TIMEOUT_57P03 email=jane@phi.test Bearer secret_tok_99887766",
                        },
                    }
                ],
            }
            raw = json.dumps(sensitive_payload).encode("utf-8")
            sig = _sign_body(settings.aegisops_webhook_hmac_secret, raw)
            headers = {
                "Content-Type": "application/json",
                "X-AegisOps-Signature": sig,
                "X-AegisOps-Provenance": "automated_test",
            }

            responses = await asyncio.gather(
                *[
                    client.post("/api/v1/webhooks/alertmanager", content=raw, headers=headers)
                    for _ in range(5)
                ]
            )
            assert all(r.status_code == 202 for r in responses)
            actions = [r.json()["results"][0]["action"] for r in responses]
            assert actions.count("created") == 1
            assert actions.count("deduplicated") == 4

            # 4. Unknown asset produces safe tracked incident with P2 severity
            unk_payload = {
                "alerts": [
                    {
                        "status": "firing",
                        "fingerprint": unk_fp,
                        "labels": {
                            "alertname": "UnknownWorkerDown",
                            "severity": "info",
                            "service": "unregistered-cron-worker",
                            "namespace": "batch-ns",
                        },
                        "annotations": {"summary": "Unregistered worker unreachable"},
                    }
                ]
            }
            unk_raw = json.dumps(unk_payload).encode("utf-8")
            unk_resp = await client.post(
                "/api/v1/webhooks/alertmanager",
                content=unk_raw,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.aegisops_webhook_bearer_token}",
                    "X-AegisOps-Provenance": "automated_test",
                },
            )
            assert unk_resp.status_code == 202
            assert unk_resp.json()["results"][0]["severity"] == "P2"

        # 5. Inspect DB persistence: zero PHI leakage, exactly 1 incident & 1 outbox job, append-only triggers
        async with app.state.session_factory() as session:
            incs = (
                (await session.execute(select(Incident).where(Incident.alert_fingerprint == fp)))
                .scalars()
                .all()
            )
            assert len(incs) == 1
            inc = incs[0]
            assert inc.severity == "P1"
            assert inc.state == "OPEN"
            assert "123-45-6789" not in inc.summary_sanitized
            assert "MBR-77665544" not in inc.summary_sanitized
            assert "10.244.0.99" not in inc.summary_sanitized
            assert "jane@phi.test" not in inc.summary_sanitized
            assert "secret_tok_99887766" not in inc.summary_sanitized
            assert "ERR_PG_POOL_TIMEOUT_57P03" in inc.summary_sanitized

            jobs = (
                (await session.execute(select(OutboxJob).where(OutboxJob.incident_id == inc.id)))
                .scalars()
                .all()
            )
            assert len(jobs) == 1
            assert jobs[0].job_type == "TRIAGE_INCIDENT"
            assert "Jane Secret Doe" not in json.dumps(jobs[0].payload_sanitized_json)

            unk_inc = (
                await session.execute(select(Incident).where(Incident.alert_fingerprint == unk_fp))
            ).scalar_one()
            assert unk_inc.primary_asset_id is None
            assert unk_inc.unknown_asset_identifier == "batch-ns/unregistered-cron-worker"

            # Verify DELETE on audit_records raises DB error via append-only trigger
            inc_id = inc.id
            with pytest.raises(DBAPIError):
                await session.execute(delete(AuditRecord).where(AuditRecord.incident_id == inc_id))
            await session.rollback()

            with pytest.raises(DBAPIError):
                await session.execute(
                    delete(IncidentEvent).where(IncidentEvent.incident_id == inc_id)
                )
            await session.rollback()

        # Mark test-created outbox jobs completed and test incidents closed so dev worker queue stays clean
        async with app.state.session_factory() as session:
            async with session.begin():
                for test_fp in (fp, unk_fp):
                    inc_row = (
                        await session.execute(
                            select(Incident).where(Incident.alert_fingerprint == test_fp)
                        )
                    ).scalar_one_or_none()
                    if inc_row is not None:
                        inc_row.state = "FAILED"
                        inc_row.refusal_reason = "Test fixture closed after assertion"
                        job_rows = (
                            (
                                await session.execute(
                                    select(OutboxJob).where(OutboxJob.incident_id == inc_row.id)
                                )
                            )
                            .scalars()
                            .all()
                        )
                        for j in job_rows:
                            j.status = "COMPLETED"
        _ = text("SELECT 1")
