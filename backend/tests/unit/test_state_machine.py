"""Unit tests for canonical incident state machine transitions."""

from __future__ import annotations

import pytest

from app.domain.state_machine import (
    IncidentState,
    InvalidStateTransitionError,
    validate_transition,
)


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        (IncidentState.OPEN, IncidentState.TRIAGING),
        (IncidentState.OPEN, IncidentState.ESCALATED),
        (IncidentState.TRIAGING, IncidentState.READY_TO_REMEDIATE),
        (IncidentState.TRIAGING, IncidentState.AWAITING_APPROVAL),
        (IncidentState.TRIAGING, IncidentState.ESCALATED),
        (IncidentState.AWAITING_APPROVAL, IncidentState.READY_TO_REMEDIATE),
        (IncidentState.AWAITING_APPROVAL, IncidentState.ESCALATED),
        (IncidentState.READY_TO_REMEDIATE, IncidentState.REMEDIATING),
        (IncidentState.REMEDIATING, IncidentState.VERIFYING),
        (IncidentState.VERIFYING, IncidentState.RESOLVED),
        (IncidentState.VERIFYING, IncidentState.ESCALATED),
        (IncidentState.VERIFYING, IncidentState.FAILED),
    ],
)
def test_valid_transitions_allowed(src: IncidentState, dst: IncidentState) -> None:
    validate_transition(src.value, dst.value)


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        (IncidentState.OPEN, IncidentState.RESOLVED),
        (IncidentState.OPEN, IncidentState.REMEDIATING),
        (IncidentState.OPEN, IncidentState.VERIFYING),
        (IncidentState.TRIAGING, IncidentState.RESOLVED),
        (IncidentState.AWAITING_APPROVAL, IncidentState.REMEDIATING),
        (IncidentState.AWAITING_APPROVAL, IncidentState.RESOLVED),
        (IncidentState.READY_TO_REMEDIATE, IncidentState.RESOLVED),
        (IncidentState.REMEDIATING, IncidentState.RESOLVED),
        (IncidentState.RESOLVED, IncidentState.OPEN),
        (IncidentState.RESOLVED, IncidentState.TRIAGING),
        (IncidentState.FAILED, IncidentState.REMEDIATING),
    ],
)
def test_illegal_transitions_rejected(src: IncidentState, dst: IncidentState) -> None:
    with pytest.raises(InvalidStateTransitionError):
        validate_transition(src.value, dst.value)
