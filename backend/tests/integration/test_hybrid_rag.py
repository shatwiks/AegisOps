"""Integration tests for runbook seeding, lexical vs vector retrieval, and embedding consistency."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.db import build_engine, build_session_factory
from app.models.entities import Runbook
from app.rag.embeddings import EmbeddingConfigError, assert_index_model_consistency, embed_texts
from app.rag.retriever import hybrid_search_runbooks
from app.seed.runbook_seed import seed_runbooks


@pytest.mark.asyncio
async def test_runbook_seed_and_hybrid_lexical_advantage() -> None:
    settings = get_settings()
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            counts = await seed_runbooks(session, settings)
        assert counts["runbooks"] >= 15
        assert counts["postmortems"] >= 3

        async with factory() as session:
            total = (await session.execute(select(func.count(Runbook.id)))).scalar_one()
            assert total >= 18

            # Prove lexical FTS boosts exact error code match even if vector signal is uninformative (neutral unit vector)
            neutral_vec = [1.0 / (768**0.5)] * 768
            hits = await hybrid_search_runbooks(
                session,
                "ERR_PG_POOL_TIMEOUT_57P03",
                settings,
                top_k=3,
                query_vector_override=neutral_vec,
            )
            assert hits
            assert hits[0].slug == "rb-002-eligibility-db-pool-exhaustion"
            assert "pm-001-eligibility-pool-exhaustion-postmortem" in [h.slug for h in hits[:3]]
            assert hits[0].lexical_score > 0.0
            assert hits[0].lexical_rank in (1, 2)
            assert (hits[0].vector_rank or 99) > 5

            # Real Ollama query test
            real_hits = await hybrid_search_runbooks(
                session,
                "claims-processor container exited code 137 OOMKilled ERR_OOM_EXIT_137_CLAIMS_BATCH",
                settings,
                top_k=3,
            )
            top_slugs = [h.slug for h in real_hits]
            assert any(
                s in top_slugs
                for s in ("rb-001-claims-processor-oom", "pm-002-claims-batch-oom-postmortem")
            )
            assert real_hits[0].vector_similarity > 0.50

            # Dimension / model mismatch guard fails safely
            bad_settings = settings.model_copy(
                update={"aegisops_embedding_model": "other-embed-model:v9"}
            )
            with pytest.raises(EmbeddingConfigError):
                await assert_index_model_consistency(session, bad_settings)

            with pytest.raises(ValueError):
                await hybrid_search_runbooks(
                    session,
                    "test",
                    settings,
                    query_vector_override=[0.1, 0.2, 0.3],
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_live_ollama_embedding_dimensions() -> None:
    settings = get_settings()
    vecs = await embed_texts(["eligibility-api db pool timeout"], settings)
    assert len(vecs) == 1
    assert len(vecs[0]) == 768
