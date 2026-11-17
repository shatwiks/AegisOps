"""Deterministic server-side remediation policy engine and refusal gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.config import Settings
from app.models.entities import Asset
from app.playbooks.registry import PLAYBOOK_REGISTRY, validate_playbook_for_asset
from app.rag.diagnosis import DiagnosisProposal
from app.rag.retriever import RetrievedDocument

PolicyDecisionType = Literal["ALLOW_AUTO_EXECUTE", "REQUIRE_APPROVAL", "REFUSE_AND_ESCALATE"]


@dataclass
class PolicyDecision:
    """Server-owned deterministic policy outcome."""

    decision: PolicyDecisionType
    target_state: Literal["READY_TO_REMEDIATE", "AWAITING_APPROVAL", "ESCALATED"]
    playbook_id: str | None = None
    playbook_version: str | None = None
    risk_tier: str | None = None
    sanitized_parameters: dict[str, Any] = field(default_factory=dict)
    cited_runbook_slug: str | None = None
    reason: str = ""
    checks: dict[str, Any] = field(default_factory=dict)


def evaluate_remediation_policy(
    *,
    asset: Asset | None,
    alertname: str,
    summary_sanitized: str,
    retrieved_docs: list[RetrievedDocument],
    proposal: DiagnosisProposal | None,
    settings: Settings,
) -> PolicyDecision:
    """Evaluate diagnosis, retrieval evidence, applicability, and playbook eligibility."""
    if asset is None:
        return PolicyDecision(
            decision="REFUSE_AND_ESCALATE",
            target_state="ESCALATED",
            reason="Target asset is unknown in CMDB; automated action refused.",
            checks={"known_asset": False},
        )

    if proposal is None:
        return PolicyDecision(
            decision="REFUSE_AND_ESCALATE",
            target_state="ESCALATED",
            reason="Diagnosis generation failed, timed out, or failed Pydantic schema validation.",
            checks={"known_asset": True, "valid_proposal": False},
        )

    if proposal.refusal_recommended:
        return PolicyDecision(
            decision="REFUSE_AND_ESCALATE",
            target_state="ESCALATED",
            reason=f"Diagnosis recommended refusal/escalation: {proposal.reasoning}",
            checks={"known_asset": True, "model_refusal_recommended": True},
        )

    if proposal.uncertainty_level == "HIGH":
        return PolicyDecision(
            decision="REFUSE_AND_ESCALATE",
            target_state="ESCALATED",
            reason="Model reported HIGH uncertainty; escalating to SRE rather than automating.",
            checks={"uncertainty_level": "HIGH"},
        )

    if not proposal.proposed_playbook_id:
        return PolicyDecision(
            decision="REFUSE_AND_ESCALATE",
            target_state="ESCALATED",
            reason="No remediable playbook proposed; escalating with diagnostic context.",
            checks={"proposed_playbook_id": None},
        )

    docs_by_slug = {d.slug: d for d in retrieved_docs}
    cited_docs = [docs_by_slug[s] for s in proposal.cited_runbook_ids if s in docs_by_slug]
    if not cited_docs:
        return PolicyDecision(
            decision="REFUSE_AND_ESCALATE",
            target_state="ESCALATED",
            reason="Proposal did not cite any verified runbook from retrieved context.",
            checks={"cited_valid_runbook": False},
        )

    # Prefer a cited runbook whose applicability explicitly includes target asset
    applicable_cited = [
        d for d in cited_docs if asset.slug in (d.applicability_json.get("services") or [])
    ]
    if not applicable_cited:
        return PolicyDecision(
            decision="REFUSE_AND_ESCALATE",
            target_state="ESCALATED",
            reason=(
                f"Cited runbook(s) {[d.slug for d in cited_docs]} do not list service "
                f"'{asset.slug}' as applicable."
            ),
            checks={"service_applicability": False},
        )

    primary_doc = applicable_cited[0]

    # Retrieval quality heuristic check (never conflate RRF score with cosine similarity)
    passes_vector = primary_doc.vector_similarity >= settings.aegisops_similarity_threshold
    passes_lexical_corroboration = (
        primary_doc.lexical_score >= 0.05 and primary_doc.vector_similarity >= 0.50
    )
    if not (passes_vector or passes_lexical_corroboration):
        return PolicyDecision(
            decision="REFUSE_AND_ESCALATE",
            target_state="ESCALATED",
            cited_runbook_slug=primary_doc.slug,
            reason=(
                f"Retrieval evidence below heuristic bar (vector_similarity={primary_doc.vector_similarity:.3f}, "
                f"threshold={settings.aegisops_similarity_threshold:.2f}, lexical_score={primary_doc.lexical_score:.3f})."
            ),
            checks={
                "vector_similarity": round(primary_doc.vector_similarity, 4),
                "lexical_score": round(primary_doc.lexical_score, 4),
                "rrf_score": round(primary_doc.rrf_score, 6),
                "threshold_passed": False,
            },
        )

    # Runbook must explicitly permit the proposed playbook (e.g. RB-011 DB failover has None)
    if primary_doc.permitted_playbook_id is None:
        return PolicyDecision(
            decision="REFUSE_AND_ESCALATE",
            target_state="ESCALATED",
            cited_runbook_slug=primary_doc.slug,
            reason=(
                f"Matched runbook '{primary_doc.slug}' prohibits automated remediation "
                f"(escalation-only boundary)."
            ),
            checks={"runbook_permits_automation": False},
        )

    if proposal.proposed_playbook_id != primary_doc.permitted_playbook_id:
        return PolicyDecision(
            decision="REFUSE_AND_ESCALATE",
            target_state="ESCALATED",
            cited_runbook_slug=primary_doc.slug,
            reason=(
                f"Model proposed '{proposal.proposed_playbook_id}', but cited runbook "
                f"'{primary_doc.slug}' permits only '{primary_doc.permitted_playbook_id}'."
            ),
            checks={"playbook_matches_runbook": False},
        )

    # Validate server-owned playbook allowlist, target eligibility, and parameter bounds
    valid, server_params, err = validate_playbook_for_asset(
        proposal.proposed_playbook_id, asset, proposal.proposed_parameters
    )
    if not valid:
        return PolicyDecision(
            decision="REFUSE_AND_ESCALATE",
            target_state="ESCALATED",
            cited_runbook_slug=primary_doc.slug,
            reason=err or "Playbook eligibility check failed",
            checks={"playbook_valid": False},
        )

    spec = PLAYBOOK_REGISTRY[proposal.proposed_playbook_id]
    checks = {
        "known_asset": True,
        "service_applicability": True,
        "vector_similarity": round(primary_doc.vector_similarity, 4),
        "lexical_score": round(primary_doc.lexical_score, 4),
        "rrf_score": round(primary_doc.rrf_score, 6),
        "server_risk_tier": spec.risk_tier,
        "alertname": alertname,
        "summary_len": len(summary_sanitized),
    }

    if spec.risk_tier == "HIGH":
        return PolicyDecision(
            decision="REQUIRE_APPROVAL",
            target_state="AWAITING_APPROVAL",
            playbook_id=spec.playbook_id,
            playbook_version=spec.version,
            risk_tier=spec.risk_tier,
            sanitized_parameters=server_params,
            cited_runbook_slug=primary_doc.slug,
            reason=f"Playbook '{spec.playbook_id}' is HIGH risk; requires authenticated SRE TOTP step-up approval.",
            checks=checks,
        )

    return PolicyDecision(
        decision="ALLOW_AUTO_EXECUTE",
        target_state="READY_TO_REMEDIATE",
        playbook_id=spec.playbook_id,
        playbook_version=spec.version,
        risk_tier=spec.risk_tier,
        sanitized_parameters=server_params,
        cited_runbook_slug=primary_doc.slug,
        reason=f"Playbook '{spec.playbook_id}' passed all LOW-risk policy & applicability checks.",
        checks=checks,
    )
