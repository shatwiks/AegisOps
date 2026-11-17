"""Incident query endpoints returning filtered queues, 7-step lifecycle, decision evidence & diffs."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import Text, asc, case, cast, desc, func, or_, select

from app.auth.oidc import AuthenticatedUser, require_role
from app.cmdb.graph import BlastRadiusResult, get_blast_radius
from app.models.entities import (
    ApprovalRequest,
    Asset,
    AuditRecord,
    BusinessProbeSample,
    ExecutionAttempt,
    Incident,
    IncidentEvent,
)
from app.showcase.postmortem import (
    build_postmortem_snapshot,
    render_postmortem_markdown,
    render_postmortem_pdf,
)

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])

ACTIVE_STATES: tuple[str, ...] = (
    "OPEN",
    "TRIAGING",
    "READY_TO_REMEDIATE",
    "AWAITING_APPROVAL",
    "REMEDIATING",
    "VERIFYING",
)


def serialize_incident(inc: Incident, asset_slug: str | None) -> dict[str, Any]:
    """Serialize sanitized incident record with provenance and verification snapshot."""
    return {
        "id": str(inc.id),
        "dedup_key": inc.dedup_key,
        "alert_fingerprint": inc.alert_fingerprint,
        "alertname": inc.alertname,
        "title": inc.title,
        "summary_sanitized": inc.summary_sanitized,
        "asset_slug": asset_slug or inc.unknown_asset_identifier,
        "unknown_asset_identifier": inc.unknown_asset_identifier,
        "severity": inc.severity,
        "severity_explanation": inc.severity_explanation_json,
        "state": inc.state,
        "source_provenance": inc.source_provenance,
        "demo_run_id": str(inc.demo_run_id) if inc.demo_run_id else None,
        "proposed_playbook_id": inc.proposed_playbook_id,
        "proposed_parameters": inc.proposed_parameters_json,
        "confidence_score": inc.confidence_score,
        "refusal_reason": inc.refusal_reason,
        "diagnosis": inc.diagnosis_json,
        "has_captured_prompt": bool((inc.sanitized_prompt_json or {}).get("captured")),
        "redaction_stats": inc.redaction_stats_json,
        "verification_state": inc.verification_state_json or {},
        "fault_onset_at": inc.fault_onset_at.isoformat() if inc.fault_onset_at else None,
        "detected_at": inc.detected_at.isoformat() if inc.detected_at else None,
        "ingested_at": inc.ingested_at.isoformat(),
        "triaged_at": inc.triaged_at.isoformat() if inc.triaged_at else None,
        "approved_at": inc.approved_at.isoformat() if inc.approved_at else None,
        "mutated_at": inc.mutated_at.isoformat() if inc.mutated_at else None,
        "first_recovered_at": inc.first_recovered_at.isoformat()
        if inc.first_recovered_at
        else None,
        "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
        "version_id": inc.version_id,
        "updated_at": inc.updated_at.isoformat(),
    }


def compute_lifecycle_steps(
    inc: Incident,
    events: list[IncidentEvent],
    approvals: list[ApprovalRequest],
    executions: list[ExecutionAttempt],
) -> list[dict[str, Any]]:
    """Derive deterministic 7-step lifecycle milestones strictly from persisted backend state."""
    evt_types = {e.event_type for e in events}
    redaction_stats = inc.redaction_stats_json or {}
    total_redactions = int(redaction_stats.get("total_redactions", 0))
    scrubber_fallback = bool(redaction_stats.get("scrubber_failed_fallback", False))

    diag = inc.diagnosis_json or {}
    citations = diag.get("citations") or []
    proposal = diag.get("proposal")
    checks = diag.get("policy_checks") or {}
    verif = inc.verification_state_json or {}
    manual_reset_assisted = "BASELINE_RESET_ASSISTED_CLOSE" in evt_types or (
        "manual_reset_assisted" in (inc.refusal_reason or "").lower()
    )

    # Step 1: Alert Caught
    step1 = {
        "key": "alert_caught",
        "step": 1,
        "label": "Alert caught",
        "status": "completed",
        "summary": f"{inc.alertname} ingested ({inc.source_provenance}).",
        "timestamp": inc.ingested_at.isoformat(),
        "evidence": {"severity": inc.severity, "provenance": inc.source_provenance},
    }

    # Step 2: Privacy Scrubbed
    step2 = {
        "key": "privacy_scrubbed",
        "step": 2,
        "label": "Sensitive data checked & scrubbed",
        "status": "failed" if scrubber_fallback else "completed",
        "summary": (
            "Boundary scrubber fail-closed fallback triggered."
            if scrubber_fallback
            else (
                "0 sensitive identifier patterns detected in payload."
                if total_redactions == 0
                else f"{total_redactions} sensitive identifier token(s) scrubbed before AI/persistence."
            )
        ),
        "timestamp": inc.ingested_at.isoformat(),
        "evidence": redaction_stats,
    }

    # Step 3: Impact Mapped
    sev_expl = inc.severity_explanation_json or {}
    downstream = sev_expl.get("downstream_impact_slugs") or []
    step3 = {
        "key": "impact_mapped",
        "step": 3,
        "label": "Service impact mapped",
        "status": "completed",
        "summary": (
            f"Unknown asset '{inc.unknown_asset_identifier}' quarantined as {inc.severity}."
            if inc.unknown_asset_identifier
            else f"Assigned {inc.severity}; {len(downstream)} downstream service(s) in CMDB blast radius."
        ),
        "timestamp": inc.ingested_at.isoformat(),
        "evidence": sev_expl,
    }

    # Step 4: Retrieval & AI Diagnosis
    if inc.triaged_at is not None or citations or proposal is not None:
        if proposal is not None:
            s4_status = "completed"
            s4_summary = f"Retrieved {len(citations)} doc(s); structured diagnosis generated."
        else:
            s4_status = "failed"
            s4_summary = (
                f"Retrieved {len(citations)} doc(s), but model diagnosis failed/timed out."
            )
    elif inc.state == "TRIAGING":
        s4_status = "running"
        s4_summary = "Searching hybrid runbooks and running local LLM diagnosis..."
    elif inc.state in ("ESCALATED", "FAILED"):
        s4_status = "not_applicable"
        s4_summary = "Incident halted prior to AI triage."
    else:
        s4_status = "pending"
        s4_summary = "Queued for hybrid retrieval and structured diagnosis."
    step4 = {
        "key": "knowledge_and_ai",
        "step": 4,
        "label": "Runbooks retrieved & AI diagnosis",
        "status": s4_status,
        "summary": s4_summary,
        "timestamp": inc.triaged_at.isoformat() if inc.triaged_at else None,
        "evidence": {
            "citations_count": len(citations),
            "model_succeeded": proposal is not None,
        },
    }

    # Step 5: Policy & MFA Gate / Execution
    latest_appr = approvals[0] if approvals else None
    latest_exec = executions[0] if executions else None
    pause_held = "AUTOMATION_PAUSED_HOLD" in evt_types and inc.state == "READY_TO_REMEDIATE"

    if pause_held:
        s5_status = "blocked"
        s5_summary = "Execution paused by operator automation control flag."
    elif inc.state == "AWAITING_APPROVAL":
        s5_status = "running"
        s5_summary = f"Awaiting step-up TOTP MFA approval for '{inc.proposed_playbook_id}'."
    elif latest_appr and latest_appr.status == "DENIED":
        s5_status = "blocked"
        s5_summary = f"MFA approval denied by {latest_appr.decided_by_email or 'approver'}."
    elif inc.state == "ESCALATED" and not executions:
        s5_status = "blocked"
        s5_summary = inc.refusal_reason or "Policy engine refused automated remediation."
    elif inc.state == "REMEDIATING":
        s5_status = "running"
        s5_summary = f"Executing '{inc.proposed_playbook_id}' on Kubernetes..."
    elif latest_exec is not None:
        if latest_exec.status in ("SUCCEEDED", "RECONCILED_SUCCEEDED"):
            s5_status = "completed"
            s5_summary = f"Executed '{latest_exec.playbook_id}' ({latest_exec.status})."
        else:
            s5_status = "failed"
            s5_summary = f"Execution '{latest_exec.playbook_id}' failed ({latest_exec.status})."
    elif inc.state == "READY_TO_REMEDIATE":
        s5_status = "running"
        s5_summary = f"Policy approved '{inc.proposed_playbook_id}'; awaiting worker execution."
    elif inc.state in ("OPEN", "TRIAGING"):
        s5_status = "pending"
        s5_summary = "Waiting for policy evaluation."
    else:
        s5_status = "not_applicable"
        s5_summary = "No automated remediation executed."

    step5 = {
        "key": "policy_and_approval",
        "step": 5,
        "label": "Policy decision & execution",
        "status": s5_status,
        "summary": s5_summary,
        "timestamp": (
            inc.mutated_at.isoformat()
            if inc.mutated_at
            else (inc.approved_at.isoformat() if inc.approved_at else None)
        ),
        "evidence": {
            "policy_checks": checks,
            "approval_status": latest_appr.status if latest_appr else None,
            "execution_status": latest_exec.status if latest_exec else None,
        },
    }

    # Step 6: Sustained Recovery Verification
    win_sec = float(verif.get("window_seconds", 60.0))
    elapsed_sec = float(verif.get("elapsed_healthy_seconds", 0.0))
    resets = int(verif.get("reset_count", 0))
    v_status = str(verif.get("status", ""))

    if inc.state == "VERIFYING" or v_status == "observing":
        s6_status = "running"
        reset_note = f" (window reset {resets}x)" if resets > 0 else ""
        s6_summary = (
            f"Checking service stability: {int(round(elapsed_sec))} of {int(win_sec)} seconds observed{reset_note}."
        )
    elif inc.state == "RESOLVED" and not manual_reset_assisted:
        s6_status = "completed"
        s6_summary = f"Sustained health confirmed over {int(win_sec)}s window ({verif.get('sample_count', 1)} samples)."
    elif "RECOVERY_VERIFICATION_FAILED" in evt_types or v_status == "failed":
        s6_status = "failed"
        s6_summary = str(verif.get("last_reset_reason") or inc.refusal_reason or "Verification window failed.")
    elif inc.state in ("ESCALATED", "FAILED") or manual_reset_assisted:
        s6_status = "not_applicable"
        s6_summary = (
            "Skipped due to manual baseline reset."
            if manual_reset_assisted
            else "Not reached; incident requires human intervention."
        )
    else:
        s6_status = "pending"
        s6_summary = f"Awaiting post-remediation {int(win_sec)}s stability check."

    step6 = {
        "key": "recovery_verification",
        "step": 6,
        "label": "Recovery verification",
        "status": s6_status,
        "summary": s6_summary,
        "timestamp": inc.first_recovered_at.isoformat() if inc.first_recovered_at else None,
        "evidence": verif,
    }

    # Step 7: Terminal Outcome (never fake green Resolved on Escalated/Failed!)
    if inc.state == "RESOLVED":
        s7_status = "completed"
        s7_summary = (
            "Closed via operator baseline reset (manual_reset_assisted)."
            if manual_reset_assisted
            else "Verified resolution confirmed; all health probes sustained."
        )
    elif inc.state == "ESCALATED":
        s7_status = "blocked"
        s7_summary = inc.refusal_reason or "Escalated to human SRE/DBA."
    elif inc.state == "FAILED":
        s7_status = "failed"
        s7_summary = inc.refusal_reason or "Incident closed as failed."
    else:
        s7_status = "pending"
        s7_summary = f"In progress ({inc.state})."

    step7 = {
        "key": "terminal_outcome",
        "step": 7,
        "label": "Verified resolution" if inc.state != "ESCALATED" else "Human escalation",
        "status": s7_status,
        "summary": s7_summary,
        "timestamp": inc.resolved_at.isoformat() if inc.resolved_at else None,
        "evidence": {"terminal_state": inc.state, "manual_reset_assisted": manual_reset_assisted},
    }

    return [step1, step2, step3, step4, step5, step6, step7]


def build_why_this_action(
    inc: Incident,
    blast: BlastRadiusResult | None,
    approvals: list[ApprovalRequest],
    executions: list[ExecutionAttempt],
    probes: list[BusinessProbeSample] | None = None,
) -> dict[str, Any]:
    """Build structured 7-question decision evidence separating AI hypothesis from server policy."""
    diag = inc.diagnosis_json or {}
    proposal = diag.get("proposal") or {}
    citations = diag.get("citations") or []
    checks = diag.get("policy_checks") or {}
    latest_appr = approvals[0] if approvals else None
    latest_exec = executions[0] if executions else None

    failed_probes = [
        p for p in (probes or []) if p.status in ("FAIL", "DEGRADED")
    ]
    recovered_probes = [p for p in (probes or []) if p.status == "PASS"]

    return {
        "ai_recommendation_hypothesis": {
            "root_cause_summary": proposal.get("root_cause_summary"),
            "proposed_playbook_id": proposal.get("proposed_playbook_id"),
            "uncertainty_level": proposal.get("uncertainty_level"),
            "reasoning": proposal.get("reasoning"),
            "note": "Model output is an untrusted hypothesis until validated by server policy.",
        },
        "policy_authorization": {
            "proposed_playbook_id": inc.proposed_playbook_id,
            "proposed_parameters": inc.proposed_parameters_json,
            "checks": checks,
            "refusal_reason": inc.refusal_reason,
            "state": inc.state,
        },
        "questions": {
            "what_failed": {
                "alertname": inc.alertname,
                "target_asset": inc.asset_slug if hasattr(inc, "asset_slug") else (blast.root_asset.slug if blast and blast.root_asset else inc.unknown_asset_identifier),
                "severity": inc.severity,
                "diagnosis_hypothesis": proposal.get("root_cause_summary") or inc.summary_sanitized,
            },
            "why_system_thinks_so": {
                "sanitized_summary": inc.summary_sanitized,
                "evidence_quotes": proposal.get("evidence_quotes") or [],
                "citations": citations,
                "failing_probes_count": len(failed_probes),
            },
            "recommended_action": {
                "playbook_id": inc.proposed_playbook_id,
                "bounded_parameters": inc.proposed_parameters_json or {},
            },
            "why_allowed_or_blocked": {
                "decision_checks": checks,
                "refusal_reason": inc.refusal_reason,
                "automation_paused": bool(checks.get("automation_paused", False)),
            },
            "why_mfa_required": {
                "required": latest_appr is not None or checks.get("risk_tier") == "HIGH",
                "rule": (
                    "HIGH-risk actions (memory limit patches and image rollbacks) require authenticated approver + single-use action-bound TOTP step-up MFA."
                    if (latest_appr is not None or checks.get("risk_tier") == "HIGH")
                    else "LOW-risk allowlisted action or escalated refusal."
                ),
                "approval_status": latest_appr.status if latest_appr else None,
            },
            "what_can_prevent_execution": [
                r
                for r in (
                    [inc.refusal_reason] if inc.refusal_reason else []
                )
                + (
                    ["Waiting for valid approver TOTP MFA submission"]
                    if inc.state == "AWAITING_APPROVAL"
                    else []
                )
                + (
                    ["Automation paused by operator control flag"]
                    if checks.get("automation_paused")
                    else []
                )
            ],
            "what_happened_afterward": {
                "execution_status": latest_exec.status if latest_exec else None,
                "before_state": latest_exec.before_state_sanitized_json if latest_exec else None,
                "after_state": latest_exec.after_state_sanitized_json if latest_exec else None,
                "verification_state": inc.verification_state_json or {},
                "recovered_probes_count": len(recovered_probes),
                "final_state": inc.state,
            },
        },
    }


def _apply_incident_filters(
    stmt: Any,
    *,
    hide_test_runs: bool,
    provenance: str | None,
    severity: str | None,
    service: str | None,
    search: str | None,
) -> Any:
    if provenance:
        stmt = stmt.where(Incident.source_provenance == provenance)
    elif hide_test_runs:
        stmt = stmt.where(Incident.source_provenance != "automated_test")

    if severity:
        stmt = stmt.where(Incident.severity == severity.upper())

    if service:
        stmt = stmt.where(
            or_(Asset.slug == service, Incident.unknown_asset_identifier == service)
        )

    if search and search.strip():
        q = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Incident.title.ilike(q),
                Incident.alertname.ilike(q),
                cast(Incident.id, Text).ilike(q),
                func.coalesce(cast(Incident.demo_run_id, Text), "").ilike(q),
            )
        )
    return stmt


@router.get("")
async def list_incidents(
    request: Request,
    tab: str = Query(default="all"),
    state: str | None = Query(default=None),
    hide_test_runs: bool = Query(default=True),
    provenance: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    service: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort: str = Query(default="newest"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    _: AuthenticatedUser = Depends(require_role("viewer")),
) -> dict[str, Any]:
    """List incidents with server-side tab filters, Hide Test Runs, search, sorting & SQL tab counts."""
    async with request.app.state.session_factory() as session:
        # Compute SQL tab counts under current non-tab filters
        count_stmt = (
            select(Incident.state, func.count(Incident.id))
            .outerjoin(Asset, Incident.primary_asset_id == Asset.id)
            .group_by(Incident.state)
        )
        count_stmt = _apply_incident_filters(
            count_stmt,
            hide_test_runs=hide_test_runs,
            provenance=provenance,
            severity=severity,
            service=service,
            search=search,
        )
        state_counts = {str(s): int(c) for s, c in (await session.execute(count_stmt)).all()}

        hidden_stmt = select(func.count(Incident.id)).where(
            Incident.source_provenance == "automated_test"
        )
        hidden_test_count = int((await session.execute(hidden_stmt)).scalar_one() or 0)

        tab_counts = {
            "active": sum(state_counts.get(s, 0) for s in ACTIVE_STATES),
            "resolved": state_counts.get("RESOLVED", 0),
            "escalated": state_counts.get("ESCALATED", 0),
            "failed": state_counts.get("FAILED", 0),
            "all": sum(state_counts.values()),
            "hidden_test_count": hidden_test_count,
        }

        stmt = select(Incident, Asset.slug).outerjoin(
            Asset, Incident.primary_asset_id == Asset.id
        )
        stmt = _apply_incident_filters(
            stmt,
            hide_test_runs=hide_test_runs,
            provenance=provenance,
            severity=severity,
            service=service,
            search=search,
        )

        norm_tab = tab.strip().lower()
        if state:
            stmt = stmt.where(Incident.state == state)
        elif norm_tab == "active":
            stmt = stmt.where(Incident.state.in_(ACTIVE_STATES))
        elif norm_tab == "resolved":
            stmt = stmt.where(Incident.state == "RESOLVED")
        elif norm_tab == "escalated":
            stmt = stmt.where(Incident.state == "ESCALATED")
        elif norm_tab == "failed":
            stmt = stmt.where(Incident.state == "FAILED")

        if sort == "oldest":
            stmt = stmt.order_by(asc(Incident.ingested_at))
        elif sort == "severity":
            sev_order = case(
                (Incident.severity == "P1", 1),
                (Incident.severity == "P2", 2),
                (Incident.severity == "P3", 3),
                else_=4,
            )
            stmt = stmt.order_by(sev_order.asc(), desc(Incident.ingested_at))
        else:
            stmt = stmt.order_by(desc(Incident.ingested_at))

        total_filtered = tab_counts.get(norm_tab, tab_counts["all"])
        rows = (await session.execute(stmt.offset(offset).limit(limit))).all()

    return {
        "items": [serialize_incident(inc, slug) for inc, slug in rows],
        "total_filtered": total_filtered,
        "tab_counts": tab_counts,
        "pagination": {
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(rows)) < total_filtered,
        },
        "filters": {
            "tab": norm_tab,
            "hide_test_runs": hide_test_runs,
            "provenance": provenance,
            "severity": severity,
            "service": service,
            "search": search,
            "sort": sort,
        },
    }


@router.get("/{incident_id}")
async def get_incident_detail(
    incident_id: uuid.UUID,
    request: Request,
    _: AuthenticatedUser = Depends(require_role("viewer")),
) -> dict[str, Any]:
    """Fetch complete incident detail, 7-step lifecycle, decision explanation, events, approvals, executions & diffs."""
    async with request.app.state.session_factory() as session:
        row = (
            await session.execute(
                select(Incident, Asset.slug)
                .outerjoin(Asset, Incident.primary_asset_id == Asset.id)
                .where(Incident.id == incident_id)
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        inc, asset_slug = row

        events = (
            (
                await session.execute(
                    select(IncidentEvent)
                    .where(IncidentEvent.incident_id == inc.id)
                    .order_by(IncidentEvent.sequence_num.asc(), IncidentEvent.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        approvals = (
            (
                await session.execute(
                    select(ApprovalRequest)
                    .where(ApprovalRequest.incident_id == inc.id)
                    .order_by(ApprovalRequest.requested_at.desc())
                )
            )
            .scalars()
            .all()
        )
        executions = (
            (
                await session.execute(
                    select(ExecutionAttempt)
                    .where(ExecutionAttempt.incident_id == inc.id)
                    .order_by(ExecutionAttempt.started_at.desc())
                )
            )
            .scalars()
            .all()
        )
        audits = (
            (
                await session.execute(
                    select(AuditRecord)
                    .where(AuditRecord.incident_id == inc.id)
                    .order_by(AuditRecord.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        probes = (
            (
                await session.execute(
                    select(BusinessProbeSample)
                    .where(BusinessProbeSample.incident_id == inc.id)
                    .order_by(BusinessProbeSample.checked_at.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )

        blast = await get_blast_radius(session, asset_slug) if asset_slug else None

    lifecycle_steps = compute_lifecycle_steps(inc, events, approvals, executions)
    why_this_action = build_why_this_action(inc, blast, approvals, executions, probes)

    return {
        "incident": serialize_incident(inc, asset_slug),
        "lifecycle_steps": lifecycle_steps,
        "why_this_action": why_this_action,
        "business_probes": [
            {
                "id": str(p.id),
                "target_service": p.target_service,
                "endpoint_path": p.endpoint_path,
                "probe_type": p.probe_type,
                "status": p.status,
                "http_status": p.http_status,
                "latency_ms": p.latency_ms,
                "summary": p.summary_sanitized,
                "checked_at": p.checked_at.isoformat(),
            }
            for p in probes
        ],
        "events": [
            {
                "id": str(e.id),
                "sequence_num": e.sequence_num,
                "event_type": e.event_type,
                "from_state": e.from_state,
                "to_state": e.to_state,
                "actor": e.actor,
                "details": e.details_sanitized_json,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ],
        "approvals": [
            {
                "id": str(a.id),
                "playbook_id": a.playbook_id,
                "playbook_version": a.playbook_version,
                "parameters_hash": a.parameters_hash,
                "parameters": a.parameters_json,
                "target_asset_slug": a.target_asset_slug,
                "target_k8s_uid": a.target_k8s_uid,
                "target_resource_version": a.target_resource_version,
                "status": a.status,
                "requested_at": a.requested_at.isoformat(),
                "expires_at": a.expires_at.isoformat(),
                "decided_by_email": a.decided_by_email,
                "decided_at": a.decided_at.isoformat() if a.decided_at else None,
                "reason": a.reason,
            }
            for a in approvals
        ],
        "executions": [
            {
                "id": str(ex.id),
                "playbook_id": ex.playbook_id,
                "status": ex.status,
                "before_state": ex.before_state_sanitized_json,
                "after_state": ex.after_state_sanitized_json,
                "error": ex.error_message_sanitized,
                "started_at": ex.started_at.isoformat(),
                "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
            }
            for ex in executions
        ],
        "audits": [
            {
                "id": str(au.id),
                "actor_sub": au.actor_sub,
                "actor_role": au.actor_role,
                "action_type": au.action_type,
                "policy_decision": au.policy_decision,
                "created_at": au.created_at.isoformat(),
            }
            for au in audits
        ],
        "blast_radius": {
            "upstream_dependencies": [
                {"slug": n.slug, "criticality": n.criticality, "hop": n.hop_distance}
                for n in (blast.upstream_dependencies if blast else [])
            ],
            "downstream_impacts": [
                {"slug": n.slug, "criticality": n.criticality, "hop": n.hop_distance}
                for n in (blast.downstream_impacts if blast else [])
            ],
            "truncated": blast.truncated if blast else False,
            "cycle_detected": blast.cycle_detected if blast else False,
        },
    }


@router.get("/{incident_id}/prompt")
async def get_incident_prompt_inspector(
    incident_id: uuid.UUID,
    request: Request,
    _: AuthenticatedUser = Depends(require_role("viewer")),
) -> dict[str, Any]:
    """Return exact captured sanitized prompt/model record + 7-question decision rationale (`viewer+`)."""
    async with request.app.state.session_factory() as session:
        row = (
            await session.execute(
                select(Incident, Asset.slug)
                .outerjoin(Asset, Incident.primary_asset_id == Asset.id)
                .where(Incident.id == incident_id)
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        inc, asset_slug = row

        approvals = (
            (
                await session.execute(
                    select(ApprovalRequest)
                    .where(ApprovalRequest.incident_id == inc.id)
                    .order_by(ApprovalRequest.requested_at.desc())
                )
            )
            .scalars()
            .all()
        )
        executions = (
            (
                await session.execute(
                    select(ExecutionAttempt)
                    .where(ExecutionAttempt.incident_id == inc.id)
                    .order_by(ExecutionAttempt.started_at.desc())
                )
            )
            .scalars()
            .all()
        )
        probes = (
            (
                await session.execute(
                    select(BusinessProbeSample)
                    .where(BusinessProbeSample.incident_id == inc.id)
                    .order_by(BusinessProbeSample.checked_at.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        blast = await get_blast_radius(session, asset_slug) if asset_slug else None

    raw_rec = inc.sanitized_prompt_json or {}
    captured = bool(raw_rec.get("captured"))
    return {
        "incident_id": str(inc.id),
        "captured": captured,
        "message": None if captured else "Prompt record not captured for this historical incident.",
        "prompt_record": raw_rec if captured else None,
        "why_this_action": build_why_this_action(inc, blast, approvals, executions, probes),
    }


async def _load_postmortem_snapshot(incident_id: uuid.UUID, request: Request) -> dict[str, Any]:
    async with request.app.state.session_factory() as session:
        row = (
            await session.execute(
                select(Incident, Asset.slug)
                .outerjoin(Asset, Incident.primary_asset_id == Asset.id)
                .where(Incident.id == incident_id)
            )
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        inc, asset_slug = row

        events = (
            (
                await session.execute(
                    select(IncidentEvent)
                    .where(IncidentEvent.incident_id == inc.id)
                    .order_by(IncidentEvent.sequence_num.asc(), IncidentEvent.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        approvals = (
            (
                await session.execute(
                    select(ApprovalRequest)
                    .where(ApprovalRequest.incident_id == inc.id)
                    .order_by(ApprovalRequest.requested_at.desc())
                )
            )
            .scalars()
            .all()
        )
        executions = (
            (
                await session.execute(
                    select(ExecutionAttempt)
                    .where(ExecutionAttempt.incident_id == inc.id)
                    .order_by(ExecutionAttempt.started_at.desc())
                )
            )
            .scalars()
            .all()
        )
        probes = (
            (
                await session.execute(
                    select(BusinessProbeSample)
                    .where(BusinessProbeSample.incident_id == inc.id)
                    .order_by(BusinessProbeSample.checked_at.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        blast = await get_blast_radius(session, asset_slug) if asset_slug else None

    why = build_why_this_action(inc, blast, approvals, executions, probes)
    return build_postmortem_snapshot(
        inc=inc,
        asset_slug=asset_slug,
        events=list(events),
        approvals=list(approvals),
        executions=list(executions),
        probes=list(probes),
        blast=blast,
        why_this_action=why,
    )


@router.get("/{incident_id}/postmortem.md")
async def export_postmortem_markdown(
    incident_id: uuid.UUID,
    request: Request,
    _: AuthenticatedUser = Depends(require_role("viewer")),
) -> Response:
    """Export sanitized Markdown postmortem (`viewer+`) derived from unified snapshot model."""
    snapshot = await _load_postmortem_snapshot(incident_id, request)
    md_text = render_postmortem_markdown(snapshot)
    safe_fname = f"aegisops-postmortem-{incident_id}.md"
    return Response(
        content=md_text,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_fname}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{incident_id}/postmortem.pdf")
async def export_postmortem_pdf(
    incident_id: uuid.UUID,
    request: Request,
    _: AuthenticatedUser = Depends(require_role("viewer")),
) -> Response:
    """Export sanitized multi-page %PDF-1.4 postmortem (`viewer+`) without external fetches."""
    snapshot = await _load_postmortem_snapshot(incident_id, request)
    pdf_bytes = render_postmortem_pdf(snapshot)
    safe_fname = f"aegisops-postmortem-{incident_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_fname}"',
            "Cache-Control": "no-store",
        },
    )
