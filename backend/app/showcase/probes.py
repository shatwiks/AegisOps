"""Allowlisted semantic business transaction recovery probes (`Feature J`)."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.k8s.executor import KubernetesExecutor
from app.models.entities import BusinessProbeSample
from app.privacy.scrubber import scrub_text

ALLOWLISTED_PROBE_TARGETS: dict[str, dict[str, str]] = {
    "eligibility-api": {
        "method": "GET",
        "url": "http://127.0.0.1:58081/api/eligibility/check?plan_code=SYNTH-HMO-01",
        "path": "/api/eligibility/check",
        "transaction_label": "Check Patient Eligibility (Synthetic)",
    },
    "claims-processor": {
        "method": "POST",
        "url": "http://127.0.0.1:58082/api/claims/adjudicate",
        "path": "/api/claims/adjudicate",
        "transaction_label": "Adjudicate Synthetic Claim Batch",
    },
    "provider-directory": {
        "method": "GET",
        "url": "http://127.0.0.1:58083/api/providers/search?specialty=primary-care",
        "path": "/api/providers/search",
        "transaction_label": "Search Provider Directory (Synthetic)",
    },
    "postgres-claims-db": {
        "method": "K8S_AND_SQL_CHECK",
        "url": "http://127.0.0.1:58081/api/eligibility/check?plan_code=SYNTH-HMO-01",
        "path": "deployment/postgres-claims-db + /api/eligibility/check",
        "transaction_label": "Verify Demo Claims DB Health",
    },
}


def serialize_probe(sample: BusinessProbeSample) -> dict[str, Any]:
    return {
        "id": str(sample.id),
        "incident_id": str(sample.incident_id) if sample.incident_id else None,
        "demo_run_id": str(sample.demo_run_id) if sample.demo_run_id else None,
        "target_service": sample.target_service,
        "endpoint_path": sample.endpoint_path,
        "probe_type": sample.probe_type,
        "status": sample.status,
        "http_status": sample.http_status,
        "latency_ms": sample.latency_ms,
        "summary": sample.summary_sanitized,
        "details": sample.details_json,
        "checked_at": sample.checked_at.isoformat(),
    }


async def execute_business_probe(
    session: AsyncSession,
    *,
    target_service: str,
    settings: Settings,
    executor: KubernetesExecutor,
    probe_type: str = "manual",
    incident_id: uuid.UUID | None = None,
    demo_run_id: uuid.UUID | None = None,
) -> BusinessProbeSample:
    """Run an allowlisted semantic business probe using fictional data and persist outcome."""
    spec = ALLOWLISTED_PROBE_TARGETS.get(target_service)
    if spec is None:
        raise ValueError(
            f"Target service '{target_service}' is not in allowlisted probe targets "
            f"{sorted(ALLOWLISTED_PROBE_TARGETS.keys())}"
        )

    now = datetime.now(UTC)
    started = time.perf_counter()
    http_status: int | None = None
    latency_ms: float | None = None
    probe_status = "UNAVAILABLE"
    summary = "Probe unavailable"
    details: dict[str, Any] = {
        "transaction_label": spec["transaction_label"],
        "synthetic": True,
    }

    if target_service == "postgres-claims-db":
        try:
            snap = await executor.read_deployment_snapshot(
                cluster=settings.aegisops_k8s_context,
                namespace=settings.aegisops_k8s_allowed_namespaces[0],
                deployment_name="postgres-claims-db",
            )
            sim_fault = snap.annotations.get("aegisops.io/simulated-fault")
            details["deployment_rollout"] = snap.rollout_status
            if sim_fault:
                probe_status = "FAIL"
                summary = f"Demo DB reports simulated fault: {sim_fault} (manual DBA intervention required)."
                details["error_code"] = sim_fault
            else:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get(spec["url"])
                    latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
                    http_status = resp.status_code
                    body = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
                    if resp.status_code == 200 and body.get("eligible") is True:
                        probe_status = "PASS"
                        summary = f"Demo DB healthy and backing eligibility transaction succeeded ({latency_ms}ms)."
                    else:
                        probe_status = "FAIL"
                        summary = f"Backing eligibility transaction returned HTTP {resp.status_code}."
        except Exception as exc:
            latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
            probe_status = "UNAVAILABLE"
            summary = f"Probe infrastructure unavailable: {type(exc).__name__}"
    else:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                if spec["method"] == "POST":
                    resp = await client.post(spec["url"])
                else:
                    resp = await client.get(spec["url"])
                latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
                http_status = resp.status_code
                resp_body: dict[str, Any] = {}
                try:
                    resp_body = resp.json()
                except Exception:
                    resp_body = {}

                if target_service == "eligibility-api":
                    semantic_ok = (
                        resp.status_code == 200
                        and resp_body.get("eligible") is True
                        and resp_body.get("synthetic") is True
                    )
                    details["release_version"] = resp_body.get("version")
                    details["error_code"] = resp_body.get("error_code")
                    if semantic_ok:
                        probe_status = "PASS"
                        summary = (
                            f"Synthetic eligibility check passed "
                            f"({resp_body.get('version', 'ok')}, {latency_ms}ms)."
                        )
                    else:
                        probe_status = "FAIL"
                        err_code = resp_body.get("error_code") or f"HTTP_{resp.status_code}"
                        summary = (
                            f"Synthetic eligibility check failed: {err_code} "
                            f"(HTTP {resp.status_code})."
                        )

                elif target_service == "claims-processor":
                    semantic_ok = (
                        resp.status_code == 200
                        and resp_body.get("adjudicated") is True
                        and resp_body.get("synthetic") is True
                    )
                    details["error_code"] = resp_body.get("error_code")
                    if semantic_ok:
                        probe_status = "PASS"
                        summary = f"Synthetic claim batch adjudication succeeded ({latency_ms}ms)."
                    else:
                        probe_status = "FAIL"
                        err_code = resp_body.get("error_code") or f"HTTP_{resp.status_code}"
                        summary = (
                            f"Synthetic claim adjudication failed: {err_code} "
                            f"(HTTP {resp.status_code})."
                        )

                elif target_service == "provider-directory":
                    providers = resp_body.get("providers") or []
                    semantic_ok = resp.status_code == 200 and len(providers) >= 1
                    details["providers_count"] = len(providers)
                    details["service_elapsed_ms"] = resp_body.get("elapsed_ms")
                    if not semantic_ok:
                        probe_status = "FAIL"
                        summary = f"Provider search returned invalid/empty response (HTTP {resp.status_code})."
                    elif latency_ms > 500.0:
                        probe_status = "DEGRADED"
                        summary = f"Provider search succeeded semantically but latency breached 500ms ({latency_ms}ms)."
                    else:
                        probe_status = "PASS"
                        summary = f"Provider search returned {len(providers)} synthetic clinic(s) in {latency_ms}ms."
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError) as exc:
            latency_ms = round((time.perf_counter() - started) * 1000.0, 1)
            probe_status = "UNAVAILABLE"
            summary = f"Probe request timed out or target unreachable ({type(exc).__name__})."

    clean_counts: dict[str, int] = {}
    safe_summary = scrub_text(summary, clean_counts)
    sample = BusinessProbeSample(
        incident_id=incident_id,
        demo_run_id=demo_run_id,
        target_service=target_service,
        endpoint_path=spec["path"],
        probe_type=probe_type,
        status=probe_status,
        http_status=http_status,
        latency_ms=latency_ms,
        summary_sanitized=safe_summary,
        details_json=details,
        checked_at=now,
    )
    session.add(sample)
    await session.flush()
    return sample


async def list_business_probes(
    session: AsyncSession,
    *,
    target_service: str | None = None,
    incident_id: uuid.UUID | None = None,
    demo_run_id: uuid.UUID | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    stmt = select(BusinessProbeSample).order_by(BusinessProbeSample.checked_at.desc()).limit(limit)
    if target_service:
        stmt = stmt.where(BusinessProbeSample.target_service == target_service)
    if incident_id:
        stmt = stmt.where(BusinessProbeSample.incident_id == incident_id)
    if demo_run_id:
        stmt = stmt.where(BusinessProbeSample.demo_run_id == demo_run_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [serialize_probe(r) for r in rows]
