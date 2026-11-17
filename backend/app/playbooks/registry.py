"""Versioned server-owned remediation playbook registry and parameter validators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.models.entities import Asset

RiskTier = Literal["LOW", "HIGH"]


@dataclass(frozen=True)
class PlaybookSpec:
    """Server-owned immutable specification for an allowlisted deterministic playbook."""

    playbook_id: str
    version: str
    risk_tier: RiskTier
    description: str
    require_stateless: bool
    require_known_good_image: bool
    allowed_asset_types: frozenset[str]
    allowed_services: frozenset[str] | None
    idempotency_strategy: str
    timeout_seconds: int
    default_parameters: dict[str, Any]


PLAYBOOK_REGISTRY: dict[str, PlaybookSpec] = {
    "replica_scale_out_bounded": PlaybookSpec(
        playbook_id="replica_scale_out_bounded",
        version="1.0.0",
        risk_tier="LOW",
        description="Deterministically set Deployment spec.replicas within bounded ceiling [1, 4].",
        require_stateless=True,
        require_known_good_image=False,
        allowed_asset_types=frozenset({"SERVICE"}),
        allowed_services=frozenset({"provider-directory", "eligibility-api", "claims-processor"}),
        idempotency_strategy="Absolute target replica count (never blind +N increment).",
        timeout_seconds=90,
        default_parameters={"target_replicas": 3},
    ),
    "stateless_deployment_restart": PlaybookSpec(
        playbook_id="stateless_deployment_restart",
        version="1.0.0",
        risk_tier="LOW",
        description="Controlled rolling restart via kubectl.kubernetes.io/restartedAt pod template annotation.",
        require_stateless=True,
        require_known_good_image=False,
        allowed_asset_types=frozenset({"SERVICE"}),
        allowed_services=frozenset({"eligibility-api", "provider-directory", "claims-processor"}),
        idempotency_strategy="Keyed by incident_id + attempt token; checks rollout generation before retry.",
        timeout_seconds=120,
        default_parameters={"rollout_strategy": "RollingUpdate"},
    ),
    "memory_limit_increase_bounded": PlaybookSpec(
        playbook_id="memory_limit_increase_bounded",
        version="1.0.0",
        risk_tier="HIGH",
        description="Patch container memory limit within strict ceiling [128Mi, 512Mi]; requires MFA approval.",
        require_stateless=False,
        require_known_good_image=False,
        allowed_asset_types=frozenset({"SERVICE"}),
        allowed_services=frozenset({"claims-processor", "eligibility-api", "provider-directory"}),
        idempotency_strategy="Absolute target memory_mi (idempotent desired limit).",
        timeout_seconds=120,
        default_parameters={"memory_mi": 384},
    ),
    "deployment_image_rollback": PlaybookSpec(
        playbook_id="deployment_image_rollback",
        version="1.0.0",
        risk_tier="HIGH",
        description="Roll back Deployment container image strictly to server-registered Asset.known_good_image; requires MFA approval.",
        require_stateless=False,
        require_known_good_image=True,
        allowed_asset_types=frozenset({"SERVICE"}),
        allowed_services=frozenset({"eligibility-api", "claims-processor", "provider-directory"}),
        idempotency_strategy="Target image fixed from CMDB Asset.known_good_image.",
        timeout_seconds=150,
        default_parameters={},
    ),
    "scoped_cache_key_eviction": PlaybookSpec(
        playbook_id="scoped_cache_key_eviction",
        version="1.0.0",
        risk_tier="LOW",
        description="Delete only allowlisted stale session lock prefix session:lock:stale:* in demo Redis.",
        require_stateless=False,
        require_known_good_image=False,
        allowed_asset_types=frozenset({"CACHE", "SERVICE"}),
        allowed_services=frozenset({"redis-session-cache", "eligibility-api"}),
        idempotency_strategy="SCAN + UNLINK on explicit prefix only (FLUSHALL/FLUSHDB forbidden).",
        timeout_seconds=45,
        default_parameters={"key_prefix": "session:lock:stale:"},
    ),
}


def validate_playbook_for_asset(
    playbook_id: str,
    asset: Asset | None,
    raw_params: dict[str, Any] | None,
) -> tuple[bool, dict[str, Any], str | None]:
    """Validate playbook existence, asset eligibility, and strict parameter bounds.

    Returns `(is_valid, sanitized_server_params, error_reason)`.
    Server-owned defaults and CMDB values override untrusted LLM parameters.
    """
    spec = PLAYBOOK_REGISTRY.get(playbook_id)
    if spec is None:
        return False, {}, f"Playbook '{playbook_id}' is not in the server allowlist"

    if asset is None:
        return False, {}, "Target asset is unknown in CMDB; autonomous remediation disallowed"

    if asset.asset_type not in spec.allowed_asset_types:
        return (
            False,
            {},
            f"Asset type '{asset.asset_type}' is ineligible for playbook '{playbook_id}'",
        )

    if spec.allowed_services is not None and asset.slug not in spec.allowed_services:
        return (
            False,
            {},
            f"Asset '{asset.slug}' is not in allowlisted targets for '{playbook_id}'",
        )

    if spec.require_stateless and not asset.stateless_eligible:
        return (
            False,
            {},
            f"Asset '{asset.slug}' is stateful (stateless_eligible=False); '{playbook_id}' refused",
        )

    if spec.require_known_good_image and not asset.known_good_image:
        return (
            False,
            {},
            f"Asset '{asset.slug}' lacks a server-registered known_good_image for rollback",
        )

    params = dict(spec.default_parameters)
    incoming = raw_params or {}

    if playbook_id == "replica_scale_out_bounded":
        raw_rep = incoming.get("target_replicas", params["target_replicas"])
        try:
            target_replicas = int(raw_rep)
        except (TypeError, ValueError):
            return False, {}, "Invalid target_replicas parameter"
        if target_replicas < 1 or target_replicas > 4:
            return False, {}, f"target_replicas={target_replicas} violates policy bounds [1, 4]"
        params = {"target_replicas": target_replicas}

    elif playbook_id == "memory_limit_increase_bounded":
        raw_mem = incoming.get("memory_mi", params["memory_mi"])
        try:
            memory_mi = int(raw_mem)
        except (TypeError, ValueError):
            return False, {}, "Invalid memory_mi parameter"
        if memory_mi < 128 or memory_mi > 512:
            return False, {}, f"memory_mi={memory_mi} violates policy bounds [128, 512]"
        params = {"memory_mi": memory_mi}

    elif playbook_id == "deployment_image_rollback":
        # Always force server-owned known_good_image; ignore any LLM-supplied image tag
        params = {"target_image": asset.known_good_image}

    elif playbook_id == "scoped_cache_key_eviction":
        prefix = str(incoming.get("key_prefix", "session:lock:stale:"))
        if not prefix.startswith("session:lock:stale:") or "*" in prefix.replace(
            "session:lock:stale:", ""
        ):
            return False, {}, "Only scoped prefix 'session:lock:stale:' is permitted"
        params = {"key_prefix": "session:lock:stale:"}

    return True, params, None
