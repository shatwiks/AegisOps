"""Cycle-safe CMDB blast-radius traversal and deterministic P1-P4 severity policy."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Asset


@dataclass
class BlastRadiusNode:
    """Impacted or upstream asset discovered in graph traversal."""

    id: uuid.UUID
    slug: str
    name: str
    namespace: str
    cluster: str
    asset_type: str
    criticality: str
    hop_distance: int


@dataclass
class BlastRadiusResult:
    """Separated upstream dependencies and downstream impacted consumers."""

    root_asset: Asset | None
    upstream_dependencies: list[BlastRadiusNode]
    downstream_impacts: list[BlastRadiusNode]
    truncated: bool
    cycle_detected: bool


async def _traverse_direction(
    session: AsyncSession,
    root_id: uuid.UUID,
    *,
    direction: str,
    max_depth: int,
    max_nodes: int,
) -> tuple[list[BlastRadiusNode], bool, bool]:
    """Run cycle-safe PostgreSQL recursive CTE in one edge direction.

    Edge semantic: `source_asset_id -> target_asset_id` means `source depends_on target`.
    - `downstream`: reverse edge walk (`target = current -> source`), finding affected consumers.
    - `upstream`: forward edge walk (`source = current -> target`), finding upstream providers.
    """
    if direction == "downstream":
        join_clause = "ad.target_asset_id = t.node_id"
        next_col = "ad.source_asset_id"
    elif direction == "upstream":
        join_clause = "ad.source_asset_id = t.node_id"
        next_col = "ad.target_asset_id"
    else:
        raise ValueError(f"Unsupported direction: {direction}")

    query = text(
        f"""
        WITH RECURSIVE walk AS (
            SELECT
                {next_col} AS node_id,
                1 AS depth,
                ARRAY[:root_id, {next_col}] AS path,
                false AS hit_cycle
            FROM asset_dependencies ad
            WHERE {"ad.target_asset_id = :root_id" if direction == "downstream" else "ad.source_asset_id = :root_id"}
            UNION ALL
            SELECT
                {next_col} AS node_id,
                t.depth + 1 AS depth,
                t.path || {next_col},
                ({next_col} = ANY(t.path)) AS hit_cycle
            FROM asset_dependencies ad
            JOIN walk t ON {join_clause}
            WHERE t.depth < :max_depth
              AND NOT t.hit_cycle
              AND NOT ({next_col} = ANY(t.path))
        ),
        cycle_check AS (
            SELECT EXISTS (
                SELECT 1
                FROM asset_dependencies ad
                JOIN walk t ON {join_clause}
                WHERE {next_col} = ANY(t.path)
            ) AS has_cycle
        ),
        dedup AS (
            SELECT
                node_id,
                MIN(depth) AS min_depth
            FROM walk
            WHERE NOT hit_cycle AND node_id <> :root_id
            GROUP BY node_id
        ),
        total_count AS (
            SELECT COUNT(*) AS total_nodes FROM dedup
        )
        SELECT
            a.id,
            a.slug,
            a.name,
            a.namespace,
            a.cluster,
            a.asset_type,
            a.criticality,
            d.min_depth AS hop_distance,
            tc.total_nodes,
            cc.has_cycle
        FROM dedup d
        JOIN assets a ON a.id = d.node_id
        CROSS JOIN total_count tc
        CROSS JOIN cycle_check cc
        ORDER BY d.min_depth ASC, a.slug ASC
        LIMIT :max_nodes
        """
    )

    rows = (
        await session.execute(
            query,
            {
                "root_id": root_id,
                "max_depth": max_depth,
                "max_nodes": max_nodes,
            },
        )
    ).all()

    if not rows:
        # Still check if a direct 2-hop cycle back to root exists even if filtered
        cycle_sql = text(
            """
            WITH RECURSIVE walk AS (
                SELECT
                    source_asset_id AS node_id,
                    1 AS depth,
                    ARRAY[:root_id, source_asset_id] AS path
                FROM asset_dependencies
                WHERE target_asset_id = :root_id
                UNION ALL
                SELECT
                    ad.source_asset_id,
                    w.depth + 1,
                    w.path || ad.source_asset_id
                FROM asset_dependencies ad
                JOIN walk w ON ad.target_asset_id = w.node_id
                WHERE w.depth < :max_depth AND NOT (ad.source_asset_id = ANY(w.path))
            )
            SELECT EXISTS (
                SELECT 1 FROM asset_dependencies ad
                JOIN walk w ON ad.target_asset_id = w.node_id
                WHERE ad.source_asset_id = ANY(w.path)
            )
            """
        )
        has_cycle = bool(
            (
                await session.execute(cycle_sql, {"root_id": root_id, "max_depth": max_depth})
            ).scalar()
        )
        return [], False, has_cycle

    total_nodes = int(rows[0].total_nodes)
    has_cycle = bool(rows[0].has_cycle)
    nodes = [
        BlastRadiusNode(
            id=row.id,
            slug=row.slug,
            name=row.name,
            namespace=row.namespace,
            cluster=row.cluster,
            asset_type=row.asset_type,
            criticality=row.criticality,
            hop_distance=int(row.hop_distance),
        )
        for row in rows
    ]
    truncated = total_nodes > max_nodes
    return nodes, truncated, has_cycle


async def get_blast_radius(
    session: AsyncSession,
    asset_slug: str,
    *,
    max_depth: int = 6,
    max_nodes: int = 50,
) -> BlastRadiusResult:
    """Compute separated upstream causes and downstream consumers for an asset."""
    asset = (
        await session.execute(select(Asset).where(Asset.slug == asset_slug))
    ).scalar_one_or_none()
    if asset is None:
        return BlastRadiusResult(
            root_asset=None,
            upstream_dependencies=[],
            downstream_impacts=[],
            truncated=False,
            cycle_detected=False,
        )

    downstream, trunc_down, cyc_down = await _traverse_direction(
        session, asset.id, direction="downstream", max_depth=max_depth, max_nodes=max_nodes
    )
    upstream, trunc_up, cyc_up = await _traverse_direction(
        session, asset.id, direction="upstream", max_depth=max_depth, max_nodes=max_nodes
    )

    return BlastRadiusResult(
        root_asset=asset,
        upstream_dependencies=upstream,
        downstream_impacts=downstream,
        truncated=trunc_down or trunc_up,
        cycle_detected=cyc_down or cyc_up,
    )


def compute_severity(
    root_asset: Asset | None,
    downstream_impacts: list[BlastRadiusNode],
    alert_severity: str,
    *,
    unknown_asset_identifier: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Deterministic explainable P1-P4 severity policy from CMDB criticality + unique blast radius."""
    normalized_alert_sev = (alert_severity or "warning").strip().lower()
    unique_downstream_slugs = sorted({n.slug for n in downstream_impacts})
    tier1_or_2_downstream = [
        n.slug for n in downstream_impacts if n.criticality in ("TIER_1_CRITICAL", "TIER_2_HIGH")
    ]

    if root_asset is None:
        return (
            "P2",
            {
                "policy_rule": "UNKNOWN_ASSET_SAFE_ESCALATION",
                "unknown_asset": unknown_asset_identifier or "unspecified",
                "unique_downstream_count": 0,
                "reason": "Asset not found in CMDB; assigned P2 safety severity instead of P4 and flagged for operator triage.",
            },
        )

    crit = root_asset.criticality
    if crit == "TIER_1_CRITICAL" and (
        normalized_alert_sev == "critical"
        or len(tier1_or_2_downstream) >= 1
        or len(unique_downstream_slugs) >= 2
    ):
        sev = "P1"
        rule = "TIER_1_CRITICAL_WITH_HIGH_IMPACT"
        reason = (
            f"Root asset '{root_asset.slug}' is TIER_1_CRITICAL with {len(unique_downstream_slugs)} "
            f"unique downstream consumer(s) ({len(tier1_or_2_downstream)} Tier-1/2) and alert severity '{normalized_alert_sev}'."
        )
    elif (
        crit == "TIER_1_CRITICAL"
        or (
            crit == "TIER_2_HIGH"
            and (normalized_alert_sev == "critical" or len(unique_downstream_slugs) >= 1)
        )
        or len(unique_downstream_slugs) >= 3
    ):
        sev = "P2"
        rule = "HIGH_CRITICALITY_OR_MULTI_CONSUMER_BLAST"
        reason = (
            f"Root asset '{root_asset.slug}' ({crit}) affects {len(unique_downstream_slugs)} "
            f"unique downstream consumer(s) with alert severity '{normalized_alert_sev}'."
        )
    elif crit == "TIER_2_HIGH" or (
        crit == "TIER_3_STANDARD" and normalized_alert_sev in ("warning", "critical")
    ):
        sev = "P3"
        rule = "CONTAINED_SERVICE_DEGRADATION"
        reason = (
            f"Root asset '{root_asset.slug}' ({crit}) degraded with {len(unique_downstream_slugs)} "
            f"downstream consumer(s) and alert severity '{normalized_alert_sev}'."
        )
    else:
        sev = "P4"
        rule = "LOW_CRITICALITY_ISOLATED_ALERT"
        reason = (
            f"Root asset '{root_asset.slug}' ({crit}) has isolated blast radius "
            f"({len(unique_downstream_slugs)} consumers) and alert severity '{normalized_alert_sev}'."
        )

    return (
        sev,
        {
            "policy_rule": rule,
            "root_asset_slug": root_asset.slug,
            "root_criticality": crit,
            "alert_severity": normalized_alert_sev,
            "unique_downstream_count": len(unique_downstream_slugs),
            "downstream_slugs": unique_downstream_slugs,
            "reason": reason,
        },
    )
