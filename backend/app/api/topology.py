"""CMDB topology graph, blast-radius query, and cached read-only Kubernetes live state endpoints."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from app.auth.oidc import AuthenticatedUser, optional_authenticate_request
from app.cmdb.graph import get_blast_radius
from app.k8s.executor import KubernetesExecutor
from app.models.entities import Asset, AssetDependency, ExecutionAttempt, Incident

router = APIRouter(prefix="/api/v1/topology", tags=["topology"])

_K8S_CACHE_TTL_SECONDS = 3.0
_k8s_live_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_k8s_cache_lock = asyncio.Lock()


async def _fetch_live_k8s_for_assets(
    assets: list[Asset],
    executor: KubernetesExecutor,
) -> dict[str, dict[str, Any]]:
    """Collect read-only Kubernetes Deployment snapshots with a 3-second TTL cache."""
    now_mono = time.monotonic()
    deployable = [a for a in assets if a.k8s_deployment_name]
    results: dict[str, dict[str, Any]] = {}
    to_fetch: list[Asset] = []

    async with _k8s_cache_lock:
        for asset in deployable:
            cached = _k8s_live_cache.get(asset.slug)
            if cached is not None and (now_mono - cached[0]) < _K8S_CACHE_TTL_SECONDS:
                results[asset.slug] = dict(cached[1])
            else:
                to_fetch.append(asset)

    if to_fetch:

        async def _probe_one(asset: Asset) -> tuple[str, dict[str, Any]]:
            dep_name = str(asset.k8s_deployment_name)
            try:
                snap = await executor.read_deployment_snapshot(
                    cluster=asset.cluster,
                    namespace=asset.namespace,
                    deployment_name=dep_name,
                )
                return asset.slug, {
                    "available": True,
                    "stale": False,
                    "virtual_cmdb_node": False,
                    "source": "kubernetes_api_live",
                    "observed_at": datetime.now(UTC).isoformat(),
                    "cluster": snap.cluster,
                    "namespace": snap.namespace,
                    "deployment": snap.deployment,
                    "container_name": snap.container_name,
                    "ready_replicas": snap.ready_replicas,
                    "desired_replicas": snap.replicas,
                    "available_replicas": snap.available_replicas,
                    "updated_replicas": snap.updated_replicas,
                    "replica_label": f"{snap.ready_replicas} ready / {snap.replicas} desired",
                    "image": snap.image,
                    "memory_limit": snap.memory_limit or "unset",
                    "rollout_status": snap.rollout_status,
                    "annotations": snap.annotations,
                }
            except Exception as exc:
                prev = _k8s_live_cache.get(asset.slug)
                if prev is not None:
                    stale_payload = dict(prev[1])
                    stale_payload["stale"] = True
                    stale_payload["stale_reason"] = f"Refresh failed ({type(exc).__name__}); showing prior snapshot."
                    return asset.slug, stale_payload
                return asset.slug, {
                    "available": False,
                    "stale": False,
                    "virtual_cmdb_node": False,
                    "source": "kubernetes_api_unavailable",
                    "observed_at": datetime.now(UTC).isoformat(),
                    "cluster": asset.cluster,
                    "namespace": asset.namespace,
                    "deployment": dep_name,
                    "replica_label": "Unavailable",
                    "rollout_status": "Unavailable",
                    "reason": f"Kubernetes read failed ({type(exc).__name__}).",
                }

        fetched = await asyncio.gather(*(_probe_one(a) for a in to_fetch))
        now_done = time.monotonic()
        async with _k8s_cache_lock:
            for slug, payload in fetched:
                results[slug] = payload
                if payload.get("available") and not payload.get("stale"):
                    _k8s_live_cache[slug] = (now_done, dict(payload))

    for asset in assets:
        if asset.slug not in results:
            results[asset.slug] = {
                "available": False,
                "stale": False,
                "virtual_cmdb_node": True,
                "source": "cmdb_logical_node",
                "replica_label": "Logical CMDB node (no K8s Deployment)",
                "rollout_status": "LogicalNode",
            }
    return results


@router.get("")
async def get_topology(
    request: Request,
    incident_id: uuid.UUID | None = Query(default=None),
    user: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Return CMDB nodes, directed edges (`source depends_on target`), active blast radius & live K8s facts (`visitor+`)."""
    settings = request.app.state.settings
    executor = KubernetesExecutor(settings)

    async with request.app.state.session_factory() as session:
        assets = (await session.execute(select(Asset).order_by(Asset.slug.asc()))).scalars().all()
        deps = (await session.execute(select(AssetDependency))).scalars().all()
        active_incidents = (
            (
                await session.execute(
                    select(Incident).where(
                        Incident.state.notin_(["RESOLVED", "FAILED"]),
                        Incident.source_provenance != "automated_test",
                    )
                )
            )
            .scalars()
            .all()
        )

        by_id = {a.id: a for a in assets}
        active_by_asset: dict[str, list[dict[str, str]]] = {}
        impacted_downstream: set[str] = set()

        for inc in active_incidents:
            if inc.primary_asset_id and inc.primary_asset_id in by_id:
                root = by_id[inc.primary_asset_id]
                active_by_asset.setdefault(root.slug, []).append(
                    {"id": str(inc.id), "severity": inc.severity, "state": inc.state}
                )
                blast = await get_blast_radius(session, root.slug)
                for n in blast.downstream_impacts:
                    impacted_downstream.add(n.slug)

        run_diffs: dict[str, dict[str, Any]] = {}
        if incident_id is not None:
            sel_inc = (
                await session.execute(select(Incident).where(Incident.id == incident_id))
            ).scalar_one_or_none()
            if sel_inc is not None and (user is not None or sel_inc.demo_run_id is not None):
                latest_exec = (
                    await session.execute(
                        select(ExecutionAttempt)
                        .where(ExecutionAttempt.incident_id == sel_inc.id)
                        .order_by(ExecutionAttempt.started_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if latest_exec is not None:
                    before = dict(latest_exec.before_state_sanitized_json or {})
                    after = dict(latest_exec.after_state_sanitized_json or {})
                    run_diffs[latest_exec.target_deployment] = {
                        "incident_id": str(sel_inc.id),
                        "playbook_id": latest_exec.playbook_id,
                        "status": latest_exec.status,
                        "before": {
                            "replicas": before.get("replicas"),
                            "ready_replicas": before.get("ready_replicas"),
                            "image": before.get("image"),
                            "memory_limit": before.get("memory_limit"),
                        },
                        "after": {
                            "replicas": after.get("replicas"),
                            "ready_replicas": after.get("ready_replicas"),
                            "image": after.get("image"),
                            "memory_limit": after.get("memory_limit"),
                            "rollout_status": after.get("rollout_status"),
                        },
                    }

    k8s_live_map = await _fetch_live_k8s_for_assets(list(assets), executor)

    return {
        "edge_semantics": "source depends_on target",
        "observed_at": datetime.now(UTC).isoformat(),
        "nodes": [
            {
                "id": str(a.id),
                "slug": a.slug,
                "name": a.name,
                "namespace": a.namespace,
                "cluster": a.cluster,
                "asset_type": a.asset_type,
                "criticality": a.criticality,
                "stateless_eligible": a.stateless_eligible,
                "owner_team": a.owner_team,
                "active_incidents": active_by_asset.get(a.slug, []),
                "downstream_impacted": a.slug in impacted_downstream,
                "k8s_live": k8s_live_map.get(a.slug, {}),
                "selected_run_diff": run_diffs.get(a.slug),
            }
            for a in assets
        ],
        "edges": [
            {
                "id": str(d.id),
                "source_slug": by_id[d.source_asset_id].slug,
                "target_slug": by_id[d.target_asset_id].slug,
                "dependency_type": d.dependency_type,
                "description": d.description,
            }
            for d in deps
            if d.source_asset_id in by_id and d.target_asset_id in by_id
        ],
    }


@router.get("/{asset_slug}/blast-radius")
async def get_asset_blast_radius(
    asset_slug: str,
    request: Request,
    _: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Return separated upstream dependencies and downstream consumers for an asset (`visitor+`)."""
    async with request.app.state.session_factory() as session:
        blast = await get_blast_radius(session, asset_slug)
        if blast.root_asset is None:
            raise HTTPException(status_code=404, detail=f"Asset '{asset_slug}' not found")
        return {
            "asset_slug": blast.root_asset.slug,
            "criticality": blast.root_asset.criticality,
            "upstream_dependencies": [
                {"slug": n.slug, "criticality": n.criticality, "hop": n.hop_distance}
                for n in blast.upstream_dependencies
            ],
            "downstream_impacts": [
                {"slug": n.slug, "criticality": n.criticality, "hop": n.hop_distance}
                for n in blast.downstream_impacts
            ],
            "truncated": blast.truncated,
            "cycle_detected": blast.cycle_detected,
        }
