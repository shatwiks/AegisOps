"""Synthetic Claims Processor microservice with Kubernetes Downward API memory limit observation."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
import psycopg
import redis
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.base_service import (
    MEMORY_LIMIT_BYTES,
    MEMORY_WORKING_SET_BYTES,
    configure_telemetry,
    verify_internal_fault_token,
)

SERVICE_NAME = "claims-processor"
RELEASE_VERSION = os.getenv("AEGISOPS_RELEASE_VERSION", "v1.0.0-good")
POSTGRES_DSN = os.getenv(
    "DEMO_POSTGRES_DSN",
    "postgresql://demo:demopass@postgres-claims-db:5432/claims_demo",
)
REDIS_URL = os.getenv("DEMO_REDIS_URL", "redis://redis-session-cache:6379/0")
ELIGIBILITY_URL = os.getenv("ELIGIBILITY_API_URL", "http://eligibility-api:8081")
BATCH_DEMAND_KEY = "aegisops:demo:claims_batch_mb"

app = FastAPI(title="AegisOps Synthetic Claims Processor", version=RELEASE_VERSION)
configure_telemetry(app, SERVICE_NAME, RELEASE_VERSION, broken=False)

_redis_client = redis.Redis.from_url(
    REDIS_URL, socket_connect_timeout=1.0, socket_timeout=1.0
)
_ws_cache: dict[str, Any] = {"value": 64, "expires_at": 0.0}


class MemoryFaultRequest(BaseModel):
    working_set_mb: int


def _get_memory_limit_bytes() -> int:
    raw = os.getenv("POD_MEMORY_LIMIT_BYTES", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return 192 * 1024 * 1024


def _get_working_set_mb(*, allow_network: bool = True) -> int:
    now = time.monotonic()
    if not allow_network or now < float(_ws_cache["expires_at"]):
        return int(_ws_cache["value"])
    try:
        val = _redis_client.get(BATCH_DEMAND_KEY)
        if val is not None:
            parsed = int(val)
            _ws_cache["value"] = parsed
            _ws_cache["expires_at"] = now + 1.5
            return parsed
    except Exception:
        pass
    _ws_cache["expires_at"] = now + 1.5
    return int(_ws_cache["value"])


def _refresh_memory_gauges(*, allow_network: bool = True) -> tuple[int, int, float]:
    limit_bytes = _get_memory_limit_bytes()
    ws_bytes = _get_working_set_mb(allow_network=allow_network) * 1024 * 1024
    MEMORY_LIMIT_BYTES.labels(service=SERVICE_NAME).set(limit_bytes)
    MEMORY_WORKING_SET_BYTES.labels(service=SERVICE_NAME).set(ws_bytes)
    ratio = ws_bytes / limit_bytes if limit_bytes > 0 else 1.0
    return ws_bytes, limit_bytes, ratio


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    _refresh_memory_gauges(allow_network=False)
    return {"status": "alive", "service": SERVICE_NAME, "version": RELEASE_VERSION}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    ws_bytes, limit_bytes, ratio = _refresh_memory_gauges()
    if ratio >= 0.88:
        return JSONResponse(
            status_code=503,
            content={
                "status": "memory_pressure",
                "error_code": "ERR_OOM_EXIT_137_CLAIMS_BATCH",
                "working_set_bytes": ws_bytes,
                "memory_limit_bytes": limit_bytes,
                "ratio": round(ratio, 3),
            },
        )
    db_ok = False
    try:
        with psycopg.connect(POSTGRES_DSN, connect_timeout=1.5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                db_ok = cur.fetchone() is not None
    except Exception:
        db_ok = False

    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={
            "status": "ready" if db_ok else "degraded",
            "working_set_bytes": ws_bytes,
            "memory_limit_bytes": limit_bytes,
            "ratio": round(ratio, 3),
            "postgres_ok": db_ok,
        },
    )


@app.post("/api/claims/adjudicate")
async def adjudicate_claim() -> JSONResponse:
    ws_bytes, limit_bytes, ratio = _refresh_memory_gauges()
    if ratio >= 0.88:
        return JSONResponse(
            status_code=503,
            content={
                "error_code": "ERR_OOM_EXIT_137_CLAIMS_BATCH",
                "working_set_bytes": ws_bytes,
                "memory_limit_bytes": limit_bytes,
            },
        )
    async with httpx.AsyncClient(timeout=2.0) as client:
        elig_resp = await client.get(f"{ELIGIBILITY_URL}/api/eligibility/check")
    if elig_resp.status_code >= 500:
        return JSONResponse(
            status_code=502,
            content={
                "error": "upstream_eligibility_failed",
                "upstream_status": elig_resp.status_code,
            },
        )
    return JSONResponse(
        status_code=200,
        content={"service": SERVICE_NAME, "adjudicated": True, "synthetic": True},
    )


@app.post("/internal/fault", dependencies=[Depends(verify_internal_fault_token)])
async def set_memory_demand(body: MemoryFaultRequest) -> dict[str, Any]:
    _redis_client.set(BATCH_DEMAND_KEY, str(body.working_set_mb))
    _ws_cache["value"] = body.working_set_mb
    _ws_cache["expires_at"] = time.monotonic() + 1.5
    ws_bytes, limit_bytes, ratio = _refresh_memory_gauges(allow_network=False)
    return {
        "service": SERVICE_NAME,
        "working_set_mb": body.working_set_mb,
        "working_set_bytes": ws_bytes,
        "memory_limit_bytes": limit_bytes,
        "ratio": round(ratio, 3),
    }
