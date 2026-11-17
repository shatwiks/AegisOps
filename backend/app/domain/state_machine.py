"""Canonical incident state machine with DB-locked transition validation and append-only audit."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import AuditRecord, Incident, IncidentEvent


class IncidentState(StrEnum):
    """Canonical lifecycle states shared across DB, API, workers, and UI."""

    OPEN = "OPEN"
    TRIAGING = "TRIAGING"
    READY_TO_REMEDIATE = "READY_TO_REMEDIATE"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    ESCALATED = "ESCALATED"
    REMEDIATING = "REMEDIATING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"


ALLOWED_TRANSITIONS: dict[IncidentState, frozenset[IncidentState]] = {
    IncidentState.OPEN: frozenset({IncidentState.TRIAGING, IncidentState.ESCALATED}),
    IncidentState.TRIAGING: frozenset(
        {
            IncidentState.READY_TO_REMEDIATE,
            IncidentState.AWAITING_APPROVAL,
            IncidentState.ESCALATED,
            IncidentState.FAILED,
        }
    ),
    IncidentState.READY_TO_REMEDIATE: frozenset(
        {IncidentState.REMEDIATING, IncidentState.ESCALATED, IncidentState.FAILED}
    ),
    IncidentState.AWAITING_APPROVAL: frozenset(
        {IncidentState.READY_TO_REMEDIATE, IncidentState.ESCALATED, IncidentState.FAILED}
    ),
    IncidentState.ESCALATED: frozenset(
        {IncidentState.TRIAGING, IncidentState.RESOLVED, IncidentState.FAILED}
    ),
    IncidentState.REMEDIATING: frozenset(
        {IncidentState.VERIFYING, IncidentState.ESCALATED, IncidentState.FAILED}
    ),
    IncidentState.VERIFYING: frozenset(
        {IncidentState.RESOLVED, IncidentState.ESCALATED, IncidentState.FAILED}
    ),
    IncidentState.RESOLVED: frozenset(),
    IncidentState.FAILED: frozenset(),
}


class InvalidStateTransitionError(ValueError):
    """Raised when an illegal state transition is attempted."""


def validate_transition(from_state: str, to_state: str) -> None:
    """Validate that `from_state -> to_state` is permitted by the canonical state machine."""
    src = IncidentState(from_state)
    dst = IncidentState(to_state)
    if dst not in ALLOWED_TRANSITIONS[src]:
        raise InvalidStateTransitionError(
            f"Illegal incident state transition: {src.value} -> {dst.value}"
        )


async def transition_incident(
    session: AsyncSession,
    *,
    incident_id: uuid.UUID,
    to_state: IncidentState,
    actor: str,
    actor_role: str,
    event_type: str,
    policy_decision: str,
    details_sanitized: dict[str, Any] | None = None,
    timestamp_field: str | None = None,
    extra_updates: dict[str, Any] | None = None,
) -> Incident:
    """Transition an incident under row lock (`SELECT ... FOR UPDATE`), writing event + audit."""
    stmt = select(Incident).where(Incident.id == incident_id).with_for_update()
    incident = (await session.execute(stmt)).scalar_one_or_none()
    if incident is None:
        raise ValueError(f"Incident {incident_id} not found")

    validate_transition(incident.state, to_state.value)
    prev_state = incident.state
    now = datetime.now(UTC)

    incident.state = to_state.value
    incident.version_id += 1
    incident.updated_at = now

    if timestamp_field is not None:
        if not hasattr(incident, timestamp_field):
            raise ValueError(f"Unknown incident timestamp field: {timestamp_field}")
        if getattr(incident, timestamp_field) is None:
            setattr(incident, timestamp_field, now)

    if extra_updates:
        for attr, val in extra_updates.items():
            setattr(incident, attr, val)

    event = IncidentEvent(
        incident_id=incident.id,
        event_type=event_type,
        from_state=prev_state,
        to_state=to_state.value,
        actor=actor,
        details_sanitized_json=details_sanitized or {},
        created_at=now,
    )
    audit = AuditRecord(
        incident_id=incident.id,
        actor_sub=actor,
        actor_role=actor_role,
        action_type=event_type,
        policy_decision=policy_decision,
        before_state_json={"state": prev_state, "version_id": incident.version_id - 1},
        after_state_json={"state": to_state.value, "version_id": incident.version_id},
        details_json=details_sanitized or {},
        created_at=now,
    )
    session.add(event)
    session.add(audit)
    await session.flush()
    return incident
