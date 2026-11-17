"""Local Ollama embedding client with strict dimension and model/digest validation."""

from __future__ import annotations

import asyncio

import ollama
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.entities import Runbook


class EmbeddingConfigError(RuntimeError):
    """Raised when Ollama embedding dimensions or active model digest mismatches DB schema."""


async def embed_texts(
    texts: list[str],
    settings: Settings,
    *,
    client_override: ollama.Client | None = None,
) -> list[list[float]]:
    """Embed texts via Ollama `/api/embed`, validating vector dimensions match settings (768)."""
    if not texts:
        return []

    def _call() -> ollama.EmbedResponse:
        client = client_override or ollama.Client(
            host=settings.aegisops_ollama_base_url,
            timeout=settings.aegisops_ollama_timeout_seconds,
        )
        return client.embed(
            model=settings.aegisops_embedding_model,
            input=texts,
            truncate=True,
        )

    response = await asyncio.to_thread(_call)
    vectors = [list(map(float, vec)) for vec in response.embeddings]

    if len(vectors) != len(texts):
        raise EmbeddingConfigError(
            f"Expected {len(texts)} embeddings from {settings.aegisops_embedding_model}, got {len(vectors)}"
        )
    for idx, vec in enumerate(vectors):
        if len(vec) != settings.aegisops_embedding_dimensions:
            raise EmbeddingConfigError(
                f"Embedding dimension mismatch at index {idx}: model '{settings.aegisops_embedding_model}' "
                f"returned {len(vec)} dims, expected {settings.aegisops_embedding_dimensions}"
            )
    return vectors


async def assert_index_model_consistency(session: AsyncSession, settings: Settings) -> None:
    """Fail safely if seeded runbook embeddings came from a different model or digest."""
    rows = (
        await session.execute(select(Runbook.embedding_model, Runbook.embedding_digest).distinct())
    ).all()
    for model_name, digest in rows:
        if model_name != settings.aegisops_embedding_model:
            raise EmbeddingConfigError(
                f"Runbook index uses model '{model_name}', but runtime is configured for "
                f"'{settings.aegisops_embedding_model}'. Run reindex via scripts/seed.ps1."
            )
        if digest != settings.aegisops_embedding_model_digest:
            raise EmbeddingConfigError(
                f"Runbook index digest '{digest}' mismatches configured digest "
                f"'{settings.aegisops_embedding_model_digest}'. Run reindex via scripts/seed.ps1."
            )
