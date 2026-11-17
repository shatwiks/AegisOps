"""Runbook knowledge browser, validated Markdown upload, indexing jobs, and hybrid search tester."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.oidc import AuthenticatedUser, optional_authenticate_request, require_role
from app.config import Settings
from app.models.entities import AuditRecord, OutboxJob, Runbook
from app.playbooks.registry import PLAYBOOK_REGISTRY
from app.rag.embeddings import EmbeddingConfigError, embed_texts
from app.rag.retriever import hybrid_search_runbooks

router = APIRouter(prefix="/api/v1/runbooks", tags=["runbooks"])

MAX_UPLOAD_BYTES = 65_536  # 64 KiB
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,120}$")
_DANGEROUS_MD_RE = re.compile(
    r"(?is)<\s*script\b|<\s*iframe\b|<\s*object\b|<\s*embed\b|javascript:|on[a-z]{2,20}\s*="
)


def _extract_section(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    if marker not in markdown:
        return ""
    after = markdown.split(marker, 1)[1]
    next_idx = after.find("\n## ")
    return (after[:next_idx] if next_idx != -1 else after).strip()


def _serialize_runbook_summary(rb: Runbook) -> dict[str, Any]:
    app_json = rb.applicability_json or {}
    pid = rb.permitted_playbook_id
    executable = bool(pid and pid in PLAYBOOK_REGISTRY)
    approval_mode = str(
        app_json.get("approval_mode")
        or ("escalation_only" if not executable else ("mfa_required" if rb.risk_tier == "HIGH" else "auto_eligible"))
    )
    return {
        "id": str(rb.id),
        "slug": rb.slug,
        "title": rb.title,
        "doc_type": rb.doc_type,
        "service_slug": rb.service_slug,
        "alertnames": list(app_json.get("alertnames") or []),
        "risk_tier": rb.risk_tier,
        "permitted_playbook_id": pid,
        "executable_in_registry": executable,
        "approval_mode": approval_mode,
        "version": rb.version,
        "source": rb.source,
        "tags": list(rb.tags_json or []),
        "indexing_status": rb.indexing_status,
        "indexing_error": rb.indexing_error,
        "embedding_model": rb.embedding_model,
        "embedding_dimensions": 768 if rb.embedding is not None else 0,
        "symptoms_preview": (rb.symptoms or "")[:240],
        "updated_at": rb.updated_at.isoformat(),
    }


def parse_and_validate_uploaded_markdown(
    *,
    filename: str,
    raw_bytes: bytes,
) -> dict[str, Any]:
    """Validate uploaded Markdown strictly before persistence (never grants new playbook authority)."""
    safe_name = Path(filename).name
    if not safe_name or safe_name != filename or ".." in filename or "/" in filename or "\\" in filename:
        raise ValueError("Invalid filename (path traversal or directory components rejected).")
    if not safe_name.lower().endswith(".md"):
        raise ValueError("Only '.md' Markdown files are accepted.")
    if len(raw_bytes) == 0:
        raise ValueError("Uploaded Markdown file is empty.")
    if len(raw_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Uploaded file exceeds 64 KiB limit ({len(raw_bytes)} > {MAX_UPLOAD_BYTES} bytes).")

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Uploaded Markdown file must be valid UTF-8 text.") from exc

    if _DANGEROUS_MD_RE.search(text):
        raise ValueError("Uploaded Markdown contains disallowed HTML/script or inline event handler content.")

    if not text.lstrip().startswith("---"):
        raise ValueError("Markdown must start with YAML frontmatter delimited by '---'.")

    stripped = text.lstrip()
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Malformed YAML frontmatter closing '---' delimiter.")

    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML frontmatter: {exc}") from exc

    if not isinstance(meta, dict):
        raise ValueError("YAML frontmatter must decode to a mapping/object.")

    slug = str(meta.get("slug") or "").strip().lower()
    if not _SLUG_RE.match(slug):
        raise ValueError("Frontmatter 'slug' must match ^[a-z0-9][a-z0-9-]{2,120}$.")

    title = str(meta.get("title") or "").strip()
    if len(title) < 3 or len(title) > 250:
        raise ValueError("Frontmatter 'title' must be between 3 and 250 characters.")

    service_slug = str(meta.get("service_slug") or "").strip()
    if not service_slug or len(service_slug) > 120:
        raise ValueError("Frontmatter 'service_slug' is required.")

    raw_doc_type = str(meta.get("doc_type") or "RUNBOOK").strip().upper()
    if raw_doc_type not in ("RUNBOOK", "POSTMORTEM"):
        raise ValueError("Frontmatter 'doc_type' must be 'RUNBOOK' or 'POSTMORTEM'.")

    raw_playbook = meta.get("permitted_playbook_id", meta.get("playbook_id"))
    if isinstance(raw_playbook, str):
        raw_playbook = raw_playbook.strip()
        if raw_playbook.lower() in ("", "none", "null"):
            raw_playbook = None
    elif raw_playbook is not None:
        raise ValueError("Frontmatter 'permitted_playbook_id' must be a string or null.")

    if raw_playbook is not None and raw_playbook not in PLAYBOOK_REGISTRY:
        raise ValueError(
            f"Unknown playbook_id '{raw_playbook}'. Uploaded Markdown cannot register executable playbooks; "
            f"omit or set permitted_playbook_id=null for reference/escalation knowledge, or reference one of {sorted(PLAYBOOK_REGISTRY)}."
        )

    raw_risk = str(meta.get("risk_tier") or "HIGH").strip().upper()
    if raw_risk not in ("LOW", "HIGH"):
        raise ValueError("Frontmatter 'risk_tier' must be 'LOW' or 'HIGH'.")

    if raw_playbook is not None:
        spec = PLAYBOOK_REGISTRY[raw_playbook]
        if spec.risk_tier == "HIGH" and raw_risk == "LOW":
            raise ValueError(
                f"Cannot downgrade risk_tier to 'LOW' for HIGH-risk playbook '{raw_playbook}'."
            )
        if spec.risk_tier == "HIGH":
            raw_risk = "HIGH"

    version = str(meta.get("version") or "1.0.0").strip()[:32]
    tags_raw = meta.get("tags") or []
    if not isinstance(tags_raw, list):
        raise ValueError("Frontmatter 'tags' must be a YAML list of strings.")
    tags = [str(t).strip()[:48] for t in tags_raw if str(t).strip()][:12]

    applicability = dict(meta.get("applicability") or {})
    alertnames: list[str] = [str(a).strip() for a in (applicability.get("alertnames") or []) if str(a).strip()]
    if meta.get("alert_name"):
        an = str(meta["alert_name"]).strip()
        if an and an not in alertnames:
            alertnames.insert(0, an)
    applicability["alertnames"] = alertnames
    if "services" not in applicability:
        applicability["services"] = [service_slug]
    applicability["approval_mode"] = (
        "escalation_only"
        if raw_playbook is None
        else ("mfa_required" if raw_risk == "HIGH" else "auto_eligible")
    )

    body = parts[2].strip()
    if len(body) < 10:
        raise ValueError("Markdown body content is required after YAML frontmatter.")

    symptoms = _extract_section(body, "Symptoms") or body[:320]
    expected_result = _extract_section(body, "Expected Result") or "Follow escalation or server policy guidance."
    verification_steps = _extract_section(body, "Verification Steps") or "Verify health endpoints and stability window."
    escalation_guidance = _extract_section(body, "Escalation Guidance") or "Escalate to owning SRE team."
    evidence_reqs = [str(e).strip() for e in (meta.get("evidence_requirements") or []) if str(e).strip()]

    embed_text = (
        f"{title}\n"
        f"Service: {service_slug}\n"
        f"Symptoms: {symptoms}\n"
        f"Evidence: {'; '.join(evidence_reqs)}"
    )
    fts_source = f"{title} {service_slug} {symptoms} {' '.join(evidence_reqs)} {body}"

    return {
        "slug": slug,
        "title": title,
        "doc_type": raw_doc_type,
        "service_slug": service_slug,
        "symptoms": symptoms,
        "evidence_requirements_json": evidence_reqs,
        "applicability_json": applicability,
        "preconditions_json": dict(meta.get("preconditions") or {}),
        "risk_tier": raw_risk,
        "permitted_playbook_id": raw_playbook,
        "expected_result": expected_result,
        "verification_steps": verification_steps,
        "escalation_guidance": escalation_guidance,
        "body_markdown": body,
        "version": version,
        "tags_json": tags,
        "_embed_text": embed_text,
        "_fts_source": fts_source,
    }


async def index_runbook_by_slug(
    slug: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> tuple[str, str | None]:
    """Compute Ollama embedding for an uploaded/pending runbook and atomically flip READY or FAILED."""
    async with session_factory() as session:
        rb = (await session.execute(select(Runbook).where(Runbook.slug == slug))).scalar_one_or_none()
        if rb is None:
            return "FAILED", f"Runbook '{slug}' not found"
        embed_text = (
            f"{rb.title}\n"
            f"Service: {rb.service_slug}\n"
            f"Symptoms: {rb.symptoms}\n"
            f"Evidence: {'; '.join(rb.evidence_requirements_json or [])}"
        )
        fts_source = (
            f"{rb.title} {rb.service_slug} {rb.symptoms} "
            f"{' '.join(rb.evidence_requirements_json or [])} {rb.body_markdown}"
        )

    try:
        vectors = await embed_texts([embed_text], settings)
        vec = vectors[0]
        async with session_factory() as session, session.begin():
            rb_upd = (
                await session.execute(select(Runbook).where(Runbook.slug == slug))
            ).scalar_one_or_none()
            if rb_upd is not None:
                rb_upd.embedding = vec
                rb_upd.embedding_model = settings.aegisops_embedding_model
                rb_upd.embedding_digest = settings.aegisops_embedding_model_digest
                rb_upd.search_tsv = func.to_tsvector("english", fts_source)
                rb_upd.indexing_status = "READY"
                rb_upd.indexing_error = None
        return "READY", None
    except Exception as exc:
        err_msg = f"{type(exc).__name__}: {str(exc)[:280]}"
        async with session_factory() as session, session.begin():
            rb_fail = (
                await session.execute(select(Runbook).where(Runbook.slug == slug))
            ).scalar_one_or_none()
            if rb_fail is not None:
                rb_fail.indexing_status = "FAILED"
                rb_fail.indexing_error = err_msg
        return "FAILED", err_msg


async def process_runbook_indexing_job(
    job: OutboxJob,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Outbox worker handler for `INDEX_RUNBOOK` jobs."""
    payload = job.payload_sanitized_json or {}
    slug = str(payload.get("slug") or "")
    if not slug:
        return
    await index_runbook_by_slug(slug, session_factory=session_factory, settings=settings)


