"""Synthetic Eligibility API microservice with real Postgres/Redis dependencies and fault modes."""

from __future__ import annotations

import os
import time
from typing import Any

import psycopg
import redis
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared.base_service import (
    DB_POOL_ACTIVE,
    DB_POOL_MAX,
    configure_telemetry,
    verify_internal_fault_token,
)

SERVICE_NAME = "eligibility-api"
RELEASE_VERSION = os.getenv("AEGISOPS_RELEASE_VERSION", "v1.0.0-good")
IS_BROKEN_CANARY = os.getenv("AEGISOPS_BROKEN_CANARY", "false").lower() == "true"
POSTGRES_DSN = os.getenv(
    "DEMO_POSTGRES_DSN",
    "postgresql://demo:demopass@postgres-claims-db:5432/claims_demo",
)
REDIS_URL = os.getenv("DEMO_REDIS_URL", "redis://redis-session-cache:6379/0")

# Process-local fault state: cleared only by pod rolling restart or explicit reset
_fault_state: dict[str, bool] = {"db_pool_exhausted": False}
MAX_POOL = 20

app = FastAPI(title="AegisOps Synthetic Eligibility API", version=RELEASE_VERSION)
configure_telemetry(app, SERVICE_NAME, RELEASE_VERSION, IS_BROKEN_CANARY)
DB_POOL_MAX.labels(service=SERVICE_NAME).set(MAX_POOL)
DB_POOL_ACTIVE.labels(service=SERVICE_NAME).set(2)

_redis_client = redis.Redis.from_url(
    REDIS_URL, socket_connect_timeout=1.5, socket_timeout=1.5
)
_dep_cache: dict[str, Any] = {
    "redis_ok": True,
    "postgres_ok": True,
    "expires_at": 0.0,
}


class FaultToggle(BaseModel):
    db_pool_exhausted: bool


def _check_dependencies() -> tuple[bool, dict[str, Any]]:
    details: dict[str, Any] = {
        "release": RELEASE_VERSION,
        "broken_canary": IS_BROKEN_CANARY,
    }
    now = time.monotonic()
    if now < float(_dep_cache["expires_at"]):
        details["redis_ok"] = bool(_dep_cache["redis_ok"])
        details["postgres_ok"] = bool(_dep_cache["postgres_ok"])
    else:
        try:
            details["redis_ok"] = bool(_redis_client.ping())
        except Exception as exc:
            details["redis_ok"] = False
            details["redis_err"] = type(exc).__name__

        try:
            with psycopg.connect(POSTGRES_DSN, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    details["postgres_ok"] = cur.fetchone() is not None
        except Exception as exc:
            details["postgres_ok"] = False
            details["postgres_err"] = type(exc).__name__

        _dep_cache["redis_ok"] = bool(details.get("redis_ok"))
        _dep_cache["postgres_ok"] = bool(details.get("postgres_ok"))
        _dep_cache["expires_at"] = now + 2.0

    ok = (
        bool(details.get("redis_ok"))
        and bool(details.get("postgres_ok"))
        and not IS_BROKEN_CANARY
        and not _fault_state["db_pool_exhausted"]
    )
    return ok, details


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness remains 200 so K8s does not auto-mask application pool leaks without AIOps."""
    return {"status": "alive", "service": SERVICE_NAME, "version": RELEASE_VERSION}


@app.get("/readyz")
async def readyz() -> JSONResponse:
    ok, details = _check_dependencies()
    if IS_BROKEN_CANARY:
        return JSONResponse(
            status_code=500,
            content={
                "status": "unhealthy",
                "error_code": "ERR_CANARY_IMG_SHA_BAD_9921",
                **details,
            },
        )
    if _fault_state["db_pool_exhausted"]:
        DB_POOL_ACTIVE.labels(service=SERVICE_NAME).set(MAX_POOL)
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "error_code": "ERR_PG_POOL_TIMEOUT_57P03",
                **details,
            },
        )
    DB_POOL_ACTIVE.labels(service=SERVICE_NAME).set(3)
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ready" if ok else "degraded", **details},
    )


@app.get("/api/eligibility/check")
async def check_eligibility(plan_code: str = "SYNTH-HMO-01") -> JSONResponse:
    if IS_BROKEN_CANARY:
        return JSONResponse(
            status_code=500,
            content={
                "error_code": "ERR_CANARY_IMG_SHA_BAD_9921",
                "message": "Synthetic broken canary release failure",
            },
        )
    if _fault_state["db_pool_exhausted"]:
        DB_POOL_ACTIVE.labels(service=SERVICE_NAME).set(MAX_POOL)
        return JSONResponse(
            status_code=503,
            content={
                "error_code": "ERR_PG_POOL_TIMEOUT_57P03",
                "message": "Database connection pool saturated (20/20)",
            },
        )
    ok, details = _check_dependencies()
    if not ok:
        return JSONResponse(status_code=503, content={"status": "degraded", **details})
    DB_POOL_ACTIVE.labels(service=SERVICE_NAME).set(4)
    return JSONResponse(
        status_code=200,
        content={
            "service": SERVICE_NAME,
            "plan_code": plan_code,
            "eligible": True,
            "synthetic": True,
            "version": RELEASE_VERSION,
        },
    )


@app.post("/internal/fault", dependencies=[Depends(verify_internal_fault_token)])
async def set_fault(body: FaultToggle) -> dict[str, Any]:
    _fault_state["db_pool_exhausted"] = body.db_pool_exhausted
    DB_POOL_ACTIVE.labels(service=SERVICE_NAME).set(
        MAX_POOL if body.db_pool_exhausted else 2
    )
    return {
        "service": SERVICE_NAME,
        "db_pool_exhausted": _fault_state["db_pool_exhausted"],
    }
