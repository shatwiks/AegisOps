"""Unit & adversarial tests for server-controlled policy refusal and playbook bounds."""

from __future__ import annotations

from app.config import Settings
from app.models.entities import Asset
from app.playbooks.registry import validate_playbook_for_asset
from app.policy.engine import evaluate_remediation_policy
from app.rag.diagnosis import DiagnosisProposal
from app.rag.retriever import RetrievedDocument


def _test_settings() -> Settings:
    return Settings(
        aegisops_database_url="postgresql+asyncpg://u:pass123456@127.0.0.1:55432/aegisops",
        aegisops_redis_url="redis://127.0.0.1:56379/0",
        aegisops_webhook_hmac_secret="a" * 32,
        aegisops_webhook_bearer_token="b" * 32,
        aegisops_totp_encryption_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
        aegisops_session_secret="c" * 32,
        _env_file=None,  # type: ignore[call-arg]
    )


def _asset(
    slug: str = "eligibility-api",
    *,
    asset_type: str = "SERVICE",
    stateless: bool = True,
    known_good_image: str | None = "aegisops/eligibility-api:v1.0.0-good",
) -> Asset:
    return Asset(
        slug=slug,
        name=slug,
        namespace="aegisops-healthcare",
        cluster="kind-aegisops-local",
        asset_type=asset_type,
        criticality="TIER_1_CRITICAL",
        owner_team="benefits-sre",
        stateless_eligible=stateless,
        known_good_image=known_good_image,
        k8s_deployment_name=slug,
    )


def _doc(
    slug: str = "rb-002-eligibility-db-pool-exhaustion",
    *,
    services: list[str] | None = None,
    permitted_playbook_id: str | None = "stateless_deployment_restart",
    risk_tier: str = "LOW",
    vec_sim: float = 0.84,
    lex_score: float = 0.22,
) -> RetrievedDocument:
    return RetrievedDocument(
        slug=slug,
        title="RB-002",
        doc_type="RUNBOOK",
        service_slug=(services or ["eligibility-api"])[0],
        risk_tier=risk_tier,
        permitted_playbook_id=permitted_playbook_id,
        applicability_json={"services": services or ["eligibility-api"]},
        preconditions_json={},
        evidence_requirements_json=["db_pool_active_connections"],
        symptoms="Pool exhausted",
        body_markdown="Restart stateless deployment.",
        vector_similarity=vec_sim,
        lexical_score=lex_score,
        rrf_score=0.03,
        vector_rank=1,
        lexical_rank=1,
    )


def _proposal(
    *,
    cited: list[str] | None = None,
    playbook: str | None = "stateless_deployment_restart",
    params: dict[str, int | str] | None = None,
    uncertainty: str = "LOW",
    refusal: bool = False,
) -> DiagnosisProposal:
    return DiagnosisProposal(
        root_cause_summary="DB pool exhausted on eligibility-api",
        cited_runbook_ids=cited if cited is not None else ["rb-002-eligibility-db-pool-exhaustion"],
        evidence_quotes=["ERR_PG_POOL_TIMEOUT_57P03"],
        proposed_playbook_id=playbook,
        proposed_parameters=params or {},
        uncertainty_level=uncertainty,  # type: ignore[arg-type]
        refusal_recommended=refusal,
        reasoning="Matches RB-002.",
    )


def test_policy_allows_eligible_low_risk_remediation() -> None:
    decision = evaluate_remediation_policy(
        asset=_asset(),
        alertname="EligibilityDbPoolExhausted",
        summary_sanitized="ERR_PG_POOL_TIMEOUT_57P03",
        retrieved_docs=[_doc()],
        proposal=_proposal(),
        settings=_test_settings(),
    )
    assert decision.decision == "ALLOW_AUTO_EXECUTE"
    assert decision.target_state == "READY_TO_REMEDIATE"
    assert decision.playbook_id == "stateless_deployment_restart"


