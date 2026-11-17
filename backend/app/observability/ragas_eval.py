"""Reproducible Ragas evaluation runner configured against local Ollama."""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import Faithfulness, LLMContextRecall
from ragas.run_config import RunConfig

from app.config import Settings
from app.privacy.scrubber import scrub_value


def run_local_ragas_evaluation(
    samples: list[dict[str, Any]],
    settings: Settings,
) -> dict[str, Any]:
    """Run Ragas Faithfulness & ContextRecall using local Ollama OpenAI-compatible API."""
    counts: dict[str, int] = {}
    safe_samples = scrub_value(samples, counts)
    base_url = f"{settings.aegisops_ollama_base_url.rstrip('/')}/v1"

    evaluator_llm = LangchainLLMWrapper(
        ChatOpenAI(
            model=settings.aegisops_chat_model,
            api_key="ollama",  # type: ignore[arg-type]
            base_url=base_url,
            temperature=0.0,
            timeout=180.0,
        )
    )
    evaluator_embeddings = LangchainEmbeddingsWrapper(
        OpenAIEmbeddings(
            model=settings.aegisops_embedding_model,
            api_key="ollama",  # type: ignore[arg-type]
            base_url=base_url,
        )
    )

    dataset_samples = [
        SingleTurnSample(
            user_input=s["question"],
            retrieved_contexts=s["contexts"],
            response=s["answer"],
            reference=s["ground_truth"],
        )
        for s in safe_samples
    ]
    dataset = EvaluationDataset(samples=dataset_samples)
    result = evaluate(
        dataset=dataset,
        metrics=[Faithfulness(), LLMContextRecall()],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        run_config=RunConfig(timeout=180, max_workers=1, max_retries=2),
        raise_exceptions=False,
    )
    scores_df = result.to_pandas()
    summary: dict[str, Any] = {
        "model": settings.aegisops_chat_model,
        "embedding_model": settings.aegisops_embedding_model,
        "sample_count": len(dataset_samples),
        "metrics": {},
        "per_sample": scores_df.to_dict(orient="records"),
    }
    for col in ("faithfulness", "context_recall"):
        if col in scores_df.columns:
            valid = scores_df[col].dropna()
            summary["metrics"][col] = round(float(valid.mean()), 4) if len(valid) > 0 else None
    return summary
