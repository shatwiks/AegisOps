"""Single-use, action-bound, TOTP step-up approval and denial routes for high-risk actions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.oidc import AuthenticatedUser, require_role
from app.auth.totp import verify_and_consume_totp
from app.config import Settings
from app.domain.state_machine import IncidentState, transition_incident
from app.k8s.executor import KubernetesExecutor
from app.models.entities import ApprovalRequest, Asset, AuditRecord, Incident, OutboxJob

router = APIRouter(prefix="/api/v1/incidents", tags=["approvals"])


class ApproveActionRequest(BaseModel):
    otp_code: str = Field(min_length=6, max_length=6)
    expected_playbook_id: str = Field(min_length=2)
    expected_target_slug: str = Field(min_length=2)
    expected_parameters_hash: str | None = None
    reason: str = Field(default="SRE step-up MFA approval", min_length=3, max_length=300)


class DenyActionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/{incident_id}/approve")
async def approve_high_risk_action(
    incident_id: uuid.UUID,
    body: ApproveActionRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_role("approver")),
) -> dict[str, Any]:
    """Atomically verify TOTP, bind target UID/resourceVersion, consume approval, and enqueue job."""
    settings: Settings = request.app.state.settings
    executor = KubernetesExecutor(settings)
    now = datetime.now(UTC)

    async with request.app.state.session_factory() as session, session.begin():
        incident = (
            await session.execute(
                select(Incident).where(Incident.id == incident_id).with_for_update()
            )
        ).scalar_one_or_none()
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")

        if incident.state != IncidentState.AWAITING_APPROVAL.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Incident is in state '{incident.state}', not AWAITING_APPROVAL",
            )

        approval = (
            await session.execute(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.incident_id == incident.id,
                    ApprovalRequest.status == "PENDING",
                )
                .order_by(ApprovalRequest.requested_at.desc())
                .with_for_update()
                .limit(1)
            )
        ).scalar_one_or_none()

        if approval is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No pending ApprovalRequest found (already consumed or invalidated)",
            )

        if approval.expires_at <= now:
            approval.status = "EXPIRED"
            await transition_incident(
                session,
                incident_id=incident.id,
                to_state=IncidentState.ESCALATED,
                actor=user.email,
                actor_role=user.highest_role,
                event_type="APPROVAL_EXPIRED",
                policy_decision="EXPIRED",
                details_sanitized={"approval_id": str(approval.id)},
                extra_updates={"refusal_reason": "Approval request expired before MFA decision"},
            )
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Approval request expired; incident escalated",
            )

        # Verify action binding
        if (
            approval.playbook_id != body.expected_playbook_id
            or approval.target_asset_slug != body.expected_target_slug
            or (
                body.expected_parameters_hash is not None
                and approval.parameters_hash != body.expected_parameters_hash
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Approval action/target/parameters mismatch",
            )

        # Verify target Kubernetes UID & resourceVersion have not drifted since approval request
        asset = (
            await session.execute(select(Asset).where(Asset.id == incident.primary_asset_id))
        ).scalar_one()
        if not approval.target_k8s_uid.startswith("unfetched-"):
            snap = await executor.read_deployment_snapshot(
                cluster=asset.cluster,
                namespace=asset.namespace,
                deployment_name=asset.k8s_deployment_name or asset.name,
            )
            if (
                snap.uid != approval.target_k8s_uid
                or snap.resource_version != approval.target_resource_version
            ):
                approval.status = "INVALIDATED"
                approval.reason = "Target Kubernetes object changed after approval request"
                await transition_incident(
                    session,
                    incident_id=incident.id,
                    to_state=IncidentState.ESCALATED,
                    actor=user.email,
                    actor_role=user.highest_role,
                    event_type="APPROVAL_INVALIDATED_TARGET_DRIFT",
                    policy_decision="INVALIDATED",
                    details_sanitized={
                        "expected_rv": approval.target_resource_version,
                        "actual_rv": snap.resource_version,
                    },
                    extra_updates={
                        "refusal_reason": "Target Deployment changed during approval window; re-triage required"
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Target Kubernetes resourceVersion/UID changed; approval invalidated",
                )

        # Verify & atomically consume TOTP (rejects invalid, locked, or replayed OTP)
        timecode = await verify_and_consume_totp(
            session,
            user_sub=user.sub,
            otp_code=body.otp_code,
            settings=settings,
            activate_enrollment=False,
        )

        approval.status = "CONSUMED"
        approval.decided_by_sub = user.sub
        approval.decided_by_email = user.email
        approval.decided_by_role = user.highest_role
        approval.totp_timecode_used = timecode
        approval.decided_at = now
        approval.consumed_at = now
        approval.reason = body.reason

        await transition_incident(
            session,
            incident_id=incident.id,
            to_state=IncidentState.READY_TO_REMEDIATE,
            actor=user.email,
            actor_role=user.highest_role,
            event_type="MFA_APPROVAL_GRANTED",
            policy_decision="APPROVED_AND_CONSUMED",
            timestamp_field="approved_at",
            details_sanitized={
                "approval_id": str(approval.id),
                "playbook_id": approval.playbook_id,
                "parameters_hash": approval.parameters_hash,
                "target_uid": approval.target_k8s_uid,
                "target_rv": approval.target_resource_version,
            },
        )

        session.add(
            OutboxJob(
                incident_id=incident.id,
                job_type="EXECUTE_REMEDIATION",
                dedup_job_key=f"EXECUTE_REMEDIATION:{incident.id}:{approval.id}",
                payload_sanitized_json={
                    "incident_id": str(incident.id),
                    "approval_id": str(approval.id),
                    "playbook_id": approval.playbook_id,
                },
                status="PENDING",
                available_at=now,
            )
        )

    return {
        "approved": True,
        "incident_id": str(incident_id),
        "approval_id": str(approval.id),
        "new_state": IncidentState.READY_TO_REMEDIATE.value,
        "approved_by": user.email,
    }


@router.post("/{incident_id}/deny")
async def deny_high_risk_action(
    incident_id: uuid.UUID,
    body: DenyActionRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_role("approver")),
) -> dict[str, Any]:
    """Explicitly deny a pending high-risk approval and escalate the incident."""
    now = datetime.now(UTC)
    async with request.app.state.session_factory() as session, session.begin():
        incident = (
            await session.execute(
                select(Incident).where(Incident.id == incident_id).with_for_update()
            )
        ).scalar_one_or_none()
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        if incident.state != IncidentState.AWAITING_APPROVAL.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Incident is in state '{incident.state}', not AWAITING_APPROVAL",
            )

        approval = (
            await session.execute(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.incident_id == incident.id,
                    ApprovalRequest.status == "PENDING",
                )
                .with_for_update()
                .limit(1)
            )
        ).scalar_one_or_none()
        if approval is not None:
            approval.status = "DENIED"
            approval.decided_by_sub = user.sub
            approval.decided_by_email = user.email
            approval.decided_by_role = user.highest_role
            approval.decided_at = now
            approval.reason = body.reason

        await transition_incident(
            session,
            incident_id=incident.id,
            to_state=IncidentState.ESCALATED,
            actor=user.email,
            actor_role=user.highest_role,
            event_type="MFA_APPROVAL_DENIED",
            policy_decision="DENIED",
            details_sanitized={"reason": body.reason},
            extra_updates={"refusal_reason": f"Denied by {user.email}: {body.reason}"},
        )
        session.add(
            AuditRecord(
                incident_id=incident.id,
                actor_sub=user.sub,
                actor_role=user.highest_role,
                action_type="APPROVAL_DENIED",
                policy_decision="ESCALATED",
                details_json={"reason": body.reason},
            )
        )

    return {
        "denied": True,
        "incident_id": str(incident_id),
        "new_state": IncidentState.ESCALATED.value,
    }
