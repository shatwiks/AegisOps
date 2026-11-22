"""FastAPI application entrypoint with lifespan lifecycle and health probes."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.api.approvals import router as approvals_router
from app.api.auth import router as auth_router
from app.api.incidents import router as incidents_router
from app.api.metrics import router as metrics_router
from app.api.runbooks import router as runbooks_router
from app.api.showcase import router as showcase_router
from app.api.stream import router as stream_router
from app.api.topology import router as topology_router
from app.api.webhooks import router as webhooks_router
from app.auth.oidc import OIDCVerifier
from app.config import Settings, get_settings
from app.db import build_engine, build_session_factory, check_postgres_ready
from app.redis_client import build_redis_client, check_redis_ready

logger = logging.getLogger("aegisops.api")
API_REQUESTS_TOTAL = Counter(
    "aegisops_control_plane_requests_total",
    "Total HTTP requests served by AegisOps control plane",
    ["method", "status"],
)


def create_app(settings_override: Settings | None = None) -> FastAPI:
    """Create and configure the AegisOps FastAPI application."""
    settings = settings_override or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        engine = build_engine(settings)
        session_factory = build_session_factory(engine)
        redis_client = build_redis_client(settings)

        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.redis = redis_client
        app.state.oidc_verifier = OIDCVerifier(settings)

        logger.info(
            "AegisOps API starting (env=%s, context=%s)",
            settings.aegisops_env,
            settings.aegisops_k8s_context,
        )
        try:
            yield
        finally:
            await redis_client.aclose()
            await engine.dispose()
            logger.info("AegisOps API shut down cleanly")

    app = FastAPI(
        title="AegisOps Control Plane",
        version=__version__,
        description="Autonomous AIOps, CMDB Blast-Radius & Self-Healing Kubernetes Control Plane",
        lifespan=lifespan,
    )
    app.include_router(webhooks_router)
    app.include_router(auth_router)
    app.include_router(approvals_router)
    app.include_router(incidents_router)
    app.include_router(topology_router)
    app.include_router(metrics_router)
    app.include_router(stream_router)
    app.include_router(runbooks_router)
    app.include_router(showcase_router)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.aegisops_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Correlation-ID"],
    )

    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next: Any) -> Any:
        raw_cid = request.headers.get("X-Correlation-ID", "").strip()
        if raw_cid and len(raw_cid) <= 128 and all(c.isalnum() or c in "-_." for c in raw_cid):
            correlation_id = raw_cid
        else:
            correlation_id = str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path != "/metrics":
            API_REQUESTS_TOTAL.labels(method=request.method, status=str(response.status_code)).inc()
        return response

    @app.exception_handler(Exception)
    async def sanitized_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = getattr(request.state, "correlation_id", "unknown")
        logger.error(
            "Unhandled API error (correlation_id=%s, type=%s)",
            correlation_id,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "correlation_id": correlation_id,
            },
        )

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        """Process liveness check."""
        return {"status": "ok", "version": __version__}

    @app.get("/metrics", tags=["observability"])
    async def prometheus_metrics() -> Response:
        """Expose control-plane Prometheus metrics."""
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/readyz", tags=["health"])
    async def readyz(request: Request) -> JSONResponse:
        """Deep readiness check verifying PostgreSQL, pgvector, and Redis."""
        checks: dict[str, Any] = {}
        overall_ready = True

        try:
            pg_status = await check_postgres_ready(request.app.state.engine)
            checks["postgres"] = pg_status
            if not pg_status.get("pgvector_installed"):
                overall_ready = False
        except Exception as exc:
            checks["postgres"] = {"connected": False, "error": type(exc).__name__}
            overall_ready = False

        try:
            redis_status = await check_redis_ready(request.app.state.redis)
            checks["redis"] = redis_status
        except Exception as exc:
            checks["redis"] = {"connected": False, "error": type(exc).__name__}
            overall_ready = False

        status_code = 200 if overall_ready else 503
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "ready" if overall_ready else "degraded",
                "checks": checks,
            },
        )

    return app


async def get_request_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an AsyncSession from app.state.session_factory."""
    async with request.app.state.session_factory() as session:
        yield session


def get_app() -> FastAPI:
    """Lazy ASGI app factory for uvicorn --factory app.main:get_app."""
    return create_app()
