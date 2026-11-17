"""Authenticated, scrubbed, deduplicated Alertmanager webhook ingestion."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.cmdb.graph import compute_severity, get_blast_radius
from app.config import Settings
from app.domain.state_machine import IncidentState
from app.models.entities import Asset, AuditRecord, DemoRun, Incident, IncidentEvent, OutboxJob
from app.privacy.scrubber import scrub_alertmanager_payload

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

_FORBIDDEN_URL_KEYS = frozenset(
    {"log_source_url", "logs_url", "fetch_url", "callback_url", "webhook_url"}
)


def _verify_webhook_auth(request: Request, raw_body: bytes, settings: Settings) -> str:
    """Authenticate webhook via HMAC-SHA256 signature or Bearer token."""
    sig_header = request.headers.get("X-AegisOps-Signature", "").strip()
    if sig_header:
        expected_hex = hmac.new(
            settings.aegisops_webhook_hmac_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        provided_hex = sig_header.removeprefix("sha256=").strip()
        if hmac.compare_digest(provided_hex, expected_hex):
            return "alertmanager-hmac"

    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if hmac.compare_digest(token, settings.aegisops_webhook_bearer_token):
            return "alertmanager-bearer"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing webhook authentication signature/token",
    )


async def _enforce_rate_limit(request: Request, settings: Settings) -> None:
    """Sliding-minute fixed-window rate limiter backed by Redis."""
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        return
    minute_bucket = int(time.time() // 60)
    key = f"aegisops:ratelimit:webhook:{minute_bucket}"
    current = await redis_client.incr(key)
    if current == 1:
        await redis_client.expire(key, 65)
    if current > settings.aegisops_webhook_rate_limit_per_min:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Webhook rate limit exceeded",
        )


def _contains_forbidden_fetch_directive(obj: Any) -> bool:
    """Reject user-controlled log-source URLs (SSRF prevention)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).strip().lower() in _FORBIDDEN_URL_KEYS:
                return True
            if _contains_forbidden_fetch_directive(v):
                return True
    elif isinstance(obj, list):
        return any(_contains_forbidden_fetch_directive(item) for item in obj)
    return False


