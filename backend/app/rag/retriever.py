"""Hybrid PostgreSQL full-text search + pgvector cosine retrieval with Reciprocal Rank Fusion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.rag.embeddings import assert_index_model_consistency, embed_texts


@dataclass
class RetrievedDocument:
    """Runbook/postmortem search hit with separate lexical, vector, and RRF scores."""

    slug: str
    title: str
    doc_type: str
    service_slug: str
    risk_tier: str
    permitted_playbook_id: str | None
    applicability_json: dict[str, Any]
    preconditions_json: dict[str, Any]
    evidence_requirements_json: list[str]
    symptoms: str
    body_markdown: str
    vector_similarity: float
    lexical_score: float
    rrf_score: float
    vector_rank: int | None
    lexical_rank: int | None


async def hybrid_search_runbooks(
    session: AsyncSession,
    query_text: str,
    settings: Settings,
    *,
    top_k: int = 5,
    rrf_k: int = 60,
    query_vector_override: list[float] | None = None,
) -> list[RetrievedDocument]:
    """Retrieve relevant runbooks/postmortems using both FTS and pgvector cosine distance + RRF."""
    await assert_index_model_consistency(session, settings)

    if query_vector_override is not None:
        if len(query_vector_override) != settings.aegisops_embedding_dimensions:
            raise ValueError(
                f"Query vector dim {len(query_vector_override)} != {settings.aegisops_embedding_dimensions}"
            )
        query_vec = query_vector_override
    else:
        query_vec = (await embed_texts([query_text], settings))[0]

    vec_literal = "[" + ",".join(f"{x:.8f}" for x in query_vec) + "]"

    sql = text(
        """
        WITH vec_hits AS (
            SELECT
                id,
                (1.0 - (embedding <=> CAST(:qvec AS vector))) AS vector_similarity,
                ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:qvec AS vector) ASC) AS v_rank
            FROM runbooks
            WHERE indexing_status = 'READY'
              AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:qvec AS vector) ASC
            LIMIT :cand_limit
        ),
        lex_query AS (
            SELECT websearch_to_tsquery('english', :qtext) AS tsq
        ),
        lex_hits AS (
            SELECT
                r.id,
                ts_rank_cd(r.search_tsv, lq.tsq) AS lexical_score,
                ROW_NUMBER() OVER (ORDER BY ts_rank_cd(r.search_tsv, lq.tsq) DESC, r.slug ASC) AS l_rank
            FROM runbooks r, lex_query lq
            WHERE r.indexing_status = 'READY'
              AND r.embedding IS NOT NULL
              AND r.search_tsv @@ lq.tsq
            ORDER BY lexical_score DESC
            LIMIT :cand_limit
        ),
        combined AS (
            SELECT
                r.id,
                r.slug,
                r.title,
                r.doc_type,
                r.service_slug,
                r.risk_tier,
                r.permitted_playbook_id,
                r.applicability_json,
                r.preconditions_json,
                r.evidence_requirements_json,
                r.symptoms,
                r.body_markdown,
                COALESCE(vh.vector_similarity, 1.0 - (r.embedding <=> CAST(:qvec AS vector))) AS vector_similarity,
                COALESCE(lh.lexical_score, 0.0) AS lexical_score,
                vh.v_rank AS vector_rank,
                lh.l_rank AS lexical_rank,
                (
                    CASE WHEN vh.v_rank IS NOT NULL THEN 1.0 / (:rrf_k + vh.v_rank) ELSE 0.0 END
                    + CASE WHEN lh.l_rank IS NOT NULL THEN 1.0 / (:rrf_k + lh.l_rank) ELSE 0.0 END
                ) AS rrf_score
            FROM runbooks r
            LEFT JOIN vec_hits vh ON vh.id = r.id
            LEFT JOIN lex_hits lh ON lh.id = r.id
            WHERE vh.id IS NOT NULL OR lh.id IS NOT NULL
        )
        SELECT *
        FROM combined
        ORDER BY rrf_score DESC, vector_similarity DESC, slug ASC
        LIMIT :top_k
        """
    )

    rows = (
        (
            await session.execute(
                sql,
                {
                    "qvec": vec_literal,
                    "qtext": query_text,
                    "cand_limit": max(top_k * 3, 12),
                    "rrf_k": rrf_k,
                    "top_k": top_k,
                },
            )
        )
        .mappings()
        .all()
    )

    return [
        RetrievedDocument(
            slug=str(row["slug"]),
            title=str(row["title"]),
            doc_type=str(row["doc_type"]),
            service_slug=str(row["service_slug"]),
            risk_tier=str(row["risk_tier"]),
            permitted_playbook_id=(
                str(row["permitted_playbook_id"]) if row["permitted_playbook_id"] else None
            ),
            applicability_json=dict(row["applicability_json"] or {}),
            preconditions_json=dict(row["preconditions_json"] or {}),
            evidence_requirements_json=list(row["evidence_requirements_json"] or []),
            symptoms=str(row["symptoms"]),
            body_markdown=str(row["body_markdown"]),
            vector_similarity=float(row["vector_similarity"]),
            lexical_score=float(row["lexical_score"]),
            rrf_score=float(row["rrf_score"]),
            vector_rank=int(row["vector_rank"]) if row["vector_rank"] is not None else None,
            lexical_rank=int(row["lexical_rank"]) if row["lexical_rank"] is not None else None,
        )
        for row in rows
    ]
