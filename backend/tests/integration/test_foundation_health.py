"""Integration tests for FastAPI health/readiness against real PostgreSQL and Redis."""

from __future__ import annotations

import httpx
import pytest

from app.config import get_settings
from app.main import create_app


@pytest.mark.asyncio
async def test_healthz_and_readyz_against_real_postgres_and_redis() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    app = create_app(settings_override=settings)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            health_resp = await client.get("/healthz")
            assert health_resp.status_code == 200
            assert health_resp.json()["status"] == "ok"
            assert "X-Correlation-ID" in health_resp.headers

            ready_resp = await client.get("/readyz")
            assert ready_resp.status_code == 200, ready_resp.text
            body = ready_resp.json()
            assert body["status"] == "ready"
            assert body["checks"]["postgres"]["connected"] is True
            assert body["checks"]["postgres"]["pgvector_installed"] is True
            assert body["checks"]["redis"]["connected"] is True
