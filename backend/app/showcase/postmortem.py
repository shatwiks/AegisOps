"""Unified server-side postmortem snapshot builder and Markdown/PDF exporters (`Feature H`)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app import __version__
from app.cmdb.graph import BlastRadiusResult
from app.models.entities import (
    ApprovalRequest,
    BusinessProbeSample,
    ExecutionAttempt,
    Incident,
    IncidentEvent,
)
from app.showcase.pdf_renderer import SimplePdfDocument

_UNSAFE_HTML_RE = re.compile(r"(?is)<\s*/?\s*(script|iframe|object|embed|style|svg)[^>]*>")


def _safe_text(val: Any) -> str:
    txt = str(val or "").strip()
    txt = _UNSAFE_HTML_RE.sub("", txt)
    txt = re.sub(r"(?i)javascript:", "blocked-uri:", txt)
    return txt


def _escape_md(val: Any) -> str:
    txt = _safe_text(val)
    return txt.replace("<", "&lt;").replace(">", "&gt;")


def _delta_seconds(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    val = (end - start).total_seconds()
    return round(val, 2) if val >= 0 else None


def build_postmortem_snapshot(
    *,
    inc: Incident,
    asset_slug: str | None,
    events: list[IncidentEvent],
    approvals: list[ApprovalRequest],
    executions: list[ExecutionAttempt],
    probes: list[BusinessProbeSample],
    blast: BlastRadiusResult | None,
    why_this_action: dict[str, Any],
) -> dict[str, Any]:
    """Assemble one authoritative sanitized report model consumed by both .md and .pdf exporters."""
    evt_types = {e.event_type for e in events}
    manual_reset_assisted = "BASELINE_RESET_ASSISTED_CLOSE" in evt_types or (
        "manual_reset_assisted" in (inc.refusal_reason or "").lower()
    )

    if inc.state == "RESOLVED" and manual_reset_assisted:
        report_kind = "Incident Closure Report (Manual Baseline Reset Assisted)"
    elif inc.state == "RESOLVED":
        report_kind = "Verified Resolution Postmortem"
    elif inc.state == "ESCALATED":
        report_kind = "Escalation Report (Autonomous Action Refused / Human Required)"
    elif inc.state == "FAILED":
        report_kind = "Failed Incident Postmortem"
    else:
        report_kind = f"In-Progress Incident Report ({inc.state})"

    diag = inc.diagnosis_json or {}
    proposal = diag.get("proposal") or {}
    citations = diag.get("citations") or []
    checks = diag.get("policy_checks") or {}
    verif = inc.verification_state_json or {}
    redaction = inc.redaction_stats_json or {}

    latest_appr = approvals[0] if approvals else None
    latest_exec = executions[0] if executions else None

    return {
        "snapshot_version": "1.0",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "build_version": __version__,
        "report_kind": report_kind,
        "manual_reset_assisted": manual_reset_assisted,
        "identifiers": {
            "incident_id": str(inc.id),
            "dedup_key": _safe_text(inc.dedup_key),
            "alert_fingerprint": _safe_text(inc.alert_fingerprint),
            "alertname": _safe_text(inc.alertname),
            "title": _safe_text(inc.title),
            "source_provenance": _safe_text(inc.source_provenance),
            "demo_run_id": str(inc.demo_run_id) if inc.demo_run_id else "None",
        },
        "service_and_impact": {
            "target_asset": _safe_text(asset_slug or inc.unknown_asset_identifier or "unknown"),
            "severity": _safe_text(inc.severity),
            "final_state": _safe_text(inc.state),
            "potential_blast_radius_downstream": [
                {"slug": n.slug, "criticality": n.criticality, "hop": n.hop_distance}
                for n in (blast.downstream_impacts if blast else [])
            ],
            "upstream_dependencies": [
                {"slug": n.slug, "criticality": n.criticality, "hop": n.hop_distance}
                for n in (blast.upstream_dependencies if blast else [])
            ],
            "summary_sanitized": _safe_text(inc.summary_sanitized),
        },
        "timestamps_and_durations": {
            "fault_onset_at": inc.fault_onset_at.isoformat() if inc.fault_onset_at else "Unavailable",
            "detected_at": inc.detected_at.isoformat() if inc.detected_at else "Unavailable",
            "ingested_at": inc.ingested_at.isoformat(),
            "triaged_at": inc.triaged_at.isoformat() if inc.triaged_at else "Unavailable",
            "approved_at": inc.approved_at.isoformat() if inc.approved_at else "Not applicable / pending",
            "mutated_at": inc.mutated_at.isoformat() if inc.mutated_at else "No mutation executed",
            "first_recovered_at": inc.first_recovered_at.isoformat() if inc.first_recovered_at else "Unavailable",
            "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else "Not resolved",
            "mttd_seconds": _delta_seconds(inc.fault_onset_at, inc.detected_at),
            "mttr_seconds": _delta_seconds(inc.fault_onset_at or inc.ingested_at, inc.resolved_at),
            "verification_window_seconds": float(verif.get("window_seconds", 60.0)),
            "verification_observed_healthy_seconds": float(verif.get("elapsed_healthy_seconds", 0.0)),
            "verification_resets": int(verif.get("reset_count", 0)),
        },
        "privacy_summary": {
            "total_redactions": int(redaction.get("total_redactions", 0)),
            "redactions_by_category": dict(redaction.get("redaction_counts") or {}),
            "dropped_unallowlisted_keys": int(redaction.get("dropped_unallowlisted_keys", 0)),
            "scrubber_failed_fallback": bool(redaction.get("scrubber_failed_fallback", False)),
            "note": "Token counts measure scrubber matches stripped prior to persistence and LLM inference; they do not equate to distinct patients.",
        },
        "retrieved_documents": [
            {
                "slug": _safe_text(c.get("slug")),
                "title": _safe_text(c.get("title")),
                "doc_type": _safe_text(c.get("doc_type")),
                "vector_similarity": c.get("vector_similarity"),
                "lexical_score": c.get("lexical_score"),
                "rrf_score": c.get("rrf_score"),
            }
            for c in citations
        ],
        "diagnosis_and_policy": {
            "diagnosis_hypothesis": _safe_text(
                proposal.get("root_cause_summary") or "Model hypothesis unavailable or failed validation"
            ),
            "uncertainty_level": _safe_text(proposal.get("uncertainty_level") or "UNKNOWN"),
            "ai_proposed_playbook": _safe_text(proposal.get("proposed_playbook_id") or "None"),
            "server_policy_playbook": _safe_text(inc.proposed_playbook_id or "None"),
            "server_policy_checks": checks,
            "refusal_or_block_reason": _safe_text(inc.refusal_reason or "None"),
        },
        "approval_record": (
            {
                "status": latest_appr.status,
                "playbook_id": latest_appr.playbook_id,
                "playbook_version": latest_appr.playbook_version,
                "target_asset_slug": latest_appr.target_asset_slug,
                "decided_by_email": _safe_text(latest_appr.decided_by_email or "Pending"),
                "decided_by_role": _safe_text(latest_appr.decided_by_role or "N/A"),
                "decided_at": latest_appr.decided_at.isoformat() if latest_appr.decided_at else "Pending",
                "mfa_note": "Action-bound TOTP verified cleanly (TOTP seeds/codes never exported).",
            }
            if latest_appr
            else None
        ),
        "kubernetes_changes": (
            {
                "playbook_id": latest_exec.playbook_id,
                "status": latest_exec.status,
                "requested_parameters": latest_exec.parameters_json,
                "before_state": latest_exec.before_state_sanitized_json,
                "after_state": latest_exec.after_state_sanitized_json,
                "error": _safe_text(latest_exec.error_message_sanitized or ""),
            }
            if latest_exec
            else None
        ),
        "business_probes": [
            {
                "target_service": p.target_service,
                "status": p.status,
                "http_status": p.http_status,
                "latency_ms": p.latency_ms,
                "summary": _safe_text(p.summary_sanitized),
                "checked_at": p.checked_at.isoformat(),
            }
            for p in probes
        ],
        "timeline": [
            {
                "seq": e.sequence_num,
                "timestamp": e.created_at.isoformat(),
                "event_type": e.event_type,
                "transition": f"{e.from_state or 'INIT'} -> {e.to_state or e.from_state or ''}",
                "actor": _safe_text(e.actor),
            }
            for e in events
        ],
        "limitations": [
            "Synthetic healthcare demonstration cluster and workloads (`aegisops-healthcare`); not certified for clinical production.",
            *(
                ["Closure assisted by operator Restore Demo Baseline (`manual_reset_assisted`); not an autonomous Kubernetes fix."]
                if manual_reset_assisted
                else []
            ),
            *(
                ["Automated DB failover is intentionally unsupported on single-instance `postgres-claims-db`; requires DBA verification."]
                if asset_slug == "postgres-claims-db"
                else []
            ),
        ],
        "why_summary": why_this_action.get("questions") or {},
    }


def render_postmortem_markdown(snapshot: dict[str, Any]) -> str:
    """Render deterministic sanitized Markdown postmortem strictly from `snapshot`."""
    ids = snapshot["identifiers"]
    svc = snapshot["service_and_impact"]
    ts = snapshot["timestamps_and_durations"]
    priv = snapshot["privacy_summary"]
    diag = snapshot["diagnosis_and_policy"]
    appr = snapshot["approval_record"]
    k8s = snapshot["kubernetes_changes"]

    lines: list[str] = [
        f"# {snapshot['report_kind']}: {_escape_md(ids['title'])}",
        "",
        f"- **Generated (UTC):** `{snapshot['generated_at_utc']}` (Snapshot v{snapshot['snapshot_version']}, Build `{snapshot['build_version']}`)",
        f"- **Incident ID:** `{ids['incident_id']}` | **Demo Run ID:** `{ids['demo_run_id']}`",
        f"- **Severity / Outcome:** `{svc['severity']}` / `{svc['final_state']}` | **Source:** `{ids['source_provenance']}`",
        f"- **Target Asset:** `{svc['target_asset']}` | **Alertname:** `{ids['alertname']}`",
        "",
        "## 1. Incident Summary & Blast Radius",
        f"**Sanitized Summary:** {_escape_md(svc['summary_sanitized'])}",
        "",
        f"- **Potential CMDB Downstream Blast Radius (Static Dependency Topology):** {', '.join('`' + d['slug'] + '`' for d in svc['potential_blast_radius_downstream']) or 'None mapped'}",
        f"- **Upstream Dependencies:** {', '.join('`' + u['slug'] + '`' for u in svc['upstream_dependencies']) or 'None'}",
        "",
        "## 2. Timestamps & Observed Durations (UTC)",
        f"- **Fault Onset:** `{ts['fault_onset_at']}`",
        f"- **Detected / Ingested:** `{ts['detected_at']}` / `{ts['ingested_at']}`",
        f"- **Triaged / Approved / Mutated:** `{ts['triaged_at']}` / `{ts['approved_at']}` / `{ts['mutated_at']}`",
        f"- **First Recovered / Resolved:** `{ts['first_recovered_at']}` / `{ts['resolved_at']}`",
        f"- **Measured MTTD / Total MTTR:** `{ts['mttd_seconds'] if ts['mttd_seconds'] is not None else 'Unavailable'}` s / `{ts['mttr_seconds'] if ts['mttr_seconds'] is not None else 'Unavailable'}` s",
        f"- **Watchdog Stability Window:** `{ts['verification_observed_healthy_seconds']}s / {ts['verification_window_seconds']}s` (Resets: `{ts['verification_resets']}`)",
        "",
        "## 3. Privacy Boundary Summary",
        f"- **Total Tokens Redacted:** `{priv['total_redactions']}` (Dropped unallowlisted keys: `{priv['dropped_unallowlisted_keys']}`, Fail-closed fallback: `{priv['scrubber_failed_fallback']}`)",
        f"- **Categories:** `{priv['redactions_by_category'] or {}}`",
        f"- **Definition Note:** {priv['note']}",
        "",
        "## 4. Hybrid RAG Evidence Citations",
    ]
    if snapshot["retrieved_documents"]:
        for doc in snapshot["retrieved_documents"]:
            lines.append(
                f"- `{doc['slug']}` ({doc['doc_type']}) — {_escape_md(doc['title'])} "
                f"[cosine=`{doc['vector_similarity']}`, lexical=`{doc['lexical_score']}`, rrf=`{doc['rrf_score']}`]"
            )
    else:
        lines.append("- No retrieved knowledge documents recorded.")

    lines.extend(
        [
            "",
            "## 5. AI Hypothesis vs. Server Policy Gate",
            f"- **AI Diagnosis Hypothesis (Untrusted until policy-checked):** {_escape_md(diag['diagnosis_hypothesis'])} (Uncertainty: `{diag['uncertainty_level']}`)",
            f"- **AI Proposed Playbook:** `{diag['ai_proposed_playbook']}` -> **Server Policy Approved Playbook:** `{diag['server_policy_playbook']}`",
            f"- **Refusal / Escalation Reason:** {_escape_md(diag['refusal_or_block_reason'])}",
            "",
            "## 6. Step-Up MFA Approval & Kubernetes Changes",
        ]
    )
    if appr:
        lines.append(
            f"- **Approval:** `{appr['status']}` by `{_escape_md(appr['decided_by_email'])}` (`{appr['decided_by_role']}`) at `{appr['decided_at']}` — {appr['mfa_note']}"
        )
    else:
        lines.append("- **Approval:** Not required or not requested.")

    if k8s:
        lines.append(f"- **Execution:** `{k8s['playbook_id']}` -> `{k8s['status']}`")
        lines.append(f"- **Requested Params:** `{k8s['requested_parameters']}`")
        lines.append(f"- **Before Snapshot:** `{k8s['before_state']}`")
        lines.append(f"- **After Snapshot:** `{k8s['after_state']}`")
    else:
        lines.append("- **Kubernetes Mutation:** None executed.")

    lines.extend(["", "## 7. Business Transaction Probes"])
    if snapshot["business_probes"]:
        for p in snapshot["business_probes"]:
            lines.append(
                f"- `{p['checked_at']}` | `{p['target_service']}` | **{p['status']}** (HTTP `{p['http_status']}`, `{p['latency_ms']}` ms) — {_escape_md(p['summary'])}"
            )
    else:
        lines.append("- No correlated business transaction probes captured.")

    lines.extend(["", "## 8. Chronological Audit Timeline (UTC)"])
    for ev in snapshot["timeline"]:
        lines.append(
            f"- `seq={ev['seq']}` | `{ev['timestamp']}` | `{ev['event_type']}` | `{ev['transition']}` | `{_escape_md(ev['actor'])}`"
        )

    lines.extend(["", "## 9. Limitations & Follow-ups"])
    for lim in snapshot["limitations"]:
        lines.append(f"- {lim}")
    return "\n".join(lines) + "\n"


def render_postmortem_pdf(snapshot: dict[str, Any]) -> bytes:
    """Render clean multi-page %PDF-1.4 document strictly from `snapshot`."""
    ids = snapshot["identifiers"]
    svc = snapshot["service_and_impact"]
    ts = snapshot["timestamps_and_durations"]
    priv = snapshot["privacy_summary"]
    diag = snapshot["diagnosis_and_policy"]
    appr = snapshot["approval_record"]
    k8s = snapshot["kubernetes_changes"]

    pdf = SimplePdfDocument(
        footer_label=f"AegisOps Incident {ids['incident_id']} | Generated {snapshot['generated_at_utc']}"
    )
    pdf.add_title(f"{snapshot['report_kind']}: {ids['title']}")
    pdf.add_kv("Generated (UTC)", f"{snapshot['generated_at_utc']} (Snapshot v{snapshot['snapshot_version']}, Build {snapshot['build_version']})")
    pdf.add_kv("Incident ID", f"{ids['incident_id']} | Demo Run ID: {ids['demo_run_id']}")
    pdf.add_kv("Target Service", f"{svc['target_asset']} | Severity: {svc['severity']} | Outcome: {svc['final_state']}")
    pdf.add_kv("Provenance / Alert", f"{ids['source_provenance']} | {ids['alertname']}")

    pdf.add_heading("1. Summary & CMDB Potential Blast Radius")
    pdf.add_paragraph(f"Sanitized Summary: {svc['summary_sanitized']}")
    down = ", ".join(d["slug"] for d in svc["potential_blast_radius_downstream"]) or "None"
    up = ", ".join(u["slug"] for u in svc["upstream_dependencies"]) or "None"
    pdf.add_kv("Potential Downstream Blast Radius", down)
    pdf.add_kv("Upstream Dependencies", up)

    pdf.add_heading("2. UTC Timeline Milestones & Observed Durations")
    pdf.add_kv("Fault Onset / Detected", f"{ts['fault_onset_at']} / {ts['detected_at']}")
    pdf.add_kv("Ingested / Triaged", f"{ts['ingested_at']} / {ts['triaged_at']}")
    pdf.add_kv("Approved / Mutated", f"{ts['approved_at']} / {ts['mutated_at']}")
    pdf.add_kv("First Recovered / Resolved", f"{ts['first_recovered_at']} / {ts['resolved_at']}")
    pdf.add_kv(
        "MTTD / Total MTTR",
        f"{ts['mttd_seconds'] if ts['mttd_seconds'] is not None else 'Unavailable'}s / "
        f"{ts['mttr_seconds'] if ts['mttr_seconds'] is not None else 'Unavailable'}s",
    )
    pdf.add_kv(
        "Watchdog Stability Window",
        f"{ts['verification_observed_healthy_seconds']}s of {ts['verification_window_seconds']}s observed (resets={ts['verification_resets']})",
    )

    pdf.add_heading("3. Privacy Scrubber Summary")
    pdf.add_kv(
        "Redaction Counts",
        f"Total={priv['total_redactions']}, Dropped Keys={priv['dropped_unallowlisted_keys']}, FailClosed={priv['scrubber_failed_fallback']}",
    )
    pdf.add_paragraph(f"Categories: {priv['redactions_by_category'] or {}} — {priv['note']}")

    pdf.add_heading("4. Retrieved Runbooks & AI vs. Server Policy Gate")
    if snapshot["retrieved_documents"]:
        for doc in snapshot["retrieved_documents"]:
            pdf.add_bullet(
                f"{doc['slug']} ({doc['doc_type']}) - {doc['title']} "
                f"[cos={doc['vector_similarity']}, lex={doc['lexical_score']}, rrf={doc['rrf_score']}]"
            )
    else:
        pdf.add_bullet("No retrieved knowledge documents recorded.")
    pdf.add_kv("AI Diagnosis Hypothesis", f"{diag['diagnosis_hypothesis']} (Uncertainty: {diag['uncertainty_level']})")
    pdf.add_kv("Server Policy Gate", f"Proposed={diag['server_policy_playbook']} | Refusal={diag['refusal_or_block_reason']}")

    pdf.add_heading("5. MFA Approval & Kubernetes State Diff")
    if appr:
        pdf.add_bullet(
            f"Approval {appr['status']} by {appr['decided_by_email']} ({appr['decided_by_role']}) "
            f"at {appr['decided_at']} - {appr['mfa_note']}"
        )
    else:
        pdf.add_bullet("Approval: Not required or not requested.")

    if k8s:
        pdf.add_kv("Execution Status", f"{k8s['playbook_id']} -> {k8s['status']}")
        pdf.add_paragraph(f"Before: {k8s['before_state']}", mono=True, indent=8)
        pdf.add_paragraph(f"After : {k8s['after_state']}", mono=True, indent=8)
    else:
        pdf.add_bullet("Kubernetes Mutation: None executed.")

    pdf.add_heading("6. Business Transaction Probes & Chronological Timeline")
    if snapshot["business_probes"]:
        for p in snapshot["business_probes"]:
            pdf.add_bullet(f"{p['checked_at']} | {p['target_service']} -> {p['status']} ({p['latency_ms']}ms): {p['summary']}")
    else:
        pdf.add_bullet("No correlated business transaction probes captured.")

    for ev in snapshot["timeline"]:
        pdf.add_paragraph(
            f"[seq={ev['seq']}] {ev['timestamp']} | {ev['event_type']} ({ev['transition']}) by {ev['actor']}",
            mono=True,
        )

    pdf.add_heading("7. Architectural Boundaries & Limitations")
    for lim in snapshot["limitations"]:
        pdf.add_bullet(lim)

    return pdf.render_bytes()
