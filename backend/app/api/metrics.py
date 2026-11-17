"""Measured operational timing metrics, scope filtering, redaction counters & honest value metrics."""

from __future__ import annotations

import statistics
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select

from app.auth.oidc import AuthenticatedUser, optional_authenticate_request
from app.models.entities import ApprovalRequest, BusinessProbeSample, Incident

router = APIRouter(prefix="/api/v1/metrics", tags=["metrics"])


def _summarize_samples(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"sample_count": 0, "mean": None, "p50": None, "p95": None, "min": None, "max": None}
    sorted_vals = sorted(values)
    p95_idx = min(len(sorted_vals) - 1, int(0.95 * (len(sorted_vals) - 1)))
    return {
        "sample_count": len(sorted_vals),
        "mean": round(statistics.mean(sorted_vals), 2),
        "p50": round(statistics.median(sorted_vals), 2),
        "p95": round(sorted_vals[p95_idx], 2),
        "min": round(sorted_vals[0], 2),
        "max": round(sorted_vals[-1], 2),
    }


@router.get("/summary")
async def get_metrics_summary(
    request: Request,
    scope: str = Query(default="live_and_demo"),
    manual_baseline_minutes: float | None = Query(default=None, ge=1.0, le=1440.0),
    _: AuthenticatedUser | None = Depends(optional_authenticate_request),
) -> dict[str, Any]:
    """Compute honest MTTD/MTTR, value counters, and probe outcomes from persisted timestamps (`visitor+`)."""
    norm_scope = scope.strip().lower()
    if norm_scope not in ("live_and_demo", "automated_test", "all"):
        norm_scope = "live_and_demo"

    async with request.app.state.session_factory() as session:
        stmt = select(Incident)
        if norm_scope == "live_and_demo":
            stmt = stmt.where(Incident.source_provenance != "automated_test")
        elif norm_scope == "automated_test":
            stmt = stmt.where(Incident.source_provenance == "automated_test")

        incidents = (await session.execute(stmt)).scalars().all()
        inc_ids = [i.id for i in incidents]

        probe_pass_count = int(
            (
                await session.execute(
                    select(func.count(BusinessProbeSample.id)).where(
                        BusinessProbeSample.status == "PASS"
                    )
                )
            ).scalar_one()
            or 0
        )
        probe_fail_count = int(
            (
                await session.execute(
                    select(func.count(BusinessProbeSample.id)).where(
                        BusinessProbeSample.status.in_(["FAIL", "DEGRADED"])
                    )
                )
            ).scalar_one()
            or 0
        )
        mfa_gated_count = (
            int(
                (
                    await session.execute(
                        select(func.count(ApprovalRequest.id)).where(
                            ApprovalRequest.incident_id.in_(inc_ids)
                        )
                    )
                ).scalar_one()
                or 0
            )
            if inc_ids
            else 0
        )

    state_counts: dict[str, int] = {}
    mttd_samples: list[float] = []
    mttd_unavailable = 0
    triage_samples: list[float] = []
    action_samples: list[float] = []
    verification_samples: list[float] = []
    mttr_samples: list[float] = []
    total_redactions = 0
    contained_by_automation = 0
    observed_degraded_assets: set[str] = set()
    potential_blast_assets: set[str] = set()

    for inc in incidents:
        state_counts[inc.state] = state_counts.get(inc.state, 0) + 1
        total_redactions += int((inc.redaction_stats_json or {}).get("total_redactions", 0))

        is_manual_assisted = "manual_reset_assisted" in (inc.refusal_reason or "").lower()
        if inc.state == "RESOLVED" and inc.mutated_at is not None and not is_manual_assisted:
            contained_by_automation += 1

        if inc.primary_asset_id and inc.state not in ("RESOLVED", "FAILED"):
            observed_degraded_assets.add(str(inc.primary_asset_id))
        for ds in (inc.severity_explanation_json or {}).get("downstream_impact_slugs") or []:
            potential_blast_assets.add(str(ds))

        if inc.fault_onset_at and inc.detected_at:
            mttd_samples.append(max(0.0, (inc.detected_at - inc.fault_onset_at).total_seconds()))
        else:
            mttd_unavailable += 1

        if inc.triaged_at:
            triage_samples.append(max(0.0, (inc.triaged_at - inc.ingested_at).total_seconds()))

        action_start = inc.approved_at or inc.triaged_at
        if inc.mutated_at and action_start:
            action_samples.append(max(0.0, (inc.mutated_at - action_start).total_seconds()))

        if inc.resolved_at and inc.first_recovered_at:
            verification_samples.append(
                max(0.0, (inc.resolved_at - inc.first_recovered_at).total_seconds())
            )

        mttr_start = inc.fault_onset_at or inc.detected_at or inc.ingested_at
        if inc.resolved_at and mttr_start and not is_manual_assisted:
            mttr_samples.append(max(0.0, (inc.resolved_at - mttr_start).total_seconds()))

    mttr_summary = _summarize_samples(mttr_samples)
    if manual_baseline_minutes is None:
        baseline_comp: dict[str, Any] = {
            "configured": False,
            "label": "Baseline not configured",
            "manual_baseline_minutes": None,
            "estimated_engineer_minutes_saved": None,
            "source": "none",
            "note": (
                "No hardcoded baseline is assumed. Enter an optional user-supplied manual remediation "
                "baseline (minutes) to compare against observed autonomous MTTR."
            ),
        }
    else:
        mean_auto_min = (
            (float(mttr_summary["mean"]) / 60.0) if mttr_summary["mean"] is not None else None
        )
        per_inc_saved = (
            max(0.0, manual_baseline_minutes - mean_auto_min)
            if mean_auto_min is not None
            else None
        )
        total_saved = (
            round(per_inc_saved * contained_by_automation, 1)
            if per_inc_saved is not None
            else None
        )
        baseline_comp = {
            "configured": True,
            "label": f"vs. {manual_baseline_minutes:.0f} min user-supplied baseline",
            "manual_baseline_minutes": manual_baseline_minutes,
            "observed_mean_autonomous_mttr_minutes": round(mean_auto_min, 2)
            if mean_auto_min is not None
            else None,
            "estimated_engineer_minutes_saved": total_saved,
            "source": "user_supplied_assumption",
            "method": (
                "(manual_baseline_minutes - mean_autonomous_mttr_minutes) * "
                f"{contained_by_automation} autonomously resolved incidents"
            ),
        }

    return {
        "scope": norm_scope,
        "total_incidents": len(incidents),
        "state_counts": state_counts,
        "total_phi_pii_redactions": total_redactions,
        "mttd_unavailable_count": mttd_unavailable,
        "timings_seconds": {
            "mttd": _summarize_samples(mttd_samples),
            "triage_latency": _summarize_samples(triage_samples),
            "action_latency": _summarize_samples(action_samples),
            "verification_window": _summarize_samples(verification_samples),
            "mttr_end_to_end": mttr_summary,
        },
        "business_value": {
            "sensitive_identifiers_redacted": total_redactions,
            "redaction_definition": "Scrubber pattern/key matches stripped on accepted alerts (retries do not re-count; token count != distinct patients).",
            "incidents_contained_by_automation": contained_by_automation,
            "high_risk_actions_gated_by_mfa": mfa_gated_count,
            "cmdb_potential_downstream_services": len(potential_blast_assets),
            "observed_active_degraded_assets": len(observed_degraded_assets),
            "business_probe_recoveries_verified": probe_pass_count,
            "business_probe_failures_observed": probe_fail_count,
            "manual_baseline_comparison": baseline_comp,
        },
        "measurement_note": (
            "Full confirmed MTTR includes the configured sustained recovery verification window "
            "(60s default); timestamps are computed solely from observed persisted samples."
        ),
    }
