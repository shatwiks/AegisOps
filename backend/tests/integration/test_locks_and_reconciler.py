"""Integration tests for Redis target leases, Lua ownership, SKIP LOCKED outbox, and crash recovery."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.config import get_settings
from app.db import build_engine, build_session_factory
from app.models.entities import Incident, IncidentEvent, OutboxJob
from app.redis_client import build_redis_client
from app.worker.locks import LeaseLostError, RedisTargetLease
from app.worker.runner import claim_next_outbox_job


@pytest.mark.asyncio
async def test_redis_lease_ownership_contention_and_loss() -> None:
    settings = get_settings()
    redis_client = build_redis_client(settings)
    key = f"test-cluster:ns:svc-{uuid.uuid4().hex[:8]}"

    w1 = RedisTargetLease(redis_client, key, ttl_ms=5_000, owner_prefix="w1")
    w2 = RedisTargetLease(redis_client, key, ttl_ms=5_000, owner_prefix="w2")
    try:
        assert await w1.acquire() is True
        # Contention: w2 must fail to acquire while w1 holds lease
        assert await w2.acquire() is False
        await w1.assert_owned()
        assert await w1.extend() is True

        # Simulate lease loss (e.g. w1 paused beyond TTL and key replaced by w2)
        await redis_client.set(w1.resource_key, w2.token, px=5_000)
        assert await w1.extend() is False
        with pytest.raises(LeaseLostError):
            await w1.assert_owned()

        # Ownership-checked release from w1 must NOT delete w2's lock
        assert await w1.release() is False
        assert await redis_client.get(w1.resource_key) == w2.token

        # Cleanup by real owner w2
        w2.acquired = True
        assert await w2.release() is True
    finally:
        await w1.release()
        await redis_client.aclose()


@pytest.mark.asyncio
async def test_outbox_skip_locked_and_expired_lease_recovery() -> None:
    settings = get_settings()
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    inc_id = uuid.uuid4()
    job_key = f"test-recover-{uuid.uuid4().hex[:8]}"

    try:
        async with factory() as session, session.begin():
            inc = Incident(
                id=inc_id,
                dedup_key=f"dedup-{inc_id}",
                alert_fingerprint="fp-outbox",
                alertname="OutboxCrashTest",
                title="OutboxCrashTest",
                summary_sanitized="Simulated crashed worker job",
                severity="P3",
                severity_explanation_json={},
                state="OPEN",
                source_provenance="automated_test",
            )
            session.add(inc)
            await session.flush()

            # Seed an expired CLAIMED job simulating a crashed previous worker
            session.add(
                OutboxJob(
                    incident_id=inc_id,
                    job_type="TRIAGE_INCIDENT",
                    dedup_job_key=job_key,
                    payload_sanitized_json={"test": True},
                    status="CLAIMED",
                    worker_id="dead-worker-1",
                    claimed_at=datetime.now(UTC) - timedelta(minutes=10),
                    lease_expires_at=datetime.now(UTC) - timedelta(minutes=5),
                    attempts=1,
                    available_at=datetime.now(UTC) - timedelta(minutes=10),
                )
            )

        # Two workers race to claim; SKIP LOCKED ensures at most one succeeds
        async def _try_claim(name: str) -> uuid.UUID | None:
            async with factory() as session, session.begin():
                job = await claim_next_outbox_job(session, worker_id=name, incident_id=inc_id)
                await asyncio.sleep(0.1)
                return job.id if job and job.dedup_job_key == job_key else None

        res_a, res_b = await asyncio.gather(_try_claim("worker-a"), _try_claim("worker-b"))
        claimed = [r for r in (res_a, res_b) if r is not None]
        assert len(claimed) == 1
    finally:
        async with factory() as session, session.begin():
            await session.execute(delete(OutboxJob).where(OutboxJob.incident_id == inc_id))
            await session.execute(delete(IncidentEvent).where(IncidentEvent.incident_id == inc_id))
            await session.execute(delete(Incident).where(Incident.id == inc_id))
        await engine.dispose()
