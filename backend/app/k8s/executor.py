"""Official Kubernetes Python SDK executor with explicit allowlist, RBAC impersonation, and reconciliation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client.rest import ApiException
from sqlalchemy import select

from app.config import Settings
from app.models.entities import ApprovalRequest, Asset, AuditRecord, ExecutionAttempt
from app.playbooks.registry import PLAYBOOK_REGISTRY, validate_playbook_for_asset
from app.worker.locks import LeaseLostError, RedisTargetLease


class KubernetesGuardError(RuntimeError):
    """Raised when target context, namespace, ownership label, or resourceVersion fails policy."""


@dataclass
class TargetSnapshot:
    """Sanitized snapshot of live Kubernetes Deployment state."""

    cluster: str
    namespace: str
    deployment: str
    uid: str
    resource_version: str
    generation: int
    replicas: int
    ready_replicas: int
    available_replicas: int
    updated_replicas: int
    image: str
    memory_limit: str
    restarted_at: str | None
    labels: dict[str, str]
    container_name: str = ""
    annotations: dict[str, str] = field(default_factory=dict)
    observed_generation: int = 0
    total_replicas: int = 0

    @property
    def rollout_status(self) -> str:
        if self.replicas <= 0:
            return "ScaledToZero"
        if (
            self.observed_generation >= self.generation
            and self.ready_replicas >= self.replicas
            and self.available_replicas >= self.replicas
            and self.updated_replicas >= self.replicas
            and self.total_replicas <= self.replicas
        ):
            return "Healthy"
        if self.ready_replicas == 0:
            return "Degraded"
        return "Progressing"

    def to_sanitized_dict(self) -> dict[str, Any]:
        return {
            "cluster": self.cluster,
            "namespace": self.namespace,
            "deployment": self.deployment,
            "container_name": self.container_name,
            "uid": self.uid,
            "resource_version": self.resource_version,
            "generation": self.generation,
            "observed_generation": self.observed_generation,
            "replicas": self.replicas,
            "total_replicas": self.total_replicas,
            "ready_replicas": self.ready_replicas,
            "available_replicas": self.available_replicas,
            "updated_replicas": self.updated_replicas,
            "image": self.image,
            "memory_limit": self.memory_limit,
            "rollout_status": self.rollout_status,
            "restarted_at": self.restarted_at,
        }


class KubernetesExecutor:
    """Executes allowlisted Kubernetes patches strictly off the async event loop."""

    def __init__(self, settings: Settings, *, impersonate_remediator: bool = True) -> None:
        self.settings = settings
        self.impersonate_remediator = impersonate_remediator

    def validate_target_boundary(
        self, *, cluster: str, namespace: str, labels: dict[str, str] | None = None
    ) -> None:
        if cluster not in self.settings.aegisops_k8s_allowed_contexts:
            raise KubernetesGuardError(
                f"Cluster context '{cluster}' is outside allowed contexts {self.settings.aegisops_k8s_allowed_contexts}"
            )
        if namespace not in self.settings.aegisops_k8s_allowed_namespaces:
            raise KubernetesGuardError(
                f"Namespace '{namespace}' is outside allowed namespaces {self.settings.aegisops_k8s_allowed_namespaces}"
            )
        if labels is not None and labels.get("aegisops.io/managed") != "true":
            raise KubernetesGuardError(
                "Target Deployment lacks required ownership label 'aegisops.io/managed=true'"
            )

    def _build_apps_api(self, cluster_context: str) -> k8s_client.AppsV1Api:
        self.validate_target_boundary(
            cluster=cluster_context, namespace=self.settings.aegisops_k8s_allowed_namespaces[0]
        )
        api_client = k8s_config.new_client_from_config(context=cluster_context)
        if self.impersonate_remediator:
            api_client.default_headers["Impersonate-User"] = (
                "system:serviceaccount:aegisops-healthcare:aegisops-remediator"
            )
        return k8s_client.AppsV1Api(api_client)

    async def read_deployment_snapshot(
        self, *, cluster: str, namespace: str, deployment_name: str
    ) -> TargetSnapshot:
        """Read live Deployment state synchronously via asyncio.to_thread."""
        self.validate_target_boundary(cluster=cluster, namespace=namespace)

        def _read() -> Any:
            apps = self._build_apps_api(cluster)
            return apps.read_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                _request_timeout=(5, 15),
            )

        dep = await asyncio.to_thread(_read)
        meta = dep.metadata
        spec = dep.spec
        status = dep.status
        labels = dict(meta.labels or {})
        self.validate_target_boundary(cluster=cluster, namespace=namespace, labels=labels)

        containers = spec.template.spec.containers or []
        c0 = containers[0] if containers else None
        mem_limit = ""
        if c0 and c0.resources and c0.resources.limits:
            mem_limit = str(c0.resources.limits.get("memory", ""))

        ann = dict((spec.template.metadata.annotations if spec.template.metadata else None) or {})
        return TargetSnapshot(
            cluster=cluster,
            namespace=namespace,
            deployment=deployment_name,
            uid=str(meta.uid or ""),
            resource_version=str(meta.resource_version or ""),
            generation=int(meta.generation or 0),
            observed_generation=int(status.observed_generation or 0),
            replicas=int(spec.replicas or 0),
            total_replicas=int(status.replicas or 0),
            ready_replicas=int(status.ready_replicas or 0),
            available_replicas=int(status.available_replicas or 0),
            updated_replicas=int(status.updated_replicas or 0),
            image=str(c0.image if c0 else ""),
            memory_limit=mem_limit,
            container_name=str(c0.name if c0 else deployment_name),
            annotations={
                str(k): str(v)
                for k, v in (meta.annotations or {}).items()
                if str(k).startswith("aegisops.io/")
            },
            restarted_at=ann.get("aegisops.io/restartedAt")
            or ann.get("kubectl.kubernetes.io/restartedAt"),
            labels=labels,
        )

    def _matches_desired_state(
        self,
        snapshot: TargetSnapshot,
        playbook_id: str,
        params: dict[str, Any],
        attempt_marker: str,
    ) -> bool:
        if playbook_id == "replica_scale_out_bounded":
            return snapshot.replicas == int(params["target_replicas"])
        if playbook_id == "memory_limit_increase_bounded":
            return snapshot.memory_limit == f"{int(params['memory_mi'])}Mi"
        if playbook_id == "deployment_image_rollback":
            return snapshot.image == str(params["target_image"])
        if playbook_id == "stateless_deployment_restart":
            return snapshot.restarted_at == attempt_marker
        return False

    async def _patch_deployment(
        self,
        *,
        cluster: str,
        namespace: str,
        deployment_name: str,
        patch_body: dict[str, Any],
    ) -> TargetSnapshot:
        def _patch() -> Any:
            apps = self._build_apps_api(cluster)
            return apps.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=patch_body,
                _request_timeout=(5, 15),
            )

        dep = await asyncio.to_thread(_patch)
        meta = dep.metadata
        spec = dep.spec
        status = dep.status
        containers = spec.template.spec.containers or []
        c0 = containers[0] if containers else None
        mem_limit = ""
        if c0 and c0.resources and c0.resources.limits:
            mem_limit = str(c0.resources.limits.get("memory", ""))
        ann = dict((spec.template.metadata.annotations if spec.template.metadata else None) or {})
        return TargetSnapshot(
            cluster=cluster,
            namespace=namespace,
            deployment=deployment_name,
            uid=str(meta.uid or ""),
            resource_version=str(meta.resource_version or ""),
            generation=int(meta.generation or 0),
            observed_generation=int(status.observed_generation or 0),
            replicas=int(spec.replicas or 0),
            total_replicas=int(status.replicas or 0),
            ready_replicas=int(status.ready_replicas or 0),
            available_replicas=int(status.available_replicas or 0),
            updated_replicas=int(status.updated_replicas or 0),
            image=str(c0.image if c0 else ""),
            memory_limit=mem_limit,
            container_name=str(c0.name if c0 else deployment_name),
            annotations={
                str(k): str(v)
                for k, v in (meta.annotations or {}).items()
                if str(k).startswith("aegisops.io/")
            },
            restarted_at=ann.get("aegisops.io/restartedAt")
            or ann.get("kubectl.kubernetes.io/restartedAt"),
            labels=dict(meta.labels or {}),
        )

    async def patch_demo_workload(
        self,
        *,
        cluster: str,
        namespace: str,
        deployment_name: str,
        patch_body: dict[str, Any],
        wait_rollout: bool = True,
        timeout_seconds: int = 90,
    ) -> TargetSnapshot:
        """Apply an allowlisted baseline or demo fault patch strictly to demo workloads."""
        allowed_demo_deployments = {
            "eligibility-api",
            "claims-processor",
            "provider-directory",
            "postgres-claims-db",
        }
        if deployment_name not in allowed_demo_deployments:
            raise KubernetesGuardError(
                f"Deployment '{deployment_name}' is outside allowlisted demo workloads"
            )
        self.validate_target_boundary(cluster=cluster, namespace=namespace)
        # Re-read first to validate ownership label before patching
        await self.read_deployment_snapshot(
            cluster=cluster, namespace=namespace, deployment_name=deployment_name
        )
        snap = await self._patch_deployment(
            cluster=cluster,
            namespace=namespace,
            deployment_name=deployment_name,
            patch_body=patch_body,
        )
        if wait_rollout:
            snap = await self.wait_for_rollout(
                cluster=cluster,
                namespace=namespace,
                deployment_name=deployment_name,
                timeout_seconds=timeout_seconds,
            )
        return snap

    async def wait_for_rollout(
        self,
        *,
        cluster: str,
        namespace: str,
        deployment_name: str,
        timeout_seconds: int = 90,
    ) -> TargetSnapshot:
        """Poll Deployment status until observed_generation >= generation and replicas stabilize."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        last_snap = await self.read_deployment_snapshot(
            cluster=cluster, namespace=namespace, deployment_name=deployment_name
        )
        while loop.time() < deadline:
            if (
                last_snap.replicas > 0
                and last_snap.observed_generation >= last_snap.generation
                and last_snap.updated_replicas >= last_snap.replicas
                and last_snap.total_replicas <= last_snap.replicas
                and last_snap.available_replicas >= last_snap.replicas
                and last_snap.ready_replicas >= last_snap.replicas
            ):
                return last_snap
            await asyncio.sleep(2.0)
            last_snap = await self.read_deployment_snapshot(
                cluster=cluster, namespace=namespace, deployment_name=deployment_name
            )
        raise TimeoutError(
            f"Rollout did not stabilize within {timeout_seconds}s for {namespace}/{deployment_name}"
        )


