"""Integration tests for CMDB topology seeding, cycle-safe recursive CTEs, and severity."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select

from app.cmdb.graph import compute_severity, get_blast_radius
from app.config import get_settings
from app.db import build_engine, build_session_factory
from app.models.entities import Asset, AssetDependency
from app.seed.cmdb_seed import seed_cmdb


@pytest.mark.asyncio
async def test_seed_idempotency_and_directed_blast_radius() -> None:
    settings = get_settings()
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    try:
        # Run seed twice to prove idempotency
        async with factory() as session:
            async with session.begin():
                first = await seed_cmdb(session)
        async with factory() as session:
            async with session.begin():
                second = await seed_cmdb(session)
        assert first == second

        async with factory() as session:
            # Verify edge direction separation for eligibility-api
            blast_elig = await get_blast_radius(session, "eligibility-api")
            assert blast_elig.root_asset is not None
            upstream_slugs = {n.slug for n in blast_elig.upstream_dependencies}
            downstream_slugs = {n.slug for n in blast_elig.downstream_impacts}
            assert upstream_slugs == {"postgres-claims-db", "redis-session-cache"}
            assert downstream_slugs == {
                "claims-processor",
                "member-portal-gateway",
                "pharmacy-prior-auth",
                "edi-837-ingest",
            }
            assert not blast_elig.cycle_detected
            assert not blast_elig.truncated

            # Diamond topology deduplication when postgres-claims-db fails
            blast_pg = await get_blast_radius(session, "postgres-claims-db")
            pg_downstream = [n.slug for n in blast_pg.downstream_impacts]
            # claims-processor is reachable both directly (1 hop) and via eligibility-api (2 hops);
            # must appear once with min hop_distance=1
            assert len(pg_downstream) == len(set(pg_downstream))
            claims_node = next(
                n for n in blast_pg.downstream_impacts if n.slug == "claims-processor"
            )
            assert claims_node.hop_distance == 1

            # Truncation guard
            truncated_blast = await get_blast_radius(session, "postgres-claims-db", max_nodes=2)
            assert len(truncated_blast.downstream_impacts) == 2
            assert truncated_blast.truncated is True

            # Severity P1-P4 verification across real CMDB assets
            sev_p1, expl_p1 = compute_severity(
                blast_elig.root_asset, blast_elig.downstream_impacts, "critical"
            )
            assert sev_p1 == "P1"
            assert expl_p1["unique_downstream_count"] == 4

            blast_claims = await get_blast_radius(session, "claims-processor")
            sev_p2, _ = compute_severity(
                blast_claims.root_asset, blast_claims.downstream_impacts, "warning"
            )
            assert sev_p2 == "P2"

            blast_prov = await get_blast_radius(session, "provider-directory")
            sev_p3, _ = compute_severity(
                blast_prov.root_asset, blast_prov.downstream_impacts, "warning"
            )
            assert sev_p3 == "P3"

            sev_p4, _ = compute_severity(
                Asset(
                    slug="batch-reporter",
                    name="batch-reporter",
                    namespace="test",
                    cluster="kind",
                    asset_type="WORKER",
                    criticality="TIER_4_LOW",
                    owner_team="ops",
                ),
                [],
                "info",
            )
            assert sev_p4 == "P4"

            sev_unk, expl_unk = compute_severity(
                None, [], "info", unknown_asset_identifier="mystery-svc"
            )
            assert sev_unk == "P2"
            assert expl_unk["policy_rule"] == "UNKNOWN_ASSET_SAFE_ESCALATION"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cycle_safe_traversal_and_duplicate_names_across_namespaces() -> None:
    settings = get_settings()
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    tag = uuid.uuid4().hex[:8]
    ns_a = f"test-cyc-a-{tag}"
    ns_b = f"test-cyc-b-{tag}"
    created_slugs = [f"dup-a-{tag}", f"dup-b-{tag}", f"cyc-1-{tag}", f"cyc-2-{tag}", f"cyc-3-{tag}"]

    try:
        async with factory() as session:
            async with session.begin():
                a1 = Asset(
                    slug=f"dup-a-{tag}",
                    name="shared-api",
                    namespace=ns_a,
                    cluster="cluster-1",
                    asset_type="SERVICE",
                    criticality="TIER_3_STANDARD",
                    owner_team="team-a",
                )
                a2 = Asset(
                    slug=f"dup-b-{tag}",
                    name="shared-api",
                    namespace=ns_b,
                    cluster="cluster-2",
                    asset_type="SERVICE",
                    criticality="TIER_3_STANDARD",
                    owner_team="team-b",
                )
                c1 = Asset(
                    slug=f"cyc-1-{tag}",
                    name="cyc-1",
                    namespace=ns_a,
                    cluster="cluster-1",
                    asset_type="SERVICE",
                    criticality="TIER_2_HIGH",
                    owner_team="team-a",
                )
                c2 = Asset(
                    slug=f"cyc-2-{tag}",
                    name="cyc-2",
                    namespace=ns_a,
                    cluster="cluster-1",
                    asset_type="SERVICE",
                    criticality="TIER_2_HIGH",
                    owner_team="team-a",
                )
                c3 = Asset(
                    slug=f"cyc-3-{tag}",
                    name="cyc-3",
                    namespace=ns_a,
                    cluster="cluster-1",
                    asset_type="SERVICE",
                    criticality="TIER_2_HIGH",
                    owner_team="team-a",
                )
                session.add_all([a1, a2, c1, c2, c3])
                await session.flush()

                session.add_all(
                    [
                        AssetDependency(
                            source_asset_id=c1.id,
                            target_asset_id=c2.id,
                            dependency_type="HTTP_SYNC",
                        ),
                        AssetDependency(
                            source_asset_id=c2.id,
                            target_asset_id=c3.id,
                            dependency_type="HTTP_SYNC",
                        ),
                        AssetDependency(
                            source_asset_id=c3.id,
                            target_asset_id=c1.id,
                            dependency_type="HTTP_SYNC",
                        ),
                    ]
                )

        async with factory() as session:
            blast = await get_blast_radius(session, f"cyc-1-{tag}")
            assert blast.cycle_detected is True
            assert {n.slug for n in blast.downstream_impacts} == {f"cyc-2-{tag}", f"cyc-3-{tag}"}
            # Verify distinct namespace/cluster assets co-exist without collision
            dups = (
                (await session.execute(select(Asset).where(Asset.name == "shared-api")))
                .scalars()
                .all()
            )
            assert len({(d.cluster, d.namespace) for d in dups}) >= 2
    finally:
        async with factory() as session:
            async with session.begin():
                await session.execute(delete(Asset).where(Asset.slug.in_(created_slugs)))
        await engine.dispose()
