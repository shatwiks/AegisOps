"""Idempotent runbook and synthetic postmortem ingestion with real Ollama 768-dim embeddings."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import build_engine, build_session_factory
from app.models.entities import Runbook
from app.rag.embeddings import embed_texts

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RUNBOOKS_DIR = _REPO_ROOT / "runbooks"


def _extract_section(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    if marker not in markdown:
        return ""
    after = markdown.split(marker, 1)[1]
    next_idx = after.find("\n## ")
    return (after[:next_idx] if next_idx != -1 else after).strip()


def parse_runbook_markdown(file_path: Path) -> dict[str, Any]:
    """Parse YAML frontmatter + Markdown sections from a runbook/postmortem file."""
    raw = file_path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"{file_path.name} missing YAML frontmatter")
    parts = raw.split("---", 2)
    meta = yaml.safe_load(parts[1])
    body = parts[2].strip()

    symptoms = _extract_section(body, "Symptoms")
    expected_result = _extract_section(body, "Expected Result")
    verification_steps = _extract_section(body, "Verification Steps")
    escalation_guidance = _extract_section(body, "Escalation Guidance")

    embed_text = (
        f"{meta['title']}\n"
        f"Service: {meta['service_slug']}\n"
        f"Symptoms: {symptoms}\n"
        f"Evidence: {'; '.join(meta.get('evidence_requirements', []))}"
    )

    return {
        "slug": meta["slug"],
        "title": meta["title"],
        "doc_type": meta["doc_type"],
        "service_slug": meta["service_slug"],
        "symptoms": symptoms,
        "evidence_requirements_json": list(meta.get("evidence_requirements", [])),
        "applicability_json": dict(meta.get("applicability", {})),
        "preconditions_json": dict(meta.get("preconditions", {})),
        "risk_tier": meta["risk_tier"],
        "permitted_playbook_id": meta.get("permitted_playbook_id"),
        "expected_result": expected_result,
        "verification_steps": verification_steps,
        "escalation_guidance": escalation_guidance,
        "body_markdown": body,
        "_embed_text": embed_text,
    }


async def seed_runbooks(
    session: AsyncSession,
    settings: Settings,
    *,
    runbooks_dir: Path | None = None,
) -> dict[str, int]:
    """Parse all runbooks/*.md, generate Ollama embeddings, and upsert into PostgreSQL."""
    target_dir = runbooks_dir or _RUNBOOKS_DIR
    files = sorted(target_dir.glob("*.md"))
    parsed = [parse_runbook_markdown(fp) for fp in files]
    if not parsed:
        return {"runbooks": 0, "postmortems": 0}

    vectors = await embed_texts([p["_embed_text"] for p in parsed], settings)

    rb_count = 0
    pm_count = 0
    for item, vec in zip(parsed, vectors, strict=True):
        if item["doc_type"] == "RUNBOOK":
            rb_count += 1
        else:
            pm_count += 1

        fts_source = (
            f"{item['title']} {item['service_slug']} {item['symptoms']} "
            f"{' '.join(item['evidence_requirements_json'])} {item['body_markdown']}"
        )

        stmt = (
            pg_insert(Runbook)
            .values(
                slug=item["slug"],
                title=item["title"],
                doc_type=item["doc_type"],
                service_slug=item["service_slug"],
                symptoms=item["symptoms"],
                evidence_requirements_json=item["evidence_requirements_json"],
                applicability_json=item["applicability_json"],
                preconditions_json=item["preconditions_json"],
                risk_tier=item["risk_tier"],
                permitted_playbook_id=item["permitted_playbook_id"],
                expected_result=item["expected_result"],
                verification_steps=item["verification_steps"],
                escalation_guidance=item["escalation_guidance"],
                body_markdown=item["body_markdown"],
                search_tsv=func.to_tsvector("english", fts_source),
                embedding=vec,
                embedding_model=settings.aegisops_embedding_model,
                embedding_digest=settings.aegisops_embedding_model_digest,
            )
            .on_conflict_do_update(
                index_elements=["slug"],
                set_={
                    "title": item["title"],
                    "doc_type": item["doc_type"],
                    "service_slug": item["service_slug"],
                    "symptoms": item["symptoms"],
                    "evidence_requirements_json": item["evidence_requirements_json"],
                    "applicability_json": item["applicability_json"],
                    "preconditions_json": item["preconditions_json"],
                    "risk_tier": item["risk_tier"],
                    "permitted_playbook_id": item["permitted_playbook_id"],
                    "expected_result": item["expected_result"],
                    "verification_steps": item["verification_steps"],
                    "escalation_guidance": item["escalation_guidance"],
                    "body_markdown": item["body_markdown"],
                    "search_tsv": func.to_tsvector("english", fts_source),
                    "embedding": vec,
                    "embedding_model": settings.aegisops_embedding_model,
                    "embedding_digest": settings.aegisops_embedding_model_digest,
                },
            )
        )
        await session.execute(stmt)

    return {"runbooks": rb_count, "postmortems": pm_count, "total": len(parsed)}


async def _main() -> None:
    settings = get_settings()
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            counts = await seed_runbooks(session, settings)
        print(f"Seeded runbooks & postmortems cleanly: {counts}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_main())
