"""Synthetic Provider Directory microservice demonstrating real scale-out latency relief."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import redis
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.base_service import (
    CPU_PRESSURE_ACTIVE,
    configure_telemetry,
    verify_internal_fault_token,
)

SERVICE_NAME = "provider-directory"
RELEASE_VERSION = os.getenv("AEGISOPS_RELEASE_VERSION", "v1.0.0-good")
REDIS_URL = os.getenv("DEMO_REDIS_URL", "redis://redis-session-cache:6379/0")
PRESSURE_KEY = "aegisops:demo:provider_cpu_pressure"

app = FastAPI(title="AegisOps Synthetic Provider Directory", version=RELEASE_VERSION)
configure_telemetry(app, SERVICE_NAME, RELEASE_VERSION, broken=False)

_redis_client = redis.Redis.from_url(
    REDIS_URL, socket_connect_timeout=1.0, socket_timeout=1.0
)
_pressure_cache: dict[str, Any] = {"value": False, "expires_at": 0.0}

# Per-pod concurrency slots: 2 slots queue 6 callers up to ~0.66s on 1 pod,
# whereas 3 replicas provide 6 slots (<0.44s even under burst collision).
_pod_semaphore = asyncio.Semaphore(2)


class CpuFaultToggle(BaseModel):
    cpu_pressure_active: bool


def _is_pressure_enabled() -> bool:
    now = time.monotonic()
    if now < float(_pressure_cache["expires_at"]):
        return bool(_pressure_cache["value"])
    try:
        val = _redis_client.get(PRESSURE_KEY) == b"1"
        _pressure_cache["value"] = val
        _pressure_cache["expires_at"] = now + 1.5
        return val
    except Exception:
        _pressure_cache["expires_at"] = now + 1.5
        return bool(_pressure_cache["value"])


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "alive", "service": SERVICE_NAME, "version": RELEASE_VERSION}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    redis_ok = False
    try:
        redis_ok = bool(_redis_client.ping())
    except Exception:
        redis_ok = False
    CPU_PRESSURE_ACTIVE.labels(service=SERVICE_NAME).set(
        1.0 if _is_pressure_enabled() else 0.0
    )
    return JSONResponse(
        status_code=200 if redis_ok else 503,
        content={"status": "ready" if redis_ok else "degraded", "redis_ok": redis_ok},
    )


@app.get("/api/providers/search")
async def search_providers(specialty: str = "primary-care") -> dict[str, Any]:
    pressure = _is_pressure_enabled()
    CPU_PRESSURE_ACTIVE.labels(service=SERVICE_NAME).set(1.0 if pressure else 0.0)
    start = time.perf_counter()
    if pressure:
        # Per-pod concurrency slots: 1 pod (2 slots) @ 6 callers queues to ~0.66s,
        # while 3 replicas (6 slots) keep p95 <= 0.44s cleanly.
        async with _pod_semaphore:
            await asyncio.sleep(0.22)
    else:
        await asyncio.sleep(0.01)

    return {
        "service": SERVICE_NAME,
        "specialty": specialty,
        "providers": [
            {"id": "SYN-PRV-001", "name": "Synthetic Clinic Alpha", "in_network": True}
        ],
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 1),
    }


@app.post("/internal/fault", dependencies=[Depends(verify_internal_fault_token)])
async def toggle_cpu_pressure(body: CpuFaultToggle) -> dict[str, Any]:
    _redis_client.set(PRESSURE_KEY, "1" if body.cpu_pressure_active else "0")
    _pressure_cache["value"] = body.cpu_pressure_active
    _pressure_cache["expires_at"] = time.monotonic() + 1.5
    CPU_PRESSURE_ACTIVE.labels(service=SERVICE_NAME).set(
        1.0 if body.cpu_pressure_active else 0.0
    )
    return {"service": SERVICE_NAME, "cpu_pressure_active": body.cpu_pressure_active}
