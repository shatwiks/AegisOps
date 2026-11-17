"""Integration & behavioral tests for sustained recovery watchdog semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.config import get_settings
from app.k8s.executor import KubernetesExecutor, TargetSnapshot
from app.models.entities import Asset
from app.worker.watchdog import HealthProbeSample, collect_health_sample, verify_sustained_recovery


def _elig_asset() -> Asset:
    return Asset(
        slug="eligibility-api",
        name="eligibility-api",
        namespace="aegisops-healthcare",
        cluster="kind-aegisops-local",
        asset_type="SERVICE",
        criticality="TIER_1_CRITICAL",
        owner_team="benefits-sre",
        stateless_eligible=True,
        known_good_image="aegisops/eligibility-api:v1.0.0-good",
        k8s_deployment_name="eligibility-api",
    )


@pytest.mark.asyncio
async def test_watchdog_refuses_readiness_when_metrics_missing_or_unhealthy() -> None:
    settings = get_settings().model_copy(
        update={
            "aegisops_prometheus_url": "http://127.0.0.1:59999",  # unreachable -> missing/unknown metrics
            "aegisops_recovery_window_seconds": 5,
            "aegisops_recovery_poll_interval_seconds": 1,
        }
    )
    executor = KubernetesExecutor(settings)
    executor.read_deployment_snapshot = AsyncMock(  # type: ignore[method-assign]
        return_value=TargetSnapshot(
            cluster="kind-aegisops-local",
            namespace="aegisops-healthcare",
            deployment="eligibility-api",
            uid="uid-1",
            resource_version="1",
            generation=1,
            replicas=1,
            ready_replicas=1,
            available_replicas=1,
            updated_replicas=1,
            image="aegisops/eligibility-api:v1.0.0-good",
            memory_limit="256Mi",
            restarted_at=None,
            labels={"aegisops.io/managed": "true"},
        )
    )
    # Even if K8s rollout is ready and HTTP /readyz responds 200, unreachable/missing Prometheus
    # telemetry must report healthy=False (unknown health != success)
    sample = await collect_health_sample(
        asset=_elig_asset(),
        settings=settings,
        executor=executor,
        service_base_url_override="http://127.0.0.1:58081",
    )
    assert sample.rollout_ready is True
    assert sample.metrics_fresh_and_ok is False
    assert sample.healthy is False


@pytest.mark.asyncio
async def test_watchdog_requires_unbroken_sustained_healthy_window() -> None:
    settings = get_settings().model_copy(
        update={"aegisops_recovery_window_seconds": 5, "aegisops_recovery_poll_interval_seconds": 1}
    )
    executor = KubernetesExecutor(settings)
    asset = _elig_asset()

    # Pattern: healthy -> healthy -> UNHEALTHY (must reset window!) -> then continuous healthy
    sequence = iter([True, True, False, True, True, True, True, True, True, True])

    async def fake_probe(**_: object) -> HealthProbeSample:
        is_ok = next(sequence, True)
        return HealthProbeSample(
            checked_at=datetime.now(UTC),
            healthy=is_ok,
            rollout_ready=True,
            http_probe_ok=is_ok,
            metrics_fresh_and_ok=is_ok,
            reasons=[] if is_ok else ["transient spike"],
        )

    ok, first_rec, samples = await verify_sustained_recovery(
        asset=asset,
        settings=settings,
        executor=executor,
        probe_fn=fake_probe,
        max_wait_seconds=12,
    )
    assert ok is True
    assert first_rec is not None
    # Because tick #3 failed, window had to restart at tick #4, so total samples >= 8
    assert len(samples) >= 8