def _parse_iso_timestamp(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned or cleaned.startswith("0001-01-01"):
        return None
    try:
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        dt = datetime.fromisoformat(cleaned)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


async def _resolve_asset(
    session: AsyncSession, labels: dict[str, str]
) -> tuple[Asset | None, str | None]:
    """Resolve CMDB Asset deterministically by (cluster, namespace, name), (namespace, name), or slug."""
    service_name = (
        labels.get("service") or labels.get("app") or labels.get("deployment") or ""
    ).strip()
    namespace = labels.get("namespace", "").strip()
    cluster = labels.get("cluster", "").strip()

    if not service_name:
        return None, "unspecified"

    if cluster and namespace:
        asset = (
            await session.execute(
                select(Asset).where(
                    Asset.cluster == cluster,
                    Asset.namespace == namespace,
                    Asset.name == service_name,
                )
            )
        ).scalar_one_or_none()
        if asset is not None:
            return asset, None

    if namespace:
        asset = (
            await session.execute(
                select(Asset).where(Asset.namespace == namespace, Asset.name == service_name)
            )
        ).scalar_one_or_none()
        if asset is not None:
            return asset, None

    asset = (
        await session.execute(select(Asset).where(Asset.slug == service_name))
    ).scalar_one_or_none()
    if asset is not None:
        return asset, None

    unknown_id = "/".join(p for p in (cluster, namespace, service_name) if p)
    return None, unknown_id


@router.post("/alertmanager")
async def ingest_alertmanager_webhook(request: Request) -> JSONResponse:
    """Ingest Alertmanager webhook batch with boundary scrubbing, dedup, and atomic outbox."""
    settings: Settings = request.app.state.settings
    raw_body = await request.body()

    if len(raw_body) > settings.aegisops_webhook_max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Webhook payload exceeds maximum {settings.aegisops_webhook_max_bytes} bytes",
        )

    actor = _verify_webhook_auth(request, raw_body, settings)
    await _enforce_rate_limit(request, settings)

    try:
        parsed_raw = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed JSON webhook payload",
        ) from exc

    if _contains_forbidden_fetch_directive(parsed_raw):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arbitrary log-source URL directives are prohibited",
        )

    # Scrub immediately at boundary before any logging, DB writes, or downstream dispatch
    scrub_result = scrub_alertmanager_payload(parsed_raw)
    clean_payload = scrub_result.sanitized_data
    alerts = clean_payload.get("alerts", [])
    if not alerts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Alertmanager payload contains zero alerts",
        )

    results: list[dict[str, Any]] = []
    session_factory = request.app.state.session_factory
    raw_prov = request.headers.get("X-AegisOps-Provenance", "").strip().lower()
    explicit_prov = (
        raw_prov
        if raw_prov in {"live_alert", "interactive_demo", "automated_test", "recorded_replay"}
        else None
    )

    async with session_factory() as session:
        async with session.begin():
            for alert in alerts:
                labels: dict[str, str] = alert.get("labels", {})
                annotations: dict[str, str] = alert.get("annotations", {})
                alert_status = alert.get("status", "firing")
                alertname = labels.get("alertname", "UnknownAlert")
                fingerprint = (
                    alert.get("fingerprint")
                    or hashlib.sha256(
                        json.dumps(labels, sort_keys=True).encode("utf-8")
                    ).hexdigest()[:16]
                )

                asset, unknown_id = await _resolve_asset(session, labels)
                asset_key = asset.slug if asset is not None else (unknown_id or "unknown")
                dedup_key = f"{alertname}:{asset_key}:{fingerprint}"

                now = datetime.now(UTC)
                starts_at = _parse_iso_timestamp(alert.get("startsAt"))

                if alert_status == "resolved":
                    active_inc = (
                        await session.execute(
                            select(Incident)
                            .where(
                                Incident.dedup_key == dedup_key,
                                Incident.state.notin_(["RESOLVED", "FAILED"]),
                            )
                            .with_for_update()
                        )
                    ).scalar_one_or_none()
                    if active_inc is not None:
                        session.add(
                            IncidentEvent(
                                incident_id=active_inc.id,
                                event_type="ALERT_RESOLVED_SIGNAL",
                                from_state=active_inc.state,
                                to_state=active_inc.state,
                                actor=actor,
                                details_sanitized_json={
                                    "fingerprint": fingerprint,
                                    "note": "Alertmanager sent resolved signal; verification gate still governs closure.",
                                },
                                created_at=now,
                            )
                        )
                        results.append(
                            {
                                "incident_id": str(active_inc.id),
                                "dedup_key": dedup_key,
                                "action": "resolved_signal_recorded",
                            }
                        )
                    else:
                        results.append(
                            {
                                "incident_id": None,
                                "dedup_key": dedup_key,
                                "action": "resolved_signal_ignored_no_active_incident",
                            }
                        )
                    continue

                # Firing alert: compute blast radius and deterministic P1-P4 severity
                if asset is not None:
                    blast = await get_blast_radius(session, asset.slug)
                    downstream = blast.downstream_impacts
                else:
                    downstream = []

                severity, sev_expl = compute_severity(
                    asset,
                    downstream,
                    labels.get("severity", "warning"),
                    unknown_asset_identifier=unknown_id,
                )

                summary_text = (
                    annotations.get("description")
                    or annotations.get("summary")
                    or f"Alert {alertname} on {asset_key}"
                )
                title = f"[{severity}] {alertname} on {asset_key}"[:256]

                initial_state = (
                    IncidentState.ESCALATED.value
                    if scrub_result.scrubber_failed_fallback
                    else IncidentState.OPEN.value
                )

                new_inc_id = uuid.uuid4()
                active_demo_run: DemoRun | None = None
                if asset is not None and explicit_prov != "automated_test":
                    active_demo_run = (
                        await session.execute(
                            select(DemoRun)
                            .where(
                                DemoRun.target_service == asset.slug,
                                DemoRun.status.notin_(
                                    ["COMPLETED", "ESCALATED", "FAILED", "CANCELLED"]
                                ),
                            )
                            .order_by(DemoRun.started_at.desc())
                        )
                    ).scalars().first()

                resolved_provenance = explicit_prov or (
                    "interactive_demo" if active_demo_run is not None else "live_alert"
                )
                insert_stmt = (
                    pg_insert(Incident)
                    .values(
                        id=new_inc_id,
                        dedup_key=dedup_key,
                        alert_fingerprint=fingerprint,
                        alertname=alertname,
                        title=title,
                        summary_sanitized=summary_text,
                        primary_asset_id=asset.id if asset else None,
                        unknown_asset_identifier=unknown_id,
                        severity=severity,
                        severity_explanation_json=sev_expl,
                        state=initial_state,
                        source_provenance=resolved_provenance,
                        demo_run_id=active_demo_run.id if active_demo_run else None,
                        refusal_reason=(
                            "Boundary scrubber fail-closed fallback triggered"
                            if scrub_result.scrubber_failed_fallback
                            else None
                        ),
                        redaction_stats_json={
                            "redactions": scrub_result.redaction_counts,
                            "total_redactions": scrub_result.total_redactions,
                            "dropped_unallowlisted_keys": scrub_result.dropped_unallowlisted_keys,
                            "scrubber_failed_fallback": scrub_result.scrubber_failed_fallback,
                        },
                        fault_onset_at=starts_at,
                        detected_at=starts_at or now,
                        ingested_at=now,
                        version_id=1,
                        updated_at=now,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["dedup_key"],
                        index_where=text("state NOT IN ('RESOLVED', 'FAILED')"),
                    )
                    .returning(Incident.id)
                )
                inserted_id = (await session.execute(insert_stmt)).scalar_one_or_none()
                if inserted_id is not None and active_demo_run is not None:
                    active_demo_run.incident_id = inserted_id
                    if active_demo_run.status in ("QUEUED", "INJECTING_FAULT", "WAITING_FOR_ALERT"):
                        active_demo_run.status = "ACTIVE"

                if inserted_id is None:
                    # Deduplicated against existing active incident
                    existing_inc = (
                        await session.execute(
                            select(Incident).where(
                                Incident.dedup_key == dedup_key,
                                Incident.state.notin_(["RESOLVED", "FAILED"]),
                            )
                        )
                    ).scalar_one()
                    session.add(
                        IncidentEvent(
                            incident_id=existing_inc.id,
                            event_type="ALERT_DEDUPLICATED",
                            from_state=existing_inc.state,
                            to_state=existing_inc.state,
                            actor=actor,
                            details_sanitized_json={
                                "fingerprint": fingerprint,
                                "redactions": scrub_result.total_redactions,
                            },
                            created_at=now,
                        )
                    )
                    results.append(
                        {
                            "incident_id": str(existing_inc.id),
                            "dedup_key": dedup_key,
                            "action": "deduplicated",
                            "state": existing_inc.state,
                        }
                    )
                    continue

                session.add(
                    IncidentEvent(
                        incident_id=inserted_id,
                        event_type="ALERT_INGESTED",
                        from_state=None,
                        to_state=initial_state,
                        actor=actor,
                        details_sanitized_json={
                            "labels": labels,
                            "severity": severity,
                            "redaction_total": scrub_result.total_redactions,
                            "scrubber_fallback": scrub_result.scrubber_failed_fallback,
                        },
                        created_at=now,
                    )
                )
                session.add(
                    AuditRecord(
                        incident_id=inserted_id,
                        actor_sub=actor,
                        actor_role="system_webhook",
                        action_type="ALERT_INGESTED",
                        policy_decision=initial_state,
                        before_state_json=None,
                        after_state_json={"state": initial_state, "severity": severity},
                        details_json={"dedup_key": dedup_key},
                        created_at=now,
                    )
                )

                if not scrub_result.scrubber_failed_fallback:
                    session.add(
                        OutboxJob(
                            incident_id=inserted_id,
                            job_type="TRIAGE_INCIDENT",
                            dedup_job_key=f"TRIAGE_INCIDENT:{inserted_id}",
                            payload_sanitized_json={
                                "incident_id": str(inserted_id),
                                "asset_slug": asset.slug if asset else None,
                                "unknown_asset": unknown_id,
                                "labels": labels,
                                "summary_sanitized": summary_text,
                            },
                            status="PENDING",
                            available_at=now,
                            created_at=now,
                        )
                    )

                results.append(
                    {
                        "incident_id": str(inserted_id),
                        "dedup_key": dedup_key,
                        "action": "created",
                        "state": initial_state,
                        "severity": severity,
                        "redactions": scrub_result.total_redactions,
                        "source_provenance": resolved_provenance,
                    }
                )

    return JSONResponse(status_code=202, content={"accepted": len(results), "results": results})
