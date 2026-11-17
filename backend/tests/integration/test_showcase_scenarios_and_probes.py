"""Integration tests for Showcase Phase 03: 5-scenario Chaos Lab, conflicts, idempotency, probes & Scenario 5."""

from __future__ import annotations

import asyncio
import contextlib
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
from app.models.entities import BusinessProbeSample, DemoRun, Incident, OutboxJob
from app.seed.cmdb_seed import seed_cmdb
from app.seed.runbook_seed import seed_runbooks
from app.worker.runner import run_worker_once


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
async def test_business_probes_launch_conflicts_and_scenario5_pii_db_escalation() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    demo_pw = os.environ["KEYCLOAK_DEMO_USER_PASSWORD"]
    app = create_app(settings_override=settings)
    viewer_tok = await _fetch_token("viewer@aegisops.local", demo_pw, settings)
    op_tok = await _fetch_token("operator@aegisops.local", demo_pw, settings)

    # Wait briefly for restarted FastAPI daemon on 58000 if starting up
    async with httpx.AsyncClient(timeout=3.0) as hc:
        for _ in range(15):
            try:
                r = await hc.get(f"http://{settings.aegisops_api_host}:{settings.aegisops_api_port}/readyz")
                if r.status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)

    launched_run_id: str | None = None
    created_inc_id: str | None = None

    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as session, session.begin():
            await seed_cmdb(session)
            await seed_runbooks(session, settings)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as api:
            try:
                # 1. Catalog is publicly readable (Visitor Mode); all 5 scenarios present
                cat = await api.get("/api/v1/showcase/scenarios")
                assert cat.status_code == 200, cat.text
                sids = [s["scenario_id"] for s in cat.json()["scenarios"]]
                assert sids == [
                    "traffic_spike",
                    "db_pool_freeze",
                    "bad_canary_update",
                    "oom_memory_crash",
                    "pii_leak_and_db_failure",
                ]

                # 2. Allowlisted Business Transaction Probes (auth enforced; arbitrary target rejected)
                assert (
                    await api.post(
                        "/api/v1/showcase/probes/run",
                        json={"target_service": "eligibility-api"},
                    )
                ).status_code == 401
                assert (
                    await api.post(
                        "/api/v1/showcase/probes/run",
                        headers={"Authorization": f"Bearer {viewer_tok}"},
                        json={"target_service": "eligibility-api"},
                    )
                ).status_code == 403
                bad_probe = await api.post(
                    "/api/v1/showcase/probes/run",
                    headers={"Authorization": f"Bearer {op_tok}"},
                    json={"target_service": "http://169.254.169.254"},
                )
                assert bad_probe.status_code == 400

                p_elig = await api.post(
                    "/api/v1/showcase/probes/run",
                    headers={"Authorization": f"Bearer {op_tok}"},
                    json={"target_service": "eligibility-api"},
                )
                assert p_elig.status_code == 200, p_elig.text
                assert p_elig.json()["probe"]["status"] == "PASS"

                p_prov = await api.post(
                    "/api/v1/showcase/probes/run",
                    headers={"Authorization": f"Bearer {op_tok}"},
                    json={"target_service": "provider-directory"},
                )
                assert p_prov.status_code == 200
                assert p_prov.json()["probe"]["status"] in ("PASS", "DEGRADED")

                # 3. Scenario launch auth + idempotency + conflict exclusion + end-to-end Scenario 5
                assert (
                    await api.post(
                        "/api/v1/showcase/scenarios/pii_leak_and_db_failure/launch",
                        json={"idempotency_key": "unauth"},
                    )
                ).status_code == 401
                assert (
                    await api.post(
                        "/api/v1/showcase/scenarios/pii_leak_and_db_failure/launch",
                        headers={"Authorization": f"Bearer {viewer_tok}"},
                        json={"idempotency_key": "viewer"},
                    )
                ).status_code == 403

                idem = f"sc5-test-{uuid.uuid4().hex[:10]}"
                l1 = await api.post(
                    "/api/v1/showcase/scenarios/pii_leak_and_db_failure/launch",
                    headers={"Authorization": f"Bearer {op_tok}"},
                    json={"idempotency_key": idem},
                )
                assert l1.status_code == 202, l1.text
                assert l1.json()["deduplicated"] is False
                launched_run_id = l1.json()["demo_run"]["id"]

                # Same idempotency key deduplicates cleanly
                l2 = await api.post(
                    "/api/v1/showcase/scenarios/pii_leak_and_db_failure/launch",
                    headers={"Authorization": f"Bearer {op_tok}"},
                    json={"idempotency_key": idem},
                )
                assert l2.status_code == 200
                assert l2.json()["deduplicated"] is True
                assert l2.json()["demo_run"]["id"] == launched_run_id

                # Conflicting launch on postgres-claims-db or dependent eligibility-api blocked (409)
                conflict_resp = await api.post(
                    "/api/v1/showcase/scenarios/db_pool_freeze/launch",
                    headers={"Authorization": f"Bearer {op_tok}"},
                    json={"idempotency_key": f"conflict-{uuid.uuid4().hex[:8]}"},
                )
                assert conflict_resp.status_code == 409, conflict_resp.text

                # Process Scenario 5 + TRIAGE_INCIDENT concurrently using 2 worker coroutines
                executor = KubernetesExecutor(settings)

                async def _drain(worker_name: str, stop_ev: asyncio.Event) -> None:
                    while not stop_ev.is_set():
                        worked = await run_worker_once(
                            worker_id=worker_name,
                            session_factory=app.state.session_factory,
                            redis_client=app.state.redis,
                            settings=settings,
                            executor=executor,
                        )
                        if not worked:
                            await asyncio.sleep(0.5)

                stop_ev = asyncio.Event()
                w1 = asyncio.create_task(_drain("sc5-w1", stop_ev))
                w2 = asyncio.create_task(_drain("sc5-w2", stop_ev))
                try:
                    for _ in range(90):
                        r_detail = await api.get(f"/api/v1/showcase/runs/{launched_run_id}")
                        assert r_detail.status_code == 200
                        st = r_detail.json()["demo_run"]["status"]
                        if st in ("ESCALATED", "COMPLETED", "FAILED"):
                            break
                        await asyncio.sleep(1.0)
                finally:
                    stop_ev.set()
                    await asyncio.gather(w1, w2, return_exceptions=True)

                r_final = await api.get(
                    f"/api/v1/showcase/runs/{launched_run_id}",
                    headers={"Authorization": f"Bearer {viewer_tok}"},
                )
                assert r_final.status_code == 200
                final_data = r_final.json()
                assert final_data["demo_run"]["status"] == "ESCALATED"
                assert final_data["incident"] is not None
                created_inc_id = final_data["incident"]["id"]
                assert final_data["incident"]["state"] == "ESCALATED"
                assert final_data["incident"]["redaction_total"] >= 4

                # Verify raw fictional identifiers never persisted & DB fault probes recorded FAIL
                async with app.state.session_factory() as session:
                    inc_row = (
                        await session.execute(
                            select(Incident).where(Incident.id == uuid.UUID(created_inc_id))
                        )
                    ).scalar_one()
                    assert "123-45-6789" not in inc_row.summary_sanitized
                    assert "MBR-90001234" not in inc_row.summary_sanitized
                    assert "jane.fictional@example.invalid" not in inc_row.summary_sanitized
                    assert "eyJFictionalDemoToken999" not in inc_row.summary_sanitized
                    assert inc_row.sanitized_prompt_json is not None
                    assert inc_row.sanitized_prompt_json.get("captured") is True
                    assert inc_row.source_provenance == "interactive_demo"

                    run_probes = (
                        (
                            await session.execute(
                                select(BusinessProbeSample).where(
                                    BusinessProbeSample.demo_run_id == uuid.UUID(launched_run_id)
                                )
                            )
                        )
                        .scalars()
                        .all()
                    )
                    assert any(p.status == "FAIL" for p in run_probes)
            finally:
                # Restore clean baseline on postgres-claims-db and complete outbox jobs
                with contextlib.suppress(Exception):
                    await api.post(
                        "/api/v1/showcase/reset/execute",
                        headers={"Authorization": f"Bearer {op_tok}"},
                        json={"force_active_runs": True},
                    )
                if created_inc_id:
                    async with app.state.session_factory() as session, session.begin():
                        row = (
                            await session.execute(
                                select(Incident).where(Incident.id == uuid.UUID(created_inc_id))
                            )
                        ).scalar_one_or_none()
                        if row and row.state not in ("RESOLVED", "FAILED"):
                            row.state = "FAILED"
                if launched_run_id:
                    async with app.state.session_factory() as session, session.begin():
                        jobs = (
                            (
                                await session.execute(
                                    select(OutboxJob).where(
                                        OutboxJob.dedup_job_key == f"RUN_DEMO_SCENARIO:{launched_run_id}"
                                    )
                                )
                            )
                            .scalars()
                            .all()
                        )
                        for j in jobs:
                            j.status = "COMPLETED"
                            j.completed_at = datetime.now(UTC)
                        d_run = (
                            await session.execute(
                                select(DemoRun).where(DemoRun.id == uuid.UUID(launched_run_id))
                            )
                        ).scalar_one_or_none()
                        if d_run and d_run.status not in ("COMPLETED", "ESCALATED", "FAILED", "CANCELLED"):
                            d_run.status = "CANCELLED"
