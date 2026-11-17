"""Read-only Recorded Incident Replay frame reconstruction (never mutates live DB, Redis, or K8s)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.incidents import compute_lifecycle_steps
from app.cmdb.graph import get_blast_radius
from app.models.entities import (
    ApprovalRequest,
    Asset,
    BusinessProbeSample,
    ExecutionAttempt,
    Incident,
    IncidentEvent,
)

ILLUSTRATIVE_FIXTURES: dict[str, dict[str, Any]] = {
    "fixture-traffic-spike-recovery": {
        "replay_id": "fixture-traffic-spike-recovery",
        "title": "Traffic Spike & Latency Surge on provider-directory",
        "scenario_id": "traffic_spike",
        "target_service": "provider-directory",
        "severity": "P3",
        "final_state": "RESOLVED",
        "source_type": "illustrative_fixture",
        "source_badge": "Illustrative fixture (synthetic timeline)",
        "captured_at": "2026-11-16T18:00:00+00:00",
        "disclaimer": (
            "This replay is a curated illustrative fixture showing the full autonomous scale-out lifecycle. "
            "It does not touch live cluster state."
        ),
        "downstream_impacts": ["member-portal-gateway"],
        "frames": [
            {
                "frame_index": 0,
                "seq": 1,
                "timestamp": "2026-11-16T18:00:05+00:00",
                "elapsed_seconds": 0,
                "lifecycle_step": 1,
                "state": "OPEN",
                "event_type": "ALERT_INGESTED",
                "headline": "Requests are slowing down on provider-directory.",
                "narration": "Prometheus/Alertmanager reported p95 search latency breaching 500ms while synthetic load rose.",
                "active_panel": "queue",
                "watchdog_progress": {"status": "idle", "elapsed_seconds": 0, "window_seconds": 60, "reset_count": 0},
                "topology_overlay": {
                    "root_service": "provider-directory",
                    "downstream_impacted": ["member-portal-gateway"],
                    "historical_k8s_snapshot": {"replicas": 1, "ready_replicas": 1, "image": "aegisops/provider-directory:v1.0.0-good"},
                },
                "probes_up_to_frame": [
                    {"target_service": "provider-directory", "status": "DEGRADED", "latency_ms": 842.0, "summary": "Clinic search succeeded semantically but latency breached 500ms."}
                ],
                "why_this_action_snapshot": {"phase": "ingestion", "ai_hypothesis": None, "policy_decision": None},
            },
            {
                "frame_index": 1,
                "seq": 2,
                "timestamp": "2026-11-16T18:00:06+00:00",
                "elapsed_seconds": 1,
                "lifecycle_step": 2,
                "state": "TRIAGING",
                "event_type": "PRIVACY_AND_BLAST_RADIUS",
                "headline": "Sensitive fields checked; CMDB blast radius computed.",
                "narration": "Boundary scrubber checked alert payload (0 PII leaked) and CMDB mapped downstream gateway consumer.",
                "active_panel": "topology",
                "watchdog_progress": {"status": "idle", "elapsed_seconds": 0, "window_seconds": 60, "reset_count": 0},
                "topology_overlay": {
                    "root_service": "provider-directory",
                    "downstream_impacted": ["member-portal-gateway"],
                    "historical_k8s_snapshot": {"replicas": 1, "ready_replicas": 1, "image": "aegisops/provider-directory:v1.0.0-good"},
                },
                "probes_up_to_frame": [],
                "why_this_action_snapshot": {"phase": "blast_radius", "downstream": ["member-portal-gateway"]},
            },
            {
                "frame_index": 2,
                "seq": 3,
                "timestamp": "2026-11-16T18:00:14+00:00",
                "elapsed_seconds": 9,
                "lifecycle_step": 5,
                "state": "READY_TO_REMEDIATE",
                "event_type": "POLICY_EVALUATED",
                "headline": "Runbook suggests scale-out; policy permits LOW-risk action.",
                "narration": "Hybrid RAG matched RB-003 (cos >= 0.78). Policy approved replica_scale_out_bounded (target_replicas=3) autonomously.",
                "active_panel": "detail",
                "watchdog_progress": {"status": "idle", "elapsed_seconds": 0, "window_seconds": 60, "reset_count": 0},
                "topology_overlay": {
                    "root_service": "provider-directory",
                    "downstream_impacted": ["member-portal-gateway"],
                    "historical_k8s_snapshot": {"replicas": 1, "ready_replicas": 1, "image": "aegisops/provider-directory:v1.0.0-good"},
                },
                "probes_up_to_frame": [],
                "why_this_action_snapshot": {
                    "phase": "policy_gate",
                    "proposed_playbook_id": "replica_scale_out_bounded",
                    "policy_decision": "ALLOW_AUTO_EXECUTE",
                    "mfa_required": False,
                },
            },
            {
                "frame_index": 3,
                "seq": 4,
                "timestamp": "2026-11-16T18:00:25+00:00",
                "elapsed_seconds": 20,
                "lifecycle_step": 6,
                "state": "VERIFYING",
                "event_type": "REMEDIATION_SUCCEEDED",
                "headline": "Kubernetes scaled provider-directory 1 -> 3; observing 60s stability.",
                "narration": "Deployment rollout succeeded (3 ready / 3 desired). Watchdog began sustained 60-second stability checks.",
                "active_panel": "detail",
                "watchdog_progress": {"status": "observing", "elapsed_seconds": 30, "window_seconds": 60, "reset_count": 0},
                "topology_overlay": {
                    "root_service": "provider-directory",
                    "downstream_impacted": ["member-portal-gateway"],
                    "historical_k8s_snapshot": {"replicas": 3, "ready_replicas": 3, "image": "aegisops/provider-directory:v1.0.0-good"},
                },
                "probes_up_to_frame": [],
                "why_this_action_snapshot": {
                    "phase": "verifying",
                    "proposed_playbook_id": "replica_scale_out_bounded",
                    "policy_decision": "ALLOW_AUTO_EXECUTE",
                    "execution_diff": {"before_replicas": 1, "after_replicas": 3},
                },
            },
            {
                "frame_index": 4,
                "seq": 5,
                "timestamp": "2026-11-16T18:01:26+00:00",
                "elapsed_seconds": 81,
                "lifecycle_step": 7,
                "state": "RESOLVED",
                "event_type": "RECOVERY_VERIFIED",
                "headline": "Sustained health confirmed over 60s; application check succeeds again.",
                "narration": "Watchdog confirmed 60s of clean /readyz + latency checks and provider search probe returned PASS (42ms).",
                "active_panel": "probes",
                "watchdog_progress": {"status": "passed", "elapsed_seconds": 60, "window_seconds": 60, "reset_count": 0},
                "topology_overlay": {
                    "root_service": "provider-directory",
                    "downstream_impacted": [],
                    "historical_k8s_snapshot": {"replicas": 3, "ready_replicas": 3, "image": "aegisops/provider-directory:v1.0.0-good"},
                },
                "probes_up_to_frame": [
                    {"target_service": "provider-directory", "status": "PASS", "latency_ms": 42.0, "summary": "Provider search returned 3 synthetic clinic(s) in 42.0ms."}
                ],
                "why_this_action_snapshot": {
                    "phase": "resolved",
                    "proposed_playbook_id": "replica_scale_out_bounded",
                    "policy_decision": "ALLOW_AUTO_EXECUTE",
                    "final_state": "RESOLVED",
                },
            },
        ],
    },
    "fixture-db-escalation-boundary": {
        "replay_id": "fixture-db-escalation-boundary",
        "title": "Fictional PII Leak Scrubbing + Stateful DB Escalation Boundary",
        "scenario_id": "pii_leak_and_db_failure",
        "target_service": "postgres-claims-db",
        "severity": "P1",
        "final_state": "ESCALATED",
        "source_type": "illustrative_fixture",
        "source_badge": "Illustrative fixture (synthetic timeline)",
        "captured_at": "2026-11-16T18:10:00+00:00",
        "disclaimer": (
            "This replay is a curated illustrative fixture showing fail-safe refusal on a stateful database boundary. "
            "It does not touch live cluster state."
        ),
        "downstream_impacts": ["eligibility-api", "claims-processor", "member-portal-gateway"],
        "frames": [
            {
                "frame_index": 0,
                "seq": 1,
                "timestamp": "2026-11-16T18:10:01+00:00",
                "elapsed_seconds": 0,
                "lifecycle_step": 2,
                "state": "OPEN",
                "event_type": "ALERT_INGESTED",
                "headline": "Fictional PII/credentials stripped at ingestion boundary.",
                "narration": "6 sensitive tokens (SSN, Member ID, Email, DOB, Bearer token) were scrubbed in memory before persistence or Ollama calls.",
                "active_panel": "detail",
                "watchdog_progress": {"status": "idle", "elapsed_seconds": 0, "window_seconds": 60, "reset_count": 0},
                "topology_overlay": {
                    "root_service": "postgres-claims-db",
                    "downstream_impacted": ["eligibility-api", "claims-processor", "member-portal-gateway"],
                    "historical_k8s_snapshot": "Not captured at ingestion boundary in fixture",
                },
                "probes_up_to_frame": [],
                "why_this_action_snapshot": {"phase": "privacy_scrubbed", "redacted_tokens": 6},
            },
            {
                "frame_index": 1,
                "seq": 2,
                "timestamp": "2026-11-16T18:10:09+00:00",
                "elapsed_seconds": 8,
                "lifecycle_step": 7,
                "state": "ESCALATED",
                "event_type": "POLICY_EVALUATED",
                "headline": "Policy safely refused automation and escalated to human DBA.",
                "narration": "Hybrid RAG matched RB-011 (permitted_playbook_id=null, stateless_eligible=False). Control plane escalated as P1 without mutating stateful DB.",
                "active_panel": "detail",
                "watchdog_progress": {"status": "not_applicable", "elapsed_seconds": 0, "window_seconds": 60, "reset_count": 0},
                "topology_overlay": {
                    "root_service": "postgres-claims-db",
                    "downstream_impacted": ["eligibility-api", "claims-processor", "member-portal-gateway"],
                    "historical_k8s_snapshot": {"replicas": 1, "ready_replicas": 1, "note": "Unmutated by policy"},
                },
                "probes_up_to_frame": [
                    {"target_service": "postgres-claims-db", "status": "FAIL", "latency_ms": 14.0, "summary": "Demo DB reports simulated fault: ERR_PG_REPLICATION_LAG (manual DBA intervention required)."}
                ],
                "why_this_action_snapshot": {
                    "phase": "escalated",
                    "proposed_playbook_id": None,
                    "policy_decision": "REFUSE_AND_ESCALATE",
                    "final_state": "ESCALATED",
                },
            },
        ],
    },
}


def _step_for_state(state: str | None) -> int:
    mapping = {
        "OPEN": 1,
        "TRIAGING": 4,
        "READY_TO_REMEDIATE": 5,
        "AWAITING_APPROVAL": 5,
        "REMEDIATING": 5,
        "VERIFYING": 6,
        "RESOLVED": 7,
        "ESCALATED": 7,
        "FAILED": 7,
    }
    return mapping.get(state or "", 3)


def _panel_for_event(event_type: str) -> str:
    et = event_type.upper()
    if "ALERT" in et or "PRIVACY" in et:
        return "queue"
    if "REMEDIATION" in et or "ROLLOUT" in et or "EXECUTION" in et:
        return "topology"
    if "RECOVERY" in et or "PROBE" in et:
        return "probes"
    return "detail"


async def list_available_replays(session: AsyncSession, *, limit: int = 12) -> list[dict[str, Any]]:
    """Return captured cluster incident replays plus clearly labeled illustrative fixtures (`visitor+`)."""
    rows = (
        await session.execute(
            select(Incident, Asset.slug)
            .outerjoin(Asset, Incident.primary_asset_id == Asset.id)
            .where(Incident.source_provenance.in_(["interactive_demo", "live_alert"]))
            .order_by(desc(Incident.ingested_at))
            .limit(limit)
        )
    ).all()

    items: list[dict[str, Any]] = []
    for inc, asset_slug in rows:
        items.append(
            {
                "replay_id": str(inc.id),
                "title": inc.title,
                "scenario_id": None,
                "target_service": asset_slug or inc.unknown_asset_identifier or "unknown",
                "severity": inc.severity,
                "final_state": inc.state,
                "source_provenance": inc.source_provenance,
                "source_type": "captured_live_run",
                "source_badge": "Captured from local cluster run",
                "captured_at": inc.ingested_at.isoformat(),
                "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
            }
        )

    for fix in ILLUSTRATIVE_FIXTURES.values():
        items.append(
            {
                "replay_id": fix["replay_id"],
                "title": fix["title"],
                "scenario_id": fix["scenario_id"],
                "target_service": fix["target_service"],
                "severity": fix["severity"],
                "final_state": fix["final_state"],
                "source_provenance": "recorded_replay",
                "source_type": fix["source_type"],
                "source_badge": fix["source_badge"],
                "captured_at": fix["captured_at"],
                "resolved_at": fix["frames"][-1]["timestamp"] if fix["final_state"] == "RESOLVED" else None,
            }
        )
    return items


async def get_replay_timeline(session: AsyncSession, replay_id: str) -> dict[str, Any] | None:
    """Reconstruct read-only chronological replay frames for a captured incident or illustrative fixture."""
    clean_id = replay_id.removeprefix("fixture:").strip()
    if clean_id in ILLUSTRATIVE_FIXTURES:
        return dict(ILLUSTRATIVE_FIXTURES[clean_id])

    raw_uuid = replay_id.removeprefix("incident:").strip()
    try:
        inc_uuid = uuid.UUID(raw_uuid)
    except ValueError:
        return None

    row = (
        await session.execute(
            select(Incident, Asset.slug)
            .outerjoin(Asset, Incident.primary_asset_id == Asset.id)
            .where(Incident.id == inc_uuid)
        )
    ).first()
    if row is None:
        return None
    inc, asset_slug = row

    # Never expose internal automated_test incidents as Visitor public replay unless explicitly addressed by UUID?
    # Allow replay by exact UUID while clearly reporting source_provenance!
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
                .order_by(ApprovalRequest.requested_at.asc())
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
                .order_by(ExecutionAttempt.started_at.asc())
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
                .order_by(BusinessProbeSample.checked_at.asc())
            )
        )
        .scalars()
        .all()
    )
    blast = await get_blast_radius(session, asset_slug) if asset_slug else None
    downstream_slugs = [d.slug for d in (blast.downstream_impacts if blast else [])]
    steps_final = compute_lifecycle_steps(
        inc, list(events), list(approvals), list(executions)
    )

    t0 = inc.ingested_at or datetime.now(UTC)
    frames: list[dict[str, Any]] = []

    if not events:
        frames.append(
            {
                "frame_index": 0,
                "seq": 1,
                "timestamp": t0.isoformat(),
                "elapsed_seconds": 0,
                "lifecycle_step": _step_for_state(inc.state),
                "state": inc.state,
                "event_type": "SNAPSHOT",
                "headline": inc.title,
                "narration": inc.summary_sanitized,
                "active_panel": "detail",
                "watchdog_progress": inc.verification_state_json or {"status": "not_captured"},
                "topology_overlay": {
                    "root_service": asset_slug or inc.unknown_asset_identifier or "unknown",
                    "downstream_impacted": downstream_slugs,
                    "historical_k8s_snapshot": "Not captured in persisted events",
                },
                "probes_up_to_frame": [],
                "why_this_action_snapshot": {"phase": inc.state.lower(), "final_state": inc.state},
            }
        )
    else:
        for idx, ev in enumerate(events):
            elapsed = max(0, int(round((ev.created_at - t0).total_seconds())))
            cur_state = ev.to_state or inc.state
            details = dict(ev.details_sanitized_json or {})

            # Match historical execution snapshot up to this event timestamp (never future live cluster state!)
            hist_snap: Any = "Historical K8s snapshot not captured at this step"
            matched_execs = [ex for ex in executions if ex.started_at <= ev.created_at]
            if matched_execs:
                latest_ex = matched_execs[-1]
                if latest_ex.completed_at and latest_ex.completed_at <= ev.created_at and latest_ex.after_state_sanitized_json:
                    hist_snap = latest_ex.after_state_sanitized_json
                elif latest_ex.before_state_sanitized_json:
                    hist_snap = latest_ex.before_state_sanitized_json

            wd = details.get("verification_state") or (
                inc.verification_state_json
                if cur_state in ("VERIFYING", "RESOLVED") and idx >= len(events) - 2
                else {"status": "observing" if cur_state == "VERIFYING" else "pending", "elapsed_seconds": 0, "window_seconds": 60}
            )
            probes_so_far = [
                {
                    "target_service": p.target_service,
                    "status": p.status,
                    "latency_ms": p.latency_ms,
                    "summary": p.summary_sanitized,
                    "checked_at": p.checked_at.isoformat(),
                }
                for p in probes
                if p.checked_at <= ev.created_at
            ]
            headline = f"{ev.event_type.replace('_', ' ').title()} ({cur_state})"
            narration = str(
                details.get("reason")
                or details.get("summary")
                or details.get("decision")
                or f"Actor {ev.actor} recorded {ev.event_type} transitioning {ev.from_state or 'INIT'} -> {cur_state}."
            )
            frames.append(
                {
                    "frame_index": idx,
                    "seq": ev.sequence_num,
                    "timestamp": ev.created_at.isoformat(),
                    "elapsed_seconds": elapsed,
                    "lifecycle_step": _step_for_state(cur_state),
                    "state": cur_state,
                    "event_type": ev.event_type,
                    "headline": headline,
                    "narration": narration,
                    "active_panel": _panel_for_event(ev.event_type),
                    "watchdog_progress": wd,
                    "topology_overlay": {
                        "root_service": asset_slug or inc.unknown_asset_identifier or "unknown",
                        "downstream_impacted": [] if cur_state == "RESOLVED" else downstream_slugs,
                        "historical_k8s_snapshot": hist_snap,
                    },
                    "probes_up_to_frame": probes_so_far,
                    "why_this_action_snapshot": {
                        "phase": cur_state.lower(),
                        "proposed_playbook_id": inc.proposed_playbook_id if _step_for_state(cur_state) >= 5 else None,
                        "policy_decision": details.get("decision"),
                        "redacted_tokens": int((inc.redaction_stats_json or {}).get("total_redactions", 0)),
                    },
                }
            )

    return {
        "replay_id": str(inc.id),
        "title": inc.title,
        "scenario_id": None,
        "target_service": asset_slug or inc.unknown_asset_identifier or "unknown",
        "severity": inc.severity,
        "final_state": inc.state,
        "source_provenance": inc.source_provenance,
        "source_type": "captured_live_run",
        "source_badge": "Captured from local cluster run",
        "captured_at": inc.ingested_at.isoformat(),
        "disclaimer": (
            "Read-only recorded replay reconstructed strictly from persisted PostgreSQL events and sanitized snapshots. "
            "No live cluster mutations or executions are triggered."
        ),
        "downstream_impacts": downstream_slugs,
        "lifecycle_steps_summary": steps_final,
        "frames": frames,
    }