async def execute_remediation_attempt(
    session_factory: Any,
    *,
    incident_id: Any,
    asset: Asset,
    playbook_id: str,
    raw_parameters: dict[str, Any],
    idempotency_key: str,
    lease: RedisTargetLease,
    executor: KubernetesExecutor,
    approval: ApprovalRequest | None = None,
    actor_sub: str = "system:outbox-worker",
    actor_role: str = "worker",
    wait_rollout: bool = True,
) -> ExecutionAttempt:
    """Execute or reconcile a deterministic Kubernetes mutation under Redis lease & DB ledger."""
    valid, params, err = validate_playbook_for_asset(playbook_id, asset, raw_parameters)
    if not valid:
        raise KubernetesGuardError(err or "Playbook validation failed")

    spec = PLAYBOOK_REGISTRY[playbook_id]
    if spec.risk_tier == "HIGH" and approval is None:
        raise KubernetesGuardError(
            f"HIGH risk playbook '{playbook_id}' cannot execute without consumed ApprovalRequest"
        )

    deployment_name = asset.k8s_deployment_name or asset.name

    # Check if an ExecutionAttempt already exists for idempotency_key (crash/timeout recovery path)
    async with session_factory() as session, session.begin():
        existing = (
            await session.execute(
                select(ExecutionAttempt)
                .where(ExecutionAttempt.idempotency_key == idempotency_key)
                .with_for_update()
            )
        ).scalar_one_or_none()

        if existing is not None:
            if existing.status in ("SUCCEEDED", "RECONCILED_SUCCEEDED"):
                return existing
            attempt_id = existing.id
            attempt_marker = f"aegisops-{attempt_id}"
        else:
            attempt = ExecutionAttempt(
                incident_id=incident_id,
                approval_id=approval.id if approval else None,
                idempotency_key=idempotency_key,
                playbook_id=playbook_id,
                playbook_version=spec.version,
                parameters_json=params,
                target_cluster=asset.cluster,
                target_namespace=asset.namespace,
                target_deployment=deployment_name,
                lock_token=lease.token,
                status="CLAIMED",
                before_state_sanitized_json={},
            )
            session.add(attempt)
            await session.flush()
            attempt_id = attempt.id
            attempt_marker = f"aegisops-{attempt_id}"

    # Read pre-mutation K8s state & check optimistic target binding
    await lease.assert_owned()
    before_snap = await executor.read_deployment_snapshot(
        cluster=asset.cluster,
        namespace=asset.namespace,
        deployment_name=deployment_name,
    )

    if (
        approval is not None
        and approval.target_k8s_uid
        and before_snap.uid != approval.target_k8s_uid
    ):
        raise KubernetesGuardError(
            f"Target UID drift detected ({before_snap.uid} != {approval.target_k8s_uid}); invalidating execution"
        )

    # Reconciliation check: if previous crashed worker already applied the mutation, do not re-apply!
    async with session_factory() as session, session.begin():
        att = (
            await session.execute(
                select(ExecutionAttempt).where(ExecutionAttempt.id == attempt_id).with_for_update()
            )
        ).scalar_one()

        if att.status in ("MUTATING", "ROLLOUT_WAITING") and executor._matches_desired_state(
            before_snap, playbook_id, params, attempt_marker
        ):
            att.status = "RECONCILED_SUCCEEDED"
            att.after_state_sanitized_json = before_snap.to_sanitized_dict()
            att.completed_at = datetime.now(UTC)
            session.add(
                AuditRecord(
                    incident_id=incident_id,
                    execution_id=att.id,
                    actor_sub=actor_sub,
                    actor_role=actor_role,
                    action_type="REMEDIATION_RECONCILED",
                    policy_decision="RECONCILED_SUCCEEDED",
                    before_state_json=att.before_state_sanitized_json,
                    after_state_json=att.after_state_sanitized_json,
                    details_json={"idempotency_key": idempotency_key},
                )
            )
            return att

        # Persist pre-mutation state & transition to MUTATING before touching K8s
        att.before_state_sanitized_json = before_snap.to_sanitized_dict()
        att.status = "MUTATING"
        att.lock_token = lease.token

    # Build deterministic strategic merge patch
    if playbook_id == "replica_scale_out_bounded":
        patch_body: dict[str, Any] = {"spec": {"replicas": int(params["target_replicas"])}}
    elif playbook_id == "stateless_deployment_restart":
        patch_body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": attempt_marker,
                            "aegisops.io/restartedAt": attempt_marker,
                        }
                    }
                }
            }
        }
    elif playbook_id == "memory_limit_increase_bounded":
        mem_mi = int(params["memory_mi"])
        patch_body = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": deployment_name,
                                "resources": {
                                    "limits": {"memory": f"{mem_mi}Mi"},
                                    "requests": {"memory": f"{min(128, mem_mi)}Mi"},
                                },
                            }
                        ]
                    }
                }
            }
        }
    elif playbook_id == "deployment_image_rollback":
        patch_body = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": deployment_name,
                                "image": str(params["target_image"]),
                            }
                        ]
                    }
                }
            }
        }
    else:
        raise KubernetesGuardError(f"Playbook '{playbook_id}' is not a Deployment patch playbook")

    try:
        # Enforce Redis lease right before mutating K8s
        await lease.assert_owned()
        after_patch_snap = await executor._patch_deployment(
            cluster=asset.cluster,
            namespace=asset.namespace,
            deployment_name=deployment_name,
            patch_body=patch_body,
        )

        async with session_factory() as session, session.begin():
            att = (
                await session.execute(
                    select(ExecutionAttempt)
                    .where(ExecutionAttempt.id == attempt_id)
                    .with_for_update()
                )
            ).scalar_one()
            att.status = "ROLLOUT_WAITING"
            att.k8s_response_sanitized_json = after_patch_snap.to_sanitized_dict()

        if wait_rollout:
            await lease.assert_owned()
            final_snap = await executor.wait_for_rollout(
                cluster=asset.cluster,
                namespace=asset.namespace,
                deployment_name=deployment_name,
                timeout_seconds=spec.timeout_seconds,
            )
        else:
            final_snap = after_patch_snap

        async with session_factory() as session, session.begin():
            att = (
                await session.execute(
                    select(ExecutionAttempt)
                    .where(ExecutionAttempt.id == attempt_id)
                    .with_for_update()
                )
            ).scalar_one()
            att.status = "SUCCEEDED"
            att.after_state_sanitized_json = final_snap.to_sanitized_dict()
            att.completed_at = datetime.now(UTC)
            session.add(
                AuditRecord(
                    incident_id=incident_id,
                    execution_id=att.id,
                    actor_sub=actor_sub,
                    actor_role=actor_role,
                    action_type="REMEDIATION_EXECUTED",
                    policy_decision="SUCCEEDED",
                    before_state_json=att.before_state_sanitized_json,
                    after_state_json=att.after_state_sanitized_json,
                    details_json={
                        "playbook_id": playbook_id,
                        "parameters": params,
                        "lock_token": lease.token,
                    },
                )
            )
            return att

    except LeaseLostError as exc:
        async with session_factory() as session, session.begin():
            att = (
                await session.execute(
                    select(ExecutionAttempt)
                    .where(ExecutionAttempt.id == attempt_id)
                    .with_for_update()
                )
            ).scalar_one()
            att.status = "ABORTED_LEASE_LOST"
            att.error_message_sanitized = str(exc)
            att.completed_at = datetime.now(UTC)
        raise

    except (ApiException, TimeoutError, Exception) as exc:
        async with session_factory() as session, session.begin():
            att = (
                await session.execute(
                    select(ExecutionAttempt)
                    .where(ExecutionAttempt.id == attempt_id)
                    .with_for_update()
                )
            ).scalar_one()
            att.status = "FAILED"
            att.error_message_sanitized = f"{type(exc).__name__}: {str(exc)[:300]}"
            att.completed_at = datetime.now(UTC)
        raise
