"""Idempotent CMDB asset & directed dependency seeder."""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import build_engine, build_session_factory
from app.models.entities import Asset, AssetDependency

CMDB_ASSETS: list[dict[str, Any]] = [
    {
        "slug": "member-portal-gateway",
        "name": "member-portal-gateway",
        "namespace": "aegisops-healthcare",
        "cluster": "kind-aegisops-local",
        "asset_type": "GATEWAY",
        "criticality": "TIER_1_CRITICAL",
        "owner_team": "platform-edge",
        "stateless_eligible": True,
        "known_good_image": None,
        "k8s_deployment_name": None,
        "metadata_json": {"synthetic": True, "tier_note": "External member portal entrypoint"},
    },
    {
        "slug": "eligibility-api",
        "name": "eligibility-api",
        "namespace": "aegisops-healthcare",
        "cluster": "kind-aegisops-local",
        "asset_type": "SERVICE",
        "criticality": "TIER_1_CRITICAL",
        "owner_team": "benefits-sre",
        "stateless_eligible": True,
        "known_good_image": "aegisops/eligibility-api:v1.0.0-good",
        "k8s_deployment_name": "eligibility-api",
        "metadata_json": {"synthetic": True, "port": 8081},
    },
    {
        "slug": "claims-processor",
        "name": "claims-processor",
        "namespace": "aegisops-healthcare",
        "cluster": "kind-aegisops-local",
        "asset_type": "SERVICE",
        "criticality": "TIER_2_HIGH",
        "owner_team": "claims-sre",
        "stateless_eligible": True,
        "known_good_image": "aegisops/claims-processor:v1.0.0-good",
        "k8s_deployment_name": "claims-processor",
        "metadata_json": {"synthetic": True, "port": 8082},
    },
    {
        "slug": "provider-directory",
        "name": "provider-directory",
        "namespace": "aegisops-healthcare",
        "cluster": "kind-aegisops-local",
        "asset_type": "SERVICE",
        "criticality": "TIER_3_STANDARD",
        "owner_team": "directory-sre",
        "stateless_eligible": True,
        "known_good_image": "aegisops/provider-directory:v1.0.0-good",
        "k8s_deployment_name": "provider-directory",
        "metadata_json": {"synthetic": True, "port": 8083},
    },
    {
        "slug": "pharmacy-prior-auth",
        "name": "pharmacy-prior-auth",
        "namespace": "aegisops-healthcare",
        "cluster": "kind-aegisops-local",
        "asset_type": "SERVICE",
        "criticality": "TIER_2_HIGH",
        "owner_team": "pharmacy-sre",
        "stateless_eligible": True,
        "known_good_image": None,
        "k8s_deployment_name": None,
        "metadata_json": {"synthetic": True, "virtual_cmdb_node": True},
    },
    {
        "slug": "edi-837-ingest",
        "name": "edi-837-ingest",
        "namespace": "aegisops-healthcare",
        "cluster": "kind-aegisops-local",
        "asset_type": "WORKER",
        "criticality": "TIER_3_STANDARD",
        "owner_team": "claims-sre",
        "stateless_eligible": False,
        "known_good_image": None,
        "k8s_deployment_name": None,
        "metadata_json": {"synthetic": True, "virtual_cmdb_node": True},
    },
    {
        "slug": "postgres-claims-db",
        "name": "postgres-claims-db",
        "namespace": "aegisops-healthcare",
        "cluster": "kind-aegisops-local",
        "asset_type": "DATABASE",
        "criticality": "TIER_1_CRITICAL",
        "owner_team": "data-platform",
        "stateless_eligible": False,
        "known_good_image": None,
        "k8s_deployment_name": "postgres-claims-db",
        "metadata_json": {"synthetic": True, "stateful": True, "db_failover_supported": False},
    },
    {
        "slug": "redis-session-cache",
        "name": "redis-session-cache",
        "namespace": "aegisops-healthcare",
        "cluster": "kind-aegisops-local",
        "asset_type": "CACHE",
        "criticality": "TIER_2_HIGH",
        "owner_team": "platform-cache",
        "stateless_eligible": False,
        "known_good_image": None,
        "k8s_deployment_name": "redis-session-cache",
        "metadata_json": {"synthetic": True, "stateful": True},
    },
]

# Directed edges: (source_slug, target_slug, dependency_type, description)
# Semantic: source depends_on target
CMDB_DEPENDENCIES: list[tuple[str, str, str, str]] = [
    (
        "member-portal-gateway",
        "eligibility-api",
        "HTTP_SYNC",
        "Portal checks member coverage eligibility synchronously",
    ),
    (
        "member-portal-gateway",
        "provider-directory",
        "HTTP_SYNC",
        "Portal queries in-network provider directory",
    ),
    (
        "claims-processor",
        "eligibility-api",
        "HTTP_SYNC",
        "Claims adjudication verifies active eligibility prior to payout",
    ),
    (
        "pharmacy-prior-auth",
        "eligibility-api",
        "HTTP_SYNC",
        "Prior auth validates member formulary & coverage tier",
    ),
    (
        "edi-837-ingest",
        "claims-processor",
        "ASYNC_QUEUE",
        "EDI 837 claim batches dispatch to claims processor",
    ),
    (
        "eligibility-api",
        "postgres-claims-db",
        "DATABASE",
        "Eligibility service reads benefit plan rules",
    ),
    (
        "eligibility-api",
        "redis-session-cache",
        "CACHE",
        "Eligibility service caches short-lived coverage lookups",
    ),
    (
        "claims-processor",
        "postgres-claims-db",
        "DATABASE",
        "Claims processor persists synthetic claim adjudications",
    ),
    (
        "provider-directory",
        "redis-session-cache",
        "CACHE",
        "Provider directory reads cached clinic search indexes",
    ),
]


async def seed_cmdb(session: AsyncSession) -> dict[str, int]:
    """Upsert all CMDB assets and directed dependencies idempotently."""
    for item in CMDB_ASSETS:
        stmt = (
            pg_insert(Asset)
            .values(**item)
            .on_conflict_do_update(
                index_elements=["slug"],
                set_={
                    "name": item["name"],
                    "namespace": item["namespace"],
                    "cluster": item["cluster"],
                    "asset_type": item["asset_type"],
                    "criticality": item["criticality"],
                    "owner_team": item["owner_team"],
                    "stateless_eligible": item["stateless_eligible"],
                    "known_good_image": item["known_good_image"],
                    "k8s_deployment_name": item["k8s_deployment_name"],
                    "metadata_json": item["metadata_json"],
                },
            )
        )
        await session.execute(stmt)

    assets_by_slug = {a.slug: a.id for a in (await session.execute(select(Asset))).scalars().all()}

    for src_slug, tgt_slug, dep_type, desc in CMDB_DEPENDENCIES:
        dep_stmt = (
            pg_insert(AssetDependency)
            .values(
                source_asset_id=assets_by_slug[src_slug],
                target_asset_id=assets_by_slug[tgt_slug],
                dependency_type=dep_type,
                description=desc,
            )
            .on_conflict_do_update(
                index_elements=["source_asset_id", "target_asset_id", "dependency_type"],
                set_={"description": desc},
            )
        )
        await session.execute(dep_stmt)

    return {"assets": len(CMDB_ASSETS), "dependencies": len(CMDB_DEPENDENCIES)}


async def _main() -> None:
    settings = get_settings()
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    try:
        async with factory() as session:
            async with session.begin():
                counts = await seed_cmdb(session)
        print(f"Seeded CMDB topology cleanly: {counts}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
