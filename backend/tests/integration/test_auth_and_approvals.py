"""Integration tests against real Keycloak, PostgreSQL, and kind for OIDC, RBAC, TOTP, and approval races."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pyotp
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.config import get_settings
from app.main import create_app
from app.models.entities import ApprovalRequest, Asset, Incident, OutboxJob, UserTotpSecret
from app.seed.cmdb_seed import seed_cmdb


async def _fetch_keycloak_token(username: str, password: str, settings: object) -> dict[str, str]:
    token_url = settings.aegisops_oidc_token_url
    client_id = settings.aegisops_oidc_client_id
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": client_id,
                "username": username,
                "password": password,
                "scope": "openid profile email",
            },
        )
    assert resp.status_code == 200, f"Keycloak token failed for {username}: {resp.text}"
    return dict(resp.json())


@pytest.mark.asyncio
async def test_oidc_rbac_totp_replay_drift_and_concurrent_approval_race() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    demo_pw = os.environ["KEYCLOAK_DEMO_USER_PASSWORD"]
    app = create_app(settings_override=settings)

    viewer_tok = (await _fetch_keycloak_token("viewer@aegisops.local", demo_pw, settings))[
        "access_token"
    ]
    op_tok = (await _fetch_keycloak_token("operator@aegisops.local", demo_pw, settings))[
        "access_token"
    ]
    appr_tokens = await _fetch_keycloak_token("approver@aegisops.local", demo_pw, settings)
    appr_tok = appr_tokens["access_token"]
    appr_id_tok = appr_tokens["id_token"]

    inc_id = uuid.uuid4()
    drift_inc_id = uuid.uuid4()

    async with app.router.lifespan_context(app):
        # Validate distinct ID token verification vs access token
        id_claims = app.state.oidc_verifier.verify_id_token(appr_id_tok)
        assert id_claims["aud"] == settings.aegisops_oidc_client_id

        async with app.state.session_factory() as session, session.begin():
            await seed_cmdb(session)
            elig = (
                await session.execute(select(Asset).where(Asset.slug == "eligibility-api"))
            ).scalar_one()

            params = {"target_image": elig.known_good_image}
            params_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()

            for iid in (inc_id, drift_inc_id):
                session.add(
                    Incident(
                        id=iid,
                        dedup_key=f"auth-test-{iid}",
                        alert_fingerprint=f"fp-auth-{iid}",
                        alertname="High5xxErrorRate",
                        title="High5xxErrorRate on eligibility-api",
                        summary_sanitized="ERR_CANARY_IMG_SHA_BAD_9921",
                        primary_asset_id=elig.id,
                        severity="P1",
                        severity_explanation_json={},
                        state="AWAITING_APPROVAL",
                        proposed_playbook_id="deployment_image_rollback",
                        proposed_parameters_json=params,
                        source_provenance="automated_test",
                    )
                )
                await session.flush()

            # Read live K8s deployment UID & RV so inc_id binds accurately and drift_inc_id fails drift check
            from app.k8s.executor import KubernetesExecutor

            snap = await KubernetesExecutor(settings).read_deployment_snapshot(
                cluster="kind-aegisops-local",
                namespace="aegisops-healthcare",
                deployment_name="eligibility-api",
            )
            session.add(
                ApprovalRequest(
                    incident_id=inc_id,
                    playbook_id="deployment_image_rollback",
                    playbook_version="1.0.0",
                    parameters_hash=params_hash,
                    parameters_json=params,
                    target_asset_slug="eligibility-api",
                    target_k8s_uid=snap.uid,
                    target_resource_version=snap.resource_version,
                    status="PENDING",
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                )
            )
            session.add(
                ApprovalRequest(
                    incident_id=drift_inc_id,
                    playbook_id="deployment_image_rollback",
                    playbook_version="1.0.0",
                    parameters_hash=params_hash,
                    parameters_json=params,
                    target_asset_slug="eligibility-api",
                    target_k8s_uid=snap.uid,
                    target_resource_version="stale-rv-0",
                    status="PENDING",
                    expires_at=datetime.now(UTC) + timedelta(minutes=10),
                )
            )

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Unauthenticated access rejected
            assert (await client.get("/api/v1/incidents")).status_code == 401
            assert (await client.get("/api/v1/stream/incidents")).status_code == 401

            # 2. Viewer and Operator cannot enroll TOTP or approve (403 even if forged headers passed)
            for low_tok in (viewer_tok, op_tok):
                r_enroll = await client.post(
                    "/api/v1/auth/totp/enroll",
                    headers={"Authorization": f"Bearer {low_tok}", "X-SRE-Role": "approver"},
                )
                assert r_enroll.status_code == 403
                r_appr = await client.post(
                    f"/api/v1/incidents/{inc_id}/approve",
                    headers={"Authorization": f"Bearer {low_tok}", "X-SRE-Role": "approver"},
                    json={
                        "otp_code": "123456",
                        "expected_playbook_id": "deployment_image_rollback",
                        "expected_target_slug": "eligibility-api",
                    },
                )
                assert r_appr.status_code == 403

            # 3. Approver TOTP enrollment & verification (encrypted at rest)
            enroll_resp = await client.post(
                "/api/v1/auth/totp/enroll",
                headers={"Authorization": f"Bearer {appr_tok}"},
            )
            assert enroll_resp.status_code == 200
            uri = enroll_resp.json()["provisioning_uri"]
            assert uri.startswith("otpauth://totp/")

            # Extract secret from provisioning URI only to simulate authenticator app
            secret_b32 = pyotp.parse_uri(uri).secret
            # Ensure DB holds encrypted ciphertext, NOT plaintext secret
            async with app.state.session_factory() as session:
                me = (
                    await client.get(
                        "/api/v1/auth/me", headers={"Authorization": f"Bearer {appr_tok}"}
                    )
                ).json()
                totp_row = (
                    await session.execute(
                        select(UserTotpSecret).where(UserTotpSecret.user_sub == me["sub"])
                    )
                ).scalar_one()
                assert secret_b32 not in totp_row.encrypted_secret
                decrypted = (
                    Fernet(settings.aegisops_totp_encryption_key.encode())
                    .decrypt(totp_row.encrypted_secret.encode())
                    .decode()
                )
                assert decrypted == secret_b32

            totp = pyotp.TOTP(secret_b32)
            # First OTP activates enrollment and consumes current timecode
            code_0 = totp.at(datetime.now(UTC) - timedelta(seconds=30))
            ver_resp = await client.post(
                "/api/v1/auth/totp/verify-enrollment",
                headers={"Authorization": f"Bearer {appr_tok}"},
                json={"otp_code": code_0},
            )
            assert ver_resp.status_code == 200

            # Replaying the same code_0 must fail!
            replay_resp = await client.post(
                f"/api/v1/incidents/{inc_id}/approve",
                headers={"Authorization": f"Bearer {appr_tok}"},
                json={
                    "otp_code": code_0,
                    "expected_playbook_id": "deployment_image_rollback",
                    "expected_target_slug": "eligibility-api",
                },
            )
            assert replay_resp.status_code == 401

            # 4. Target resourceVersion drift invalidates approval & escalates
            code_now = totp.now()
            drift_resp = await client.post(
                f"/api/v1/incidents/{drift_inc_id}/approve",
                headers={"Authorization": f"Bearer {appr_tok}"},
                json={
                    "otp_code": code_now,
                    "expected_playbook_id": "deployment_image_rollback",
                    "expected_target_slug": "eligibility-api",
                },
            )
            assert drift_resp.status_code == 409

            # 5. Concurrent parallel approvals with fresh OTP schedule EXACTLY ONE execution
            code_fresh = totp.now()
            payload = {
                "otp_code": code_fresh,
                "expected_playbook_id": "deployment_image_rollback",
                "expected_target_slug": "eligibility-api",
                "expected_parameters_hash": params_hash,
            }
            race_resps = await asyncio.gather(
                *[
                    client.post(
                        f"/api/v1/incidents/{inc_id}/approve",
                        headers={"Authorization": f"Bearer {appr_tok}"},
                        json=payload,
                    )
                    for _ in range(5)
                ]
            )
            statuses = [r.status_code for r in race_resps]
            assert statuses.count(200) == 1
            assert all(s in (200, 401, 409) for s in statuses)

            async with app.state.session_factory() as session:
                jobs = (
                    (
                        await session.execute(
                            select(OutboxJob).where(
                                OutboxJob.incident_id == inc_id,
                                OutboxJob.job_type == "EXECUTE_REMEDIATION",
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                assert len(jobs) == 1

            # 6. Clean up synthetic test incidents so worker queue stays clean
            async with app.state.session_factory() as session, session.begin():
                for tid in (inc_id, drift_inc_id):
                    inc_obj = (
                        await session.execute(select(Incident).where(Incident.id == tid))
                    ).scalar_one()
                    inc_obj.state = "FAILED"
                    inc_obj.refusal_reason = "Auth test fixture closed"
                    for j in (
                        (
                            await session.execute(
                                select(OutboxJob).where(OutboxJob.incident_id == tid)
                            )
                        )
                        .scalars()
                        .all()
                    ):
                        j.status = "COMPLETED"
