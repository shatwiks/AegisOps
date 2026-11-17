"""Authenticated Server-Sent Events (SSE) stream with sequence catch-up and live verification progress."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, func, select

from app.auth.oidc import AuthenticatedUser, require_role
from app.models.entities import Asset, DemoRun, Incident, IncidentEvent

router = APIRouter(prefix="/api/v1/stream", tags=["stream"])


@router.get("/incidents")
async def stream_incidents(
    request: Request,
    after_seq: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    _: AuthenticatedUser = Depends(require_role("viewer")),
) -> StreamingResponse:
    """Stream sanitized incident/run snapshots with monotonic sequence_num catch-up."""
    resume_seq = after_seq
    if last_event_id and last_event_id.isdigit():
        resume_seq = max(resume_seq, int(last_event_id))

    async def _event_gen() -> AsyncGenerator[str, None]:
        nonlocal resume_seq
        last_digest = ""
        while True:
            if await request.is_disconnected():
                break

            async with request.app.state.session_factory() as session:
                rows = (
                    await session.execute(
                        select(Incident, Asset.slug)
                        .outerjoin(Asset, Incident.primary_asset_id == Asset.id)
                        .order_by(desc(Incident.updated_at))
                        .limit(30)
                    )
                ).all()

                max_seq = int(
                    (await session.execute(select(func.max(IncidentEvent.sequence_num)))).scalar_one()
                    or 0
                )
                delta_events = (
                    (
                        await session.execute(
                            select(IncidentEvent)
                            .where(IncidentEvent.sequence_num > resume_seq)
                            .order_by(IncidentEvent.sequence_num.asc())
                            .limit(50)
                        )
                    )
                    .scalars()
                    .all()
                )
                active_runs = (
                    (
                        await session.execute(
                            select(DemoRun)
                            .order_by(DemoRun.started_at.desc())
                            .limit(10)
                        )
                    )
                    .scalars()
                    .all()
                )

            payload = {
                "latest_seq": max_seq,
                "incidents": [
                    {
                        "id": str(inc.id),
                        "title": inc.title,
                        "asset_slug": slug or inc.unknown_asset_identifier,
                        "severity": inc.severity,
                        "state": inc.state,
                        "source_provenance": inc.source_provenance,
                        "verification_state": inc.verification_state_json or {},
                        "version_id": inc.version_id,
                        "updated_at": inc.updated_at.isoformat(),
                    }
                    for inc, slug in rows
                ],
                "delta_events": [
                    {
                        "id": str(e.id),
                        "sequence_num": e.sequence_num,
                        "incident_id": str(e.incident_id),
                        "event_type": e.event_type,
                        "to_state": e.to_state,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in delta_events
                ],
                "demo_runs": [
                    {
                        "id": str(r.id),
                        "scenario_id": r.scenario_id,
                        "target_service": r.target_service,
                        "status": r.status,
                        "incident_id": str(r.incident_id) if r.incident_id else None,
                    }
                    for r in active_runs
                ],
            }
            digest = json.dumps(payload, sort_keys=True)
            if digest != last_digest:
                last_digest = digest
                resume_seq = max(resume_seq, max_seq)
                yield f"id: {resume_seq}\nevent: incidents_snapshot\ndata: {digest}\n\n"
            else:
                yield ": keepalive\n\n"

            await asyncio.sleep(2.0)

    return StreamingResponse(
        _event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