@router.get("")
async def list_runbooks(
    request: Request,
    q: str | None = Query(default=None),
    doc_type: str | None = Query(default=None),
    service_slug: str | None = Query(default=None),
    indexing_status: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    _: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Browse knowledge base documents with actual database counts (`visitor+`)."""
    async with request.app.state.session_factory() as session:
        counts_rows = (
            await session.execute(select(Runbook.indexing_status, func.count(Runbook.id)).group_by(Runbook.indexing_status))
        ).all()
        by_status = {str(st): int(cnt) for st, cnt in counts_rows}

        stmt = select(Runbook)
        if q and q.strip():
            like = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    Runbook.slug.ilike(like),
                    Runbook.title.ilike(like),
                    Runbook.symptoms.ilike(like),
                    Runbook.service_slug.ilike(like),
                )
            )
        if doc_type:
            stmt = stmt.where(Runbook.doc_type == doc_type.strip().upper())
        if service_slug:
            stmt = stmt.where(Runbook.service_slug == service_slug.strip())
        if indexing_status:
            stmt = stmt.where(Runbook.indexing_status == indexing_status.strip().upper())

        total_filtered = int(
            (await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one() or 0
        )
        rows = (
            (
                await session.execute(
                    stmt.order_by(Runbook.doc_type.asc(), Runbook.slug.asc()).offset(offset).limit(limit)
                )
            )
            .scalars()
            .all()
        )

    return {
        "items": [_serialize_runbook_summary(r) for r in rows],
        "total_filtered": total_filtered,
        "counts": {
            "total": sum(by_status.values()),
            "ready": by_status.get("READY", 0),
            "indexing": by_status.get("INDEXING", 0) + by_status.get("VALIDATING", 0) + by_status.get("UPLOADED", 0),
            "failed": by_status.get("FAILED", 0),
        },
        "pagination": {"offset": offset, "limit": limit, "has_more": (offset + len(rows)) < total_filtered},
    }


@router.get("/{slug}")
async def get_runbook_detail(
    slug: str,
    request: Request,
    _: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Read full sanitized Markdown body and metadata for a runbook or postmortem (`visitor+`)."""
    async with request.app.state.session_factory() as session:
        rb = (await session.execute(select(Runbook).where(Runbook.slug == slug))).scalar_one_or_none()
        if rb is None:
            raise HTTPException(status_code=404, detail=f"Runbook '{slug}' not found")
        data = _serialize_runbook_summary(rb)
        data["body_markdown"] = rb.body_markdown
        data["symptoms"] = rb.symptoms
        data["evidence_requirements"] = list(rb.evidence_requirements_json or [])
        data["applicability"] = dict(rb.applicability_json or {})
        data["preconditions"] = dict(rb.preconditions_json or {})
        data["expected_result"] = rb.expected_result
        data["verification_steps"] = rb.verification_steps
        data["escalation_guidance"] = rb.escalation_guidance
        data["uploaded_by_sub"] = rb.uploaded_by_sub
        data["created_at"] = rb.created_at.isoformat()
    return {"runbook": data}


@router.post("/upload")
async def upload_runbook_markdown(
    request: Request,
    user: AuthenticatedUser = Depends(require_role("operator")),
) -> JSONResponse:
    """Validate and ingest an uploaded `.md` runbook (`operator+`), without creating new executable playbooks."""
    content_type = request.headers.get("content-type", "").lower()
    async_index = False
    overwrite = False
    filename = ""
    raw_bytes = b""

    if "multipart/form-data" in content_type:
        form = await request.form()
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(status_code=400, detail="Multipart 'file' upload field is required.")
        filename = str(getattr(upload, "filename", "") or "")
        raw_bytes = await upload.read()
        async_index = str(form.get("async_index") or "false").lower() in ("1", "true", "yes")
        overwrite = str(form.get("overwrite") or "false").lower() in ("1", "true", "yes")
    else:
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Expected multipart/form-data or JSON body.") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="JSON body must be an object.")
        filename = str(payload.get("filename") or "")
        raw_content = str(payload.get("content") or "")
        raw_bytes = raw_content.encode("utf-8")
        async_index = bool(payload.get("async_index", False))
        overwrite = bool(payload.get("overwrite", False))

    lifecycle_trace = ["UPLOADED", "VALIDATING"]
    try:
        parsed = parse_and_validate_uploaded_markdown(filename=filename, raw_bytes=raw_bytes)
    except ValueError as exc:
        msg = str(exc)
        status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if "exceeds 64 KiB" in msg else 400
        raise HTTPException(status_code=status_code, detail=msg) from exc

    settings = request.app.state.settings
    slug = parsed["slug"]
    lifecycle_trace.append("INDEXING")

    async with request.app.state.session_factory() as session, session.begin():
        existing = (await session.execute(select(Runbook).where(Runbook.slug == slug))).scalar_one_or_none()
        if existing is not None:
            if existing.source == "seeded_file":
                raise HTTPException(
                    status_code=409,
                    detail=f"Cannot overwrite seeded built-in runbook '{slug}'; choose a custom slug.",
                )
            if existing.version == parsed["version"] and not overwrite:
                raise HTTPException(
                    status_code=409,
                    detail=f"Runbook '{slug}' version '{parsed['version']}' already exists; bump 'version' in YAML frontmatter or enable overwrite.",
                )
            existing.title = parsed["title"]
            existing.doc_type = parsed["doc_type"]
            existing.service_slug = parsed["service_slug"]
            existing.symptoms = parsed["symptoms"]
            existing.evidence_requirements_json = parsed["evidence_requirements_json"]
            existing.applicability_json = parsed["applicability_json"]
            existing.preconditions_json = parsed["preconditions_json"]
            existing.risk_tier = parsed["risk_tier"]
            existing.permitted_playbook_id = parsed["permitted_playbook_id"]
            existing.expected_result = parsed["expected_result"]
            existing.verification_steps = parsed["verification_steps"]
            existing.escalation_guidance = parsed["escalation_guidance"]
            existing.body_markdown = parsed["body_markdown"]
            existing.version = parsed["version"]
            existing.tags_json = parsed["tags_json"]
            existing.indexing_status = "INDEXING"
            existing.indexing_error = None
            existing.embedding = None
            existing.uploaded_by_sub = user.sub
            existing.search_tsv = func.to_tsvector("english", parsed["_fts_source"])
            rb_row = existing
        else:
            rb_row = Runbook(
                slug=slug,
                title=parsed["title"],
                doc_type=parsed["doc_type"],
                service_slug=parsed["service_slug"],
                symptoms=parsed["symptoms"],
                evidence_requirements_json=parsed["evidence_requirements_json"],
                applicability_json=parsed["applicability_json"],
                preconditions_json=parsed["preconditions_json"],
                risk_tier=parsed["risk_tier"],
                permitted_playbook_id=parsed["permitted_playbook_id"],
                expected_result=parsed["expected_result"],
                verification_steps=parsed["verification_steps"],
                escalation_guidance=parsed["escalation_guidance"],
                body_markdown=parsed["body_markdown"],
                search_tsv=func.to_tsvector("english", parsed["_fts_source"]),
                embedding=None,
                embedding_model=settings.aegisops_embedding_model,
                embedding_digest=settings.aegisops_embedding_model_digest,
                version=parsed["version"],
                source="uploaded_md",
                tags_json=parsed["tags_json"],
                indexing_status="INDEXING",
                uploaded_by_sub=user.sub,
            )
            session.add(rb_row)

        session.add(
            AuditRecord(
                actor_sub=user.sub,
                actor_role=user.highest_role,
                action_type="RUNBOOK_UPLOADED",
                policy_decision=parsed["applicability_json"]["approval_mode"],
                details_json={
                    "slug": slug,
                    "version": parsed["version"],
                    "permitted_playbook_id": parsed["permitted_playbook_id"],
                    "risk_tier": parsed["risk_tier"],
                    "async_index": async_index,
                },
            )
        )

        if async_index:
            session.add(
                OutboxJob(
                    incident_id=None,
                    job_type="INDEX_RUNBOOK",
                    dedup_job_key=f"index-runbook:{slug}:{parsed['version']}:{uuid.uuid4().hex[:8]}",
                    payload_sanitized_json={"slug": slug, "version": parsed["version"]},
                )
            )
            await session.flush()
            serialized = _serialize_runbook_summary(rb_row)

    if async_index:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"runbook": serialized, "lifecycle_trace": lifecycle_trace},
        )

    final_status, idx_err = await index_runbook_by_slug(
        slug,
        session_factory=request.app.state.session_factory,
        settings=settings,
    )
    lifecycle_trace.append(final_status)
    async with request.app.state.session_factory() as session:
        fresh = (await session.execute(select(Runbook).where(Runbook.slug == slug))).scalar_one()
        serialized = _serialize_runbook_summary(fresh)
    return JSONResponse(
        status_code=status.HTTP_201_CREATED if final_status == "READY" else status.HTTP_200_OK,
        content={
            "runbook": serialized,
            "lifecycle_trace": lifecycle_trace,
            "indexing_error": idx_err,
        },
    )


