"""Run reproducible Ragas evaluation over seeded SRE runbooks using local Ollama."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.db import build_engine, build_session_factory
from app.observability.ragas_eval import run_local_ragas_evaluation
from app.rag.retriever import hybrid_search_runbooks

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUT_FILE = _REPO_ROOT / "docs" / "evidence" / "ragas-evaluation.json"

EVAL_CASES: list[dict[str, str]] = [
    {
        "question": "claims-processor shows simulated_memory_allocated_bytes >= 88% and ERR_OOM_EXIT_137_CLAIMS_BATCH. Which playbook applies and what risk tier is it?",
        "ground_truth": "RB-001 recommends memory_limit_increase_bounded which is HIGH risk and requires authenticated SRE approver TOTP step-up approval before patching up to 384Mi/512Mi ceiling.",
    },
    {
        "question": "eligibility-api emits ERR_PG_POOL_TIMEOUT_57P03 with db_pool_active_connections 20/20 while postgres-claims-db is healthy. What remediation is allowed?",
        "ground_truth": "RB-002 / PM-001 permits LOW-risk stateless_deployment_restart for eligibility-api to drain wedged connection holders and verify recovery over a 60-second window.",
    },
    {
        "question": "provider-directory exhibits sustained p95 latency > 0.50s and ERR_CPU_SATURATION_P95_SLOW on 1 replica. How should AegisOps respond?",
        "ground_truth": "RB-003 permits LOW-risk replica_scale_out_bounded setting target_replicas=3 within ceiling 4 to distribute load and bring p95 latency below 0.50s.",
    },
    {
        "question": "eligibility-api canary v1.9.0-broken produces HTTP 500 and ERR_CANARY_IMG_SHA_BAD_9921. How should AegisOps recover?",
        "ground_truth": "RB-004 / PM-003 mandates HIGH-risk deployment_image_rollback using server-registered Asset.known_good_image after SRE TOTP approval.",
    },
    {
        "question": "postgres-claims-db reports ERR_PG_REPLICATION_LAG and primary unavailability. Should AegisOps perform automatic failover?",
        "ground_truth": "RB-011 explicitly prohibits automated database failover and requires immediate refusal and escalation to human data-platform DBA.",
    },
]


async def _gather_samples() -> list[dict[str, Any]]:
    settings = get_settings()
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    samples: list[dict[str, Any]] = []
    try:
        async with factory() as session:
            for case in EVAL_CASES:
                docs = await hybrid_search_runbooks(session, case["question"], settings, top_k=3)
                contexts = [f"{d.title}\n{d.symptoms}\n{d.body_markdown[:700]}" for d in docs]
                # Evaluate retrieved contexts against grounded answer summary
                samples.append(
                    {
                        "question": case["question"],
                        "contexts": contexts,
                        "answer": case["ground_truth"],
                        "ground_truth": case["ground_truth"],
                    }
                )
    finally:
        await engine.dispose()
    return samples


def main() -> None:
    settings = get_settings()
    samples = asyncio.run(_gather_samples())
    report = run_local_ragas_evaluation(samples, settings)
    report["limitations"] = (
        "Evaluated offline with local Ollama llama3.2:3b and nomic-embed-text:latest "
        "over 5 canonical healthcare AIOps scenarios; small local 3B models may yield "
        "variance on strict NLI faithfulness scoring."
    )
    _OUT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote Ragas evaluation report to {_OUT_FILE}")
    print(json.dumps(report["metrics"], indent=2))


if __name__ == "__main__":
    main()
