"""Async Redis client factory and readiness probe."""

from __future__ import annotations

from redis.asyncio import Redis

from app.config import Settings


def build_redis_client(settings: Settings) -> Redis:
    """Create an async Redis client."""
    return Redis.from_url(
        settings.aegisops_redis_url,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=3.0,
        socket_timeout=3.0,
    )


async def check_redis_ready(redis_client: Redis) -> dict[str, bool]:
    """Verify Redis connectivity via PING."""
    pong = await redis_client.ping()
    return {"connected": bool(pong)}
