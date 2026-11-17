"""Sanitized Langfuse tracing wrapper that degrades safely when Langfuse is disabled or offline."""

from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.privacy.scrubber import scrub_value

logger = logging.getLogger("aegisops.langfuse")


def record_sanitized_llm_trace(
    *,
    settings: Settings,
    trace_name: str,
    incident_id: str,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send scrubbed LLM trace to local Langfuse if enabled; never blocks remediation on failure."""
    counts: dict[str, int] = {}
    safe_input = scrub_value(input_payload, counts)
    safe_output = scrub_value(output_payload, counts)
    safe_meta = scrub_value(metadata or {}, counts)

    if not settings.aegisops_langfuse_enabled or not (
        settings.langfuse_public_key and settings.langfuse_secret_key
    ):
        return {
            "recorded": False,
            "reason": "langfuse_disabled",
            "scrub_redactions": sum(counts.values()),
        }

    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        trace = client.trace(
            id=f"aegisops-{incident_id}",
            name=trace_name,
            input=safe_input,
            output=safe_output,
            metadata=safe_meta,
        )
        trace.generation(
            name=f"{trace_name}-ollama",
            model=settings.aegisops_chat_model,
            input=safe_input,
            output=safe_output,
        )
        client.flush()
        return {"recorded": True, "trace_id": f"aegisops-{incident_id}"}
    except Exception as exc:
        logger.warning("Langfuse trace failed safely (%s): %s", type(exc).__name__, exc)
        return {"recorded": False, "reason": type(exc).__name__}
