"""Real kind-aegisops-local integration tests for K8s SDK remediation, RBAC, guards, and crash reconciliation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from kubernetes.client.rest import ApiException
from sqlalchemy import select

from app.config import get_settings
from app.db import build_engine, build_session_factory
from app.k8s.executor import (
    KubernetesExecutor,
    KubernetesGuardError,
    execute_remediation_attempt,
)
from app.models.entities import ApprovalRequest, Asset, ExecutionAttempt, Incident
from app.redis_client import build_redis_client
from app.seed.cmdb_seed import seed_cmdb
from app.worker.locks import RedisTargetLease


@pytest.mark.asyncio
async def test_k8s_guards_rbac_live_scale_and_crash_reconciliation() -> None:
    settings = get_settings()
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    redis_client = build_redis_client(settings)
    executor = KubernetesExecutor(settings, impersonate_remediator=True)

    inc_id = uuid.uuid4()
    lease = RedisTargetLease(
        redis_client, f"kind:prov:{uuid.uuid4().hex[:6]}", ttl_ms=30_000, owner_prefix="test"
    )
    try:
        async with factory() as session, session.begin():
            await seed_cmdb(session)
            prov = (
                await session.execute(select(Asset).where(Asset.slug == "provider-directory"))
            ).scalar_one()
            elig = (
                await session.execute(select(Asset).where(Asset.slug == "eligibility-api"))
            ).scalar_one()
            inc = Incident(
                id=inc_id,
                dedup_key=f"dedup-k8s-{inc_id}",
                alert_fingerprint=f"fp-k8s-{inc_id}",
                alertname="KindScaleTest",
                title="KindScaleTest",
                summary_sanitized="Live kind integration test",
                primary_asset_id=prov.id,
                severity="P3",
                severity_explanation_json={},
                state="REMEDIATING",
                source_provenance="automated_test",
            )
            session.add(inc)

        # 1. Disallowed context / namespace rejected
        with pytest.raises(KubernetesGuardError):
            executor.validate_target_boundary(cluster="prod-eks", namespace="aegisops-healthcare")
        with pytest.raises(KubernetesGuardError):
            executor.validate_target_boundary(
                cluster="kind-aegisops-local", namespace="kube-system"
            )
        with pytest.raises(KubernetesGuardError):
            executor.validate_target_boundary(
                cluster="kind-aegisops-local",
                namespace="aegisops-healthcare",
                labels={"app": "unmanaged"},
            )

        # 2. Terraform RBAC impersonation forbids patching outside healthcare namespace
        apps_api = executor._build_apps_api("kind-aegisops-local")
        with pytest.raises(ApiException) as api_exc:
            apps_api.list_namespaced_deployment(namespace="kube-system")
        assert api_exc.value.status == 403

        # 3. High-risk rollback rejected without ApprovalRequest
        assert await lease.acquire() is True
        with pytest.raises(KubernetesGuardError):
            await execute_remediation_attempt(
                factory,
                incident_id=inc_id,
                asset=elig,
                playbook_id="deployment_image_rollback",
                raw_parameters={},
                idempotency_key=f"no-appr-{inc_id}",
                lease=lease,
                executor=executor,
                approval=None,
            )

        # 4. Real live scale-out on kind-aegisops-local provider-directory (1 -> 2 replicas)
        snap_before = await executor.read_deployment_snapshot(
            cluster="kind-aegisops-local",
            namespace="aegisops-healthcare",
            deployment_name="provider-directory",
        )
        assert snap_before.replicas == 1

        idem_key = f"scale-live-{inc_id}"
        att = await execute_remediation_attempt(
            factory,
            incident_id=inc_id,
            asset=prov,
            playbook_id="replica_scale_out_bounded",
            raw_parameters={"target_replicas": 2},
            idempotency_key=idem_key,
            lease=lease,
            executor=executor,
            wait_rollout=True,
        )
        assert att.status == "SUCCEEDED"
        snap_after = await executor.read_deployment_snapshot(
            cluster="kind-aegisops-local",
            namespace="aegisops-healthcare",
            deployment_name="provider-directory",
        )
        assert snap_after.replicas == 2
        assert snap_after.ready_replicas == 2

        # 5. Simulate crashed MUTATING attempt with same target state -> reconciles without patching again!
        crash_key = f"crash-rec-{inc_id}"
        async with factory() as session, session.begin():
            session.add(
                ExecutionAttempt(
                    incident_id=inc_id,
                    idempotency_key=crash_key,
                    playbook_id="replica_scale_out_bounded",
                    playbook_version="1.0.0",
                    parameters_json={"target_replicas": 2},
                    target_cluster="kind-aegisops-local",
                    target_namespace="aegisops-healthcare",
                    target_deployment="provider-directory",
                    lock_token="crashed-worker",
                    status="MUTATING",
                    before_state_sanitized_json={"replicas": 1},
                )
            )
        spy_patch = AsyncMock(
            side_effect=AssertionError("Must not re-patch when K8s state already matches!")
        )
        orig_patch = executor._patch_deployment
        executor._patch_deployment = spy_patch  # type: ignore[method-assign]
        try:
            reconciled = await execute_remediation_attempt(
                factory,
                incident_id=inc_id,
                asset=prov,
                playbook_id="replica_scale_out_bounded",
                raw_parameters={"target_replicas": 2},
                idempotency_key=crash_key,
                lease=lease,
                executor=executor,
                wait_rollout=False,
            )
            assert reconciled.status == "RECONCILED_SUCCEEDED"
            assert spy_patch.await_count == 0
        finally:
            executor._patch_deployment = orig_patch  # type: ignore[method-assign]

        # 6. Target UID mismatch against ApprovalRequest fails safely
        bad_appr = ApprovalRequest(
            id=uuid.uuid4(),
            incident_id=inc_id,
            playbook_id="deployment_image_rollback",
            playbook_version="1.0.0",
            parameters_hash="x",
            parameters_json={"target_image": elig.known_good_image},
            target_asset_slug="eligibility-api",
            target_k8s_uid="wrong-uid-0000",
            target_resource_version="1",
            status="CONSUMED",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        async with factory() as session, session.begin():
            session.add(bad_appr)
        with pytest.raises(KubernetesGuardError):
            await execute_remediation_attempt(
                factory,
                incident_id=inc_id,
                asset=elig,
                playbook_id="deployment_image_rollback",
                raw_parameters={},
                idempotency_key=f"bad-uid-{inc_id}",
                lease=lease,
                executor=executor,
                approval=bad_appr,
            )

    finally:
        try:
            async with factory() as cleanup_session, cleanup_session.begin():
                leftover = await cleanup_session.get(Incident, inc_id)
                if leftover is not None and leftover.state not in {"RESOLVED", "FAILED"}:
                    leftover.state = "FAILED"
        except Exception:
            pass
        try:
            await executor._patch_deployment(
                cluster="kind-aegisops-local",
                namespace="aegisops-healthcare",
                deployment_name="provider-directory",
                patch_body={"spec": {"replicas": 1}},
            )
            await executor.wait_for_rollout(
                cluster="kind-aegisops-local",
                namespace="aegisops-healthcare",
                deployment_name="provider-directory",
            )
        except Exception:
            pass
        await lease.release()
        await redis_client.aclose()
        await engine.dispose()
