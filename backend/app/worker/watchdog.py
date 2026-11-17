"""Sustained recovery watchdog verifying K8s rollout, fresh Prometheus telemetry, and functional probes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings
from app.k8s.executor import KubernetesExecutor
from app.models.entities import Asset

_SERVICE_LOCAL_PORTS: dict[str, int] = {
    "eligibility-api": 58081,
    "claims-processor": 58082,
    "provider-directory": 58083,
}


@dataclass
class HealthProbeSample:
    """Single timestamped health observation across cluster, HTTP probe, and Prometheus."""

    checked_at: datetime
    healthy: bool
    rollout_ready: bool
    http_probe_ok: bool
    metrics_fresh_and_ok: bool
    reasons: list[str] = field(default_factory=list)
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)


async def query_prometheus_scalar(
    prom_url: str,
    promql: str,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> float | None:
    """Query Prometheus instant API; returns None if missing, stale, or unreachable."""
    own_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=4.0)
    try:
        resp = await client.get(f"{prom_url.rstrip('/')}/api/v1/query", params={"query": promql})
        if resp.status_code != 200:
            return None
        payload = resp.json()
        result = payload.get("data", {}).get("result", [])
        if not result:
            return None
        ts_val = result[0].get("value", [])
        if len(ts_val) < 2:
            return None
        # Reject stale samples older than 60s
        sample_ts = float(ts_val[0])
        if datetime.now(UTC).timestamp() - sample_ts > 60.0:
            return None
        val = float(ts_val[1])
        if val != val:  # NaN check
            return None
        return val
    except Exception:
        return None
    finally:
        if own_client:
            await client.aclose()


async def collect_health_sample(
    *,
    asset: Asset,
    settings: Settings,
    executor: KubernetesExecutor,
    service_base_url_override: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> HealthProbeSample:
    """Evaluate deployment readiness, live HTTP functional probe, and Prometheus telemetry."""
    now = datetime.now(UTC)
    reasons: list[str] = []
    metrics_snap: dict[str, Any] = {}

    # 1. Kubernetes rollout check
    rollout_ready = False
    try:
        snap = await executor.read_deployment_snapshot(
            cluster=asset.cluster,
            namespace=asset.namespace,
            deployment_name=asset.k8s_deployment_name or asset.name,
        )
        rollout_ready = (
            snap.replicas > 0
            and snap.ready_replicas >= snap.replicas
            and snap.available_replicas >= snap.replicas
            and snap.updated_replicas >= snap.replicas
        )
        metrics_snap["k8s_replicas"] = snap.replicas
        metrics_snap["k8s_ready_replicas"] = snap.ready_replicas
        metrics_snap["k8s_image"] = snap.image
        metrics_snap["k8s_memory_limit"] = snap.memory_limit
        if not rollout_ready:
            reasons.append(f"K8s rollout not ready (ready={snap.ready_replicas}/{snap.replicas})")
    except Exception as exc:
        reasons.append(f"K8s snapshot error: {type(exc).__name__}")

    # 2. HTTP /readyz + functional probe
    port = _SERVICE_LOCAL_PORTS.get(asset.slug)
    base_url = service_base_url_override or (f"http://127.0.0.1:{port}" if port else None)
    http_probe_ok = False
    own_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=6.0)
    try:
        if base_url is not None:
            r_ready = await client.get(f"{base_url.rstrip('/')}/readyz")
            if r_ready.status_code != 200:
                reasons.append(f"/readyz returned HTTP {r_ready.status_code}")
            else:
                # Functional endpoint check where applicable
                func_ok = True
                if asset.slug == "eligibility-api":
                    r_func = await client.get(f"{base_url.rstrip('/')}/api/eligibility/check")
                    func_ok = r_func.status_code == 200
                    if not func_ok:
                        reasons.append(f"/api/eligibility/check returned HTTP {r_func.status_code}")
                elif asset.slug == "provider-directory":
                    r_func = await client.get(f"{base_url.rstrip('/')}/api/providers/search")
                    func_ok = r_func.status_code == 200
                    if not func_ok:
                        reasons.append(f"/api/providers/search returned HTTP {r_func.status_code}")
                http_probe_ok = func_ok
        else:
            reasons.append("No probe endpoint mapped for asset")

        # 3. Fresh Prometheus telemetry checks (missing/stale samples fail safe as unknown)
        prom_url = settings.aegisops_prometheus_url
        total_req_rate = await query_prometheus_scalar(
            prom_url,
            f'sum(rate(http_requests_total{{service="{asset.slug}"}}[30s]))',
            http_client=client,
        )
        metrics_snap["http_req_rate_30s"] = total_req_rate

        if total_req_rate is None:
            metrics_fresh_and_ok = False
            metrics_snap["http_5xx_ratio"] = None
            reasons.append("Prometheus request rate metric missing or stale (unknown health)")
        else:
            err_ratio = await query_prometheus_scalar(
                prom_url,
                f'(sum(rate(http_requests_total{{service="{asset.slug}",status=~"5.."}}[30s])) or vector(0)) / '
                f'clamp_min(sum(rate(http_requests_total{{service="{asset.slug}"}}[30s])), 0.001)',
                http_client=client,
            )
            metrics_snap["http_5xx_ratio"] = err_ratio
            if err_ratio is None:
                metrics_fresh_and_ok = False
                reasons.append("Prometheus 5xx metric missing or stale (unknown health)")
            elif err_ratio > 0.05:
                metrics_fresh_and_ok = False
                reasons.append(f"5xx error ratio elevated ({err_ratio:.3f} > 0.05)")
            else:
                metrics_fresh_and_ok = True

        if asset.slug == "eligibility-api" and metrics_fresh_and_ok:
            pool_ratio = await query_prometheus_scalar(
                prom_url,
                'db_pool_active_connections{service="eligibility-api"} / '
                'clamp_min(db_pool_max_connections{service="eligibility-api"}, 1)',
                http_client=client,
            )
            metrics_snap["db_pool_ratio"] = pool_ratio
            if pool_ratio is None or pool_ratio >= 0.80:
                metrics_fresh_and_ok = False
                reasons.append(f"DB pool metric unhealthy or missing ({pool_ratio})")

        elif asset.slug == "claims-processor" and metrics_fresh_and_ok:
            mem_ratio = await query_prometheus_scalar(
                prom_url,
                'simulated_memory_allocated_bytes{service="claims-processor"} / '
                'clamp_min(container_memory_limit_bytes{service="claims-processor"}, 1)',
                http_client=client,
            )
            metrics_snap["memory_ratio"] = mem_ratio
            if mem_ratio is None or mem_ratio >= 0.80:
                metrics_fresh_and_ok = False
                reasons.append(f"Memory utilization unhealthy or missing ({mem_ratio})")

        elif asset.slug == "provider-directory" and metrics_fresh_and_ok:
            p95_sec = await query_prometheus_scalar(
                prom_url,
                'http_recent_p95_latency_seconds{service="provider-directory"}',
                http_client=client,
            )
            metrics_snap["latency_p95_seconds"] = p95_sec
            if p95_sec is None or p95_sec > 0.50:
                metrics_fresh_and_ok = False
                reasons.append(f"p95 latency unhealthy or missing ({p95_sec})")

    except Exception as exc:
        reasons.append(f"Probe exception: {type(exc).__name__}")
        metrics_fresh_and_ok = False
    finally:
        if own_client:
            await client.aclose()

    healthy = rollout_ready and http_probe_ok and metrics_fresh_and_ok
    return HealthProbeSample(
        checked_at=now,
        healthy=healthy,
        rollout_ready=rollout_ready,
        http_probe_ok=http_probe_ok,
        metrics_fresh_and_ok=metrics_fresh_and_ok,
        reasons=reasons,
        metrics_snapshot=metrics_snap,
    )


async def verify_sustained_recovery(
    *,
    asset: Asset,
    settings: Settings,
    executor: KubernetesExecutor,
    probe_fn: Any = collect_health_sample,
    max_wait_seconds: int | None = None,
    on_sample_callback: Any = None,
) -> tuple[bool, datetime | None, list[HealthProbeSample]]:
    """Require continuous healthy samples across settings.aegisops_recovery_window_seconds."""
    window_sec = float(settings.aegisops_recovery_window_seconds)
    poll_sec = float(settings.aegisops_recovery_poll_interval_seconds)
    total_deadline_sec = float(max_wait_seconds or (window_sec * 4 + 60))

    loop = asyncio.get_running_loop()
    start_mono = loop.time()
    started_at = datetime.now(UTC)
    healthy_since_mono: float | None = None
    first_recovered_at: datetime | None = None
    samples: list[HealthProbeSample] = []
    reset_count = 0
    last_reset_reason: str | None = None

    while (loop.time() - start_mono) < total_deadline_sec:
        sample: HealthProbeSample = await probe_fn(
            asset=asset, settings=settings, executor=executor
        )
        samples.append(sample)

        elapsed_healthy = 0.0
        if sample.healthy:
            if healthy_since_mono is None:
                healthy_since_mono = loop.time()
                first_recovered_at = sample.checked_at
            elapsed_healthy = min(window_sec, loop.time() - healthy_since_mono)
        else:
            # Any unhealthy tick resets the sustained healthy window
            if healthy_since_mono is not None:
                reset_count += 1
                last_reset_reason = "; ".join(sample.reasons) or "Probe became unhealthy"
            healthy_since_mono = None
            first_recovered_at = None

        if on_sample_callback is not None:
            await on_sample_callback(
                sample=sample,
                started_at=started_at,
                first_recovered_at=first_recovered_at,
                elapsed_healthy_seconds=elapsed_healthy,
                window_seconds=window_sec,
                sample_count=len(samples),
                reset_count=reset_count,
                last_reset_reason=last_reset_reason,
            )

        if sample.healthy and elapsed_healthy >= window_sec:
            return True, first_recovered_at, samples

        await asyncio.sleep(poll_sec)

    return False, first_recovered_at, samples