@router.post("/{slug}/retry-index")
async def retry_runbook_index(
    slug: str,
    request: Request,
    user: AuthenticatedUser = Depends(require_role("operator")),
) -> dict[str, Any]:
    """Retry Ollama embedding generation for a FAILED or pending runbook (`operator+`)."""
    async with request.app.state.session_factory() as session, session.begin():
        rb = (await session.execute(select(Runbook).where(Runbook.slug == slug))).scalar_one_or_none()
        if rb is None:
            raise HTTPException(status_code=404, detail=f"Runbook '{slug}' not found")
        rb.indexing_status = "INDEXING"
        rb.indexing_error = None
        session.add(
            AuditRecord(
                actor_sub=user.sub,
                actor_role=user.highest_role,
                action_type="RUNBOOK_RETRY_INDEX",
                policy_decision="INDEXING",
                details_json={"slug": slug},
            )
        )

    final_status, idx_err = await index_runbook_by_slug(
        slug,
        session_factory=request.app.state.session_factory,
        settings=request.app.state.settings,
    )
    async with request.app.state.session_factory() as session:
        fresh = (await session.execute(select(Runbook).where(Runbook.slug == slug))).scalar_one()
        return {
            "runbook": _serialize_runbook_summary(fresh),
            "indexing_error": idx_err,
            "status": final_status,
        }


class HybridSearchTestRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    service_slug: str | None = Field(default=None, max_length=120)
    top_k: int = Field(default=5, ge=1, le=10)


@router.post("/search")
async def test_hybrid_search(
    body: HybridSearchTestRequest,
    request: Request,
    _: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> JSONResponse:
    """Execute real hybrid FTS + pgvector cosine + RRF search (`visitor+`) and explain threshold decisions."""
    settings = request.app.state.settings
    async with request.app.state.session_factory() as session:
        in_progress_cnt = int(
            (
                await session.execute(
                    select(func.count(Runbook.id)).where(
                        Runbook.indexing_status.in_(["UPLOADED", "VALIDATING", "INDEXING"])
                    )
                )
            ).scalar_one()
            or 0
        )

        search_q = body.query.strip()
        effective_q = f"{body.service_slug.strip()} {search_q}" if body.service_slug else search_q
        try:
            docs = await hybrid_search_runbooks(
                session,
                effective_q,
                settings,
                top_k=max(body.top_k * 2, 10) if body.service_slug else body.top_k,
                rrf_k=60,
            )
        except (EmbeddingConfigError, Exception) as exc:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "model_unavailable",
                    "detail": f"Embedding search unavailable: {type(exc).__name__}: {str(exc)[:220]}",
                    "indexing_in_progress_count": in_progress_cnt,
                    "hits": [],
                },
            )

        if body.service_slug:
            svc = body.service_slug.strip()
            filtered = [
                d
                for d in docs
                if d.service_slug == svc or svc in (d.applicability_json.get("services") or [])
            ]
            docs = filtered[: body.top_k]

        meta_rows = (
            await session.execute(
                select(Runbook.slug, Runbook.version, Runbook.source).where(
                    Runbook.slug.in_([d.slug for d in docs] or ["__none__"])
                )
            )
        ).all()
        meta_by_slug = {str(s): {"version": str(v), "source": str(src)} for s, v, src in meta_rows}

    cos_threshold = float(settings.aegisops_similarity_threshold)
    hits_out: list[dict[str, Any]] = []
    for idx, d in enumerate(docs, start=1):
        passes_vec = d.vector_similarity >= cos_threshold
        passes_lex = d.lexical_score >= 0.05 and d.vector_similarity >= 0.50
        primary_eligible = passes_vec or passes_lex
        m = meta_by_slug.get(d.slug, {"version": "1.0.0", "source": "seeded_file"})
        hits_out.append(
            {
                "rrf_rank": idx,
                "slug": d.slug,
                "title": d.title,
                "doc_type": d.doc_type,
                "service_slug": d.service_slug,
                "version": m["version"],
                "source": m["source"],
                "risk_tier": d.risk_tier,
                "permitted_playbook_id": d.permitted_playbook_id,
                "vector_similarity": round(d.vector_similarity, 4),
                "vector_rank": d.vector_rank,
                "lexical_score": round(d.lexical_score, 4),
                "lexical_rank": d.lexical_rank,
                "rrf_score": round(d.rrf_score, 6),
                "passes_cosine_threshold": passes_vec,
                "passes_lexical_corroboration": passes_lex,
                "is_primary_evidence": primary_eligible,
                "matched_passage": d.symptoms[:360] or d.body_markdown[:360],
            }
        )

    ambiguous = (
        len(hits_out) >= 2
        and abs(float(hits_out[0]["rrf_score"]) - float(hits_out[1]["rrf_score"])) <= 0.0025
    ) or (len(hits_out) > 0 and not hits_out[0]["is_primary_evidence"])

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok" if hits_out else "empty",
            "query": search_q,
            "service_slug": body.service_slug,
            "hits": hits_out,
            "ambiguous": ambiguous,
            "indexing_in_progress_count": in_progress_cnt,
            "explanation": {
                "rrf_k": 60,
                "cosine_similarity_threshold": cos_threshold,
                "lexical_corroboration_rule": "lexical_score >= 0.05 AND vector_similarity >= 0.50",
                "embedding_model": settings.aegisops_embedding_model,
                "embedding_dimensions": settings.aegisops_embedding_dimensions,
                "plain_english": (
                    f"Hybrid retrieval fuses PostgreSQL full-text search (ts_rank_cd) and pgvector cosine "
                    f"similarity ({settings.aegisops_embedding_dimensions}-dim {settings.aegisops_embedding_model}) "
                    f"using Reciprocal Rank Fusion (RRF, k=60). RRF ranks candidates deterministically without "
                    f"treating RRF scores as probabilities; the policy gate separately requires cosine similarity "
                    f">= {cos_threshold:.2f} (or >= 0.50 with lexical corroboration >= 0.05) before trusting a match."
                ),
            },
        },
    )


def build_json_log_audit_safe(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True)
