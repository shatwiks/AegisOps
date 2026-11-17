"""Shared telemetry, Prometheus metrics, OTel exporter, and health scaffolding for demo services."""

from __future__ import annotations

import hmac
import os
import time
from collections import deque
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests handled by synthetic healthcare service",
    ["service", "method", "path", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency distribution",
    ["service", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.8, 1.2, 2.5, 5.0),
)

RELEASE_BUILD_STATUS = Gauge(
    "release_build_status",
    "1 if service image build is healthy, 0 if broken canary",
    ["service", "version"],
)

DB_POOL_ACTIVE = Gauge(
    "db_pool_active_connections",
    "Active database pool connections",
    ["service"],
)

DB_POOL_MAX = Gauge(
    "db_pool_max_connections",
    "Maximum database pool connections",
    ["service"],
)

MEMORY_WORKING_SET_BYTES = Gauge(
    "simulated_memory_allocated_bytes",
    "Service batch memory working set in bytes",
    ["service"],
)

MEMORY_LIMIT_BYTES = Gauge(
    "container_memory_limit_bytes",
    "Kubernetes Downward API container memory limit in bytes",
    ["service"],
)

CPU_PRESSURE_ACTIVE = Gauge(
    "cpu_pressure_active",
    "1 if service is under sustained CPU/concurrency load pressure",
    ["service"],
)

HTTP_RECENT_P95_SECONDS = Gauge(
    "http_recent_p95_latency_seconds",
    "Rolling 20s p95 application request latency in seconds",
    ["service"],
)


def configure_telemetry(
    app: FastAPI, service_name: str, release_version: str, broken: bool
) -> None:
    """Wire OpenTelemetry OTLP HTTP exporter and Prometheus HTTP timing middleware."""
    otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if otel_endpoint:
        resource = Resource.create(
            {"service.name": service_name, "service.version": release_version}
        )
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(
            endpoint=f"{otel_endpoint.rstrip('/')}/v1/traces", timeout=2.0
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)

    RELEASE_BUILD_STATUS.labels(service=service_name, version=release_version).set(
        0.0 if broken else 1.0
    )
    HTTP_RECENT_P95_SECONDS.labels(service=service_name).set(0.01)
    recent_samples: deque[tuple[float, float]] = deque(maxlen=500)

    def _refresh_recent_p95() -> None:
        cutoff = time.monotonic() - 12.0
        while recent_samples and recent_samples[0][0] < cutoff:
            recent_samples.popleft()
        if not recent_samples:
            HTTP_RECENT_P95_SECONDS.labels(service=service_name).set(0.01)
            return
        ordered = sorted(dur for _, dur in recent_samples)
        idx = min(len(ordered) - 1, int(0.95 * (len(ordered) - 1)))
        HTTP_RECENT_P95_SECONDS.labels(service=service_name).set(ordered[idx])

    @app.middleware("http")
    async def prometheus_middleware(request: Request, call_next: Any) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = time.perf_counter() - start
        path = request.url.path
        if path != "/metrics":
            HTTP_REQUESTS_TOTAL.labels(
                service=service_name,
                method=request.method,
                path=path,
                status=str(response.status_code),
            ).inc()
            HTTP_REQUEST_DURATION.labels(service=service_name, path=path).observe(
                elapsed
            )
            if path not in ("/healthz", "/readyz"):
                recent_samples.append((time.monotonic(), elapsed))
                _refresh_recent_p95()
        return response

    @app.get("/metrics")
    async def metrics() -> Response:
        _refresh_recent_p95()
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def verify_internal_fault_token(
    x_fault_token: str | None = Header(default=None),
) -> None:
    """Authenticate internal chaos fault-injection requests."""
    expected = os.getenv("DEMO_INTERNAL_FAULT_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Fault token not configured")
    if not x_fault_token or not hmac.compare_digest(x_fault_token.strip(), expected):
        raise HTTPException(status_code=401, detail="Invalid X-Fault-Token")
