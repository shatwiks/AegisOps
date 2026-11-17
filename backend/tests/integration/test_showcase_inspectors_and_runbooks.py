"""Integration tests for Showcase Phase 04: Privacy Playground, Prompt Inspector, Runbook Upload/Search & Live K8s Topology."""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.config import get_settings
from app.main import create_app
from app.models.entities import Asset, Incident, Runbook
from app.seed.cmdb_seed import seed_cmdb
from app.seed.runbook_seed import seed_runbooks


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
async def test_privacy_playground_prompt_inspector_runbook_upload_search_and_live_topology() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    demo_pw = os.environ["KEYCLOAK_DEMO_USER_PASSWORD"]
    app = create_app(settings_override=settings)
    viewer_tok = await _fetch_token("viewer@aegisops.local", demo_pw, settings)
    op_tok = await _fetch_token("operator@aegisops.local", demo_pw, settings)

    custom_slug = f"rb-custom-showcase-{uuid.uuid4().hex[:8]}"
    captured_inc_id = uuid.uuid4()
    legacy_inc_id = uuid.uuid4()

    async with app.router.lifespan_context(app):
        async with app.state.session_factory() as session, session.begin():
            await seed_cmdb(session)
            await seed_runbooks(session, settings)
            elig = (
                await session.execute(select(Asset).where(Asset.slug == "eligibility-api"))
            ).scalar_one()

            session.add(
                Incident(
                    id=captured_inc_id,
                    dedup_key=f"p4-cap-{captured_inc_id}",
                    alert_fingerprint=f"fp-p4-cap-{captured_inc_id}",
                    alertname="High5xxErrorRate",
                    title="High5xxErrorRate on eligibility-api",
                    summary_sanitized="ERR_PG_POOL_TIMEOUT_57P03",
                    primary_asset_id=elig.id,
                    severity="P1",
                    severity_explanation_json={"downstream_impact_slugs": ["claims-processor"]},
                    state="RESOLVED",
                    proposed_playbook_id="stateless_deployment_restart",
                    proposed_parameters_json={"rollout_strategy": "RollingUpdate"},
                    source_provenance="automated_test",
                    sanitized_prompt_json={
                        "captured": True,
                        "model": settings.aegisops_chat_model,
                        "delimiters": ["<untrusted_telemetry>", "<retrieved_runbook_data>"],
                        "system_prompt": "You are AegisOps SRE Triage Analyst.",
                        "user_prompt": "<untrusted_telemetry>ERR_PG_POOL_TIMEOUT_57P03</untrusted_telemetry>",
                        "cited_context_slugs": ["rb-002-eligibility-db-pool-exhaustion"],
                        "validated_output": {"proposed_playbook_id": "stateless_deployment_restart"},
                    },
                )
            )
            session.add(
                Incident(
                    id=legacy_inc_id,
                    dedup_key=f"p4-leg-{legacy_inc_id}",
                    alert_fingerprint=f"fp-p4-leg-{legacy_inc_id}",
                    alertname="LegacyAlert",
                    title="LegacyAlert on eligibility-api",
                    summary_sanitized="Legacy summary",
                    primary_asset_id=elig.id,
                    severity="P3",
                    severity_explanation_json={},
                    state="RESOLVED",
                    source_provenance="automated_test",
                    sanitized_prompt_json=None,
                )
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as api:
            try:
                # 1. Privacy presets & playground preview (`visitor+`, zero persistence, 8 KiB + 30/min guards)
                presets_resp = await api.get("/api/v1/showcase/privacy/presets")
                assert presets_resp.status_code == 200
                presets = presets_resp.json()["fictional_presets"]
                assert len(presets) == 3

                sample_text = presets[0]["text"] + " Bearer tok_live_secret_xyz12345"
                prev_resp = await api.post(
                    "/api/v1/showcase/privacy/preview",
                    json={"text": sample_text},
                )
                assert prev_resp.status_code == 200, prev_resp.text
                pj = prev_resp.json()
                assert pj["persisted"] is False
                assert pj["total_redactions"] >= 5
                assert "[REDACTED:SSN]" in pj["sanitized_text"]
                assert "123-45-6789" not in pj["sanitized_text"]
                assert "tok_live_secret_xyz12345" not in pj["sanitized_text"]

                oversize = await api.post(
                    "/api/v1/showcase/privacy/preview",
                    json={"text": "x" * 9000},
                )
                assert oversize.status_code == 413

                # 2. Sanitized Prompt Inspector + 7-question "Why This Action?" card
                assert (await api.get(f"/api/v1/incidents/{captured_inc_id}/prompt")).status_code == 401
                cap_resp = await api.get(
                    f"/api/v1/incidents/{captured_inc_id}/prompt",
                    headers={"Authorization": f"Bearer {viewer_tok}"},
                )
                assert cap_resp.status_code == 200, cap_resp.text
                cap_j = cap_resp.json()
                assert cap_j["captured"] is True
                assert cap_j["prompt_record"]["delimiters"] == [
                    "<untrusted_telemetry>",
                    "<retrieved_runbook_data>",
                ]
                assert set(cap_j["why_this_action"]["questions"].keys()) == {
                    "what_failed",
                    "why_system_thinks_so",
                    "recommended_action",
                    "why_allowed_or_blocked",
                    "why_mfa_required",
                    "what_can_prevent_execution",
                    "what_happened_afterward",
                }

                leg_resp = await api.get(
                    f"/api/v1/incidents/{legacy_inc_id}/prompt",
                    headers={"Authorization": f"Bearer {viewer_tok}"},
                )
                assert leg_resp.status_code == 200
                assert leg_resp.json()["captured"] is False
                assert "not captured" in (leg_resp.json()["message"] or "").lower()

                # 3. Runbook browser + validated upload + security guards + hybrid search tester
                rb_list = await api.get("/api/v1/runbooks")
                assert rb_list.status_code == 200, rb_list.text
                assert rb_list.json()["counts"]["ready"] >= 18

                # Upload auth guard
                assert (
                    await api.post(
                        "/api/v1/runbooks/upload",
                        json={"filename": "test.md", "content": "---\nslug: abc\n---"},
                    )
                ).status_code == 401
                assert (
                    await api.post(
                        "/api/v1/runbooks/upload",
                        headers={"Authorization": f"Bearer {viewer_tok}"},
                        json={"filename": "test.md", "content": "---\nslug: abc\n---"},
                    )
                ).status_code == 403

                # Upload security rejections (XSS tag, unknown playbook, risk downgrade)
                xss_md = "---\nslug: bad-xss-rb\ntitle: Bad XSS\nservice_slug: eligibility-api\ndoc_type: RUNBOOK\nrisk_tier: HIGH\n---\n\n## Symptoms\n<script>alert(1)</script>\n"
                assert (
                    await api.post(
                        "/api/v1/runbooks/upload",
                        headers={"Authorization": f"Bearer {op_tok}"},
                        files={"file": ("bad-xss.md", xss_md.encode("utf-8"), "text/markdown")},
                    )
                ).status_code == 400

                unknown_pb_md = "---\nslug: bad-pb-rb\ntitle: Bad PB\nservice_slug: eligibility-api\ndoc_type: RUNBOOK\nrisk_tier: LOW\npermitted_playbook_id: arbitrary_shell_exec\n---\n\n## Symptoms\nTest body content here.\n"
                assert (
                    await api.post(
                        "/api/v1/runbooks/upload",
                        headers={"Authorization": f"Bearer {op_tok}"},
                        files={"file": ("bad-pb.md", unknown_pb_md.encode("utf-8"), "text/markdown")},
                    )
                ).status_code == 400

                downgrade_md = "---\nslug: bad-risk-rb\ntitle: Bad Risk\nservice_slug: claims-processor\ndoc_type: RUNBOOK\nrisk_tier: LOW\npermitted_playbook_id: memory_limit_increase_bounded\n---\n\n## Symptoms\nMemory exhaustion body.\n"
                assert (
                    await api.post(
                        "/api/v1/runbooks/upload",
                        headers={"Authorization": f"Bearer {op_tok}"},
                        files={"file": ("bad-risk.md", downgrade_md.encode("utf-8"), "text/markdown")},
                    )
                ).status_code == 400

                # Valid reference .md upload -> UPLOADED -> VALIDATING -> INDEXING -> READY
                valid_md = f"""---
slug: {custom_slug}
title: "Custom Showcase Escalation Runbook"
doc_type: RUNBOOK
service_slug: eligibility-api
risk_tier: HIGH
permitted_playbook_id: null
version: "1.0.0"
tags: ["showcase", "synthetic"]
applicability:
  services: ["eligibility-api"]
  alertnames: ["ShowcaseCustomAlert"]
evidence_requirements:
  - "ERR_CUSTOM_SHOWCASE_9001"
---

## Symptoms
Synthetic showcase custom test symptom `ERR_CUSTOM_SHOWCASE_9001` affecting eligibility-api.

## Expected Result
Escalate safely with verified reference knowledge.

## Verification Steps
Confirm `/healthz` returns 200.

## Escalation Guidance
Escalate to benefits-sre team.
"""
                up_resp = await api.post(
                    "/api/v1/runbooks/upload",
                    headers={"Authorization": f"Bearer {op_tok}"},
                    files={"file": (f"{custom_slug}.md", valid_md.encode("utf-8"), "text/markdown")},
                )
                assert up_resp.status_code == 201, up_resp.text
                up_j = up_resp.json()
                assert up_j["runbook"]["indexing_status"] == "READY"
                assert up_j["runbook"]["approval_mode"] == "escalation_only"
                assert up_j["lifecycle_trace"] == ["UPLOADED", "VALIDATING", "INDEXING", "READY"]

                # Hybrid search tester finds seeded + custom docs and explains 0.78 threshold cleanly
                search_resp = await api.post(
                    "/api/v1/runbooks/search",
                    json={"query": "ERR_PG_POOL_TIMEOUT_57P03", "service_slug": "eligibility-api", "top_k": 5},
                )
                assert search_resp.status_code == 200, search_resp.text
                sj = search_resp.json()
                assert sj["status"] == "ok"
                assert sj["explanation"]["rrf_k"] == 60
                assert sj["explanation"]["cosine_similarity_threshold"] == pytest.approx(0.78, rel=1e-3)
                assert any(h["slug"] == "rb-002-eligibility-db-pool-exhaustion" for h in sj["hits"])

                # 4. Live Kubernetes facts on CMDB Topology (`visitor+`)
                topo_resp = await api.get(f"/api/v1/topology?incident_id={captured_inc_id}")
                assert topo_resp.status_code == 200, topo_resp.text
                nodes = {n["slug"]: n for n in topo_resp.json()["nodes"]}
                elig_node = nodes["eligibility-api"]
                assert elig_node["k8s_live"]["available"] is True
                assert " ready / " in elig_node["k8s_live"]["replica_label"]
                assert elig_node["k8s_live"]["image"]
                assert nodes["member-portal-gateway"]["k8s_live"]["virtual_cmdb_node"] is True

                # Verify privacy preview 30 req/60s rate limit returns 429 cleanly
                got_429 = False
                for _ in range(32):
                    rl = await api.post(
                        "/api/v1/showcase/privacy/preview",
                        json={"text": "test SSN 123-45-6789"},
                    )
                    if rl.status_code == 429:
                        got_429 = True
                        break
                assert got_429, "Expected 429 after 30 privacy preview calls in 60s window"
            finally:
                # Clean up rate limit key & synthetic test records
                await app.state.redis.delete("aegisops:ratelimit:privacy:127.0.0.1")
                async with app.state.session_factory() as session, session.begin():
                    await session.execute(delete(Runbook).where(Runbook.slug == custom_slug))
                    await session.execute(
                        delete(Incident).where(Incident.id.in_([captured_inc_id, legacy_inc_id]))
                    )