def test_policy_gates_high_risk_rollback_and_ignores_llm_image_tag() -> None:
    doc = _doc(
        slug="rb-004-bad-canary-release-rollback",
        services=["eligibility-api"],
        permitted_playbook_id="deployment_image_rollback",
        risk_tier="HIGH",
    )
    prop = _proposal(
        cited=["rb-004-bad-canary-release-rollback"],
        playbook="deployment_image_rollback",
        params={"target_image": "evil-attacker/backdoor:latest", "command": "rm -rf /"},
    )
    decision = evaluate_remediation_policy(
        asset=_asset(known_good_image="aegisops/eligibility-api:v1.0.0-good"),
        alertname="High5xxErrorRate",
        summary_sanitized="ERR_CANARY_IMG_SHA_BAD_9921",
        retrieved_docs=[doc],
        proposal=prop,
        settings=_test_settings(),
    )
    assert decision.decision == "REQUIRE_APPROVAL"
    assert decision.target_state == "AWAITING_APPROVAL"
    assert decision.sanitized_parameters == {"target_image": "aegisops/eligibility-api:v1.0.0-good"}


def test_policy_refuses_unknown_asset_malformed_model_and_db_failover() -> None:
    cfg = _test_settings()

    # Unknown asset
    d_unk = evaluate_remediation_policy(
        asset=None,
        alertname="UnknownAlert",
        summary_sanitized="something broke",
        retrieved_docs=[_doc()],
        proposal=_proposal(),
        settings=cfg,
    )
    assert d_unk.decision == "REFUSE_AND_ESCALATE"

    # Malformed / unavailable model
    d_none = evaluate_remediation_policy(
        asset=_asset(),
        alertname="EligibilityDbPoolExhausted",
        summary_sanitized="ERR_PG_POOL_TIMEOUT_57P03",
        retrieved_docs=[_doc()],
        proposal=None,
        settings=cfg,
    )
    assert d_none.decision == "REFUSE_AND_ESCALATE"

    # Database failover runbook explicitly refuses automation
    db_doc = _doc(
        slug="rb-011-postgres-replication-lag",
        services=["postgres-claims-db"],
        permitted_playbook_id=None,
        risk_tier="HIGH",
    )
    d_db = evaluate_remediation_policy(
        asset=_asset(
            "postgres-claims-db", asset_type="DATABASE", stateless=False, known_good_image=None
        ),
        alertname="PostgresPrimaryDown",
        summary_sanitized="ERR_PG_REPLICATION_LAG",
        retrieved_docs=[db_doc],
        proposal=_proposal(
            cited=["rb-011-postgres-replication-lag"], playbook="stateless_deployment_restart"
        ),
        settings=cfg,
    )
    assert d_db.decision == "REFUSE_AND_ESCALATE"
    assert d_db.target_state == "ESCALATED"


def test_policy_refuses_low_similarity_and_out_of_bounds_params() -> None:
    cfg = _test_settings()

    # Low similarity and zero lexical match -> refused
    weak_doc = _doc(vec_sim=0.41, lex_score=0.0)
    d_weak = evaluate_remediation_policy(
        asset=_asset(),
        alertname="WeirdSignal",
        summary_sanitized="Unrecognized cosmic bitflip",
        retrieved_docs=[weak_doc],
        proposal=_proposal(),
        settings=cfg,
    )
    assert d_weak.decision == "REFUSE_AND_ESCALATE"

    # Parameter bounds rejection
    ok_scale, _, err_scale = validate_playbook_for_asset(
        "replica_scale_out_bounded", _asset("provider-directory"), {"target_replicas": 99}
    )
    assert not ok_scale and "bounds" in (err_scale or "")

    ok_mem, _, err_mem = validate_playbook_for_asset(
        "memory_limit_increase_bounded", _asset("claims-processor"), {"memory_mi": 4096}
    )
    assert not ok_mem and "bounds" in (err_mem or "")

    ok_cache, _, _ = validate_playbook_for_asset(
        "scoped_cache_key_eviction",
        _asset("redis-session-cache", asset_type="CACHE", stateless=False, known_good_image=None),
        {"key_prefix": "*"},
    )
    assert not ok_cache
