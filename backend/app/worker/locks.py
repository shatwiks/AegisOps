"""Single-instance Redis lease locking with unique ownership tokens and atomic Lua scripts.

NOTE ON DISTRIBUTED ASSUMPTIONS:
A single-instance Redis lease is NOT Redlock and does not fence in-flight HTTP requests
already dispatched to the Kubernetes API server. AegisOps pairs this lease with a durable
PostgreSQL ExecutionAttempt ledger, idempotency keys, and Kubernetes resourceVersion/state
reconciliation before retries.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid

from redis.asyncio import Redis

_LUA_EXTEND_IF_OWNED = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
else
    return 0
end
"""

_LUA_RELEASE_IF_OWNED = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


class LeaseLostError(RuntimeError):
    """Raised when a worker loses its Redis lock ownership mid-operation."""


class RedisTargetLease:
    """Per-attempt Redis lease with bounded renewal and ownership-checked release."""

    def __init__(
        self,
        redis_client: Redis,
        resource_key: str,
        *,
        ttl_ms: int = 30_000,
        owner_prefix: str = "worker",
    ) -> None:
        self.redis = redis_client
        self.resource_key = f"aegisops:lock:{resource_key}"
        self.ttl_ms = ttl_ms
        self.token = f"{owner_prefix}:{uuid.uuid4()}"
        self.acquired = False
        self.lease_lost = False
        self._renew_task: asyncio.Task[None] | None = None

    async def acquire(self) -> bool:
        """Atomically acquire lease via SET NX PX with unique ownership token."""
        ok = await self.redis.set(self.resource_key, self.token, nx=True, px=self.ttl_ms)
        self.acquired = bool(ok)
        if self.acquired:
            self.lease_lost = False
            self._start_renewal()
        return self.acquired

    def _start_renewal(self) -> None:
        interval_sec = max(self.ttl_ms / 3000.0, 0.5)

        async def _loop() -> None:
            while self.acquired and not self.lease_lost:
                await asyncio.sleep(interval_sec)
                if not self.acquired:
                    break
                ok = await self.extend()
                if not ok:
                    self.lease_lost = True
                    break

        self._renew_task = asyncio.create_task(_loop())

    async def extend(self) -> bool:
        """Renew TTL atomically only if this worker still owns the token."""
        res = await self.redis.eval(
            _LUA_EXTEND_IF_OWNED, 1, self.resource_key, self.token, str(self.ttl_ms)
        )  # type: ignore[misc]
        owned = int(res or 0) == 1
        if not owned:
            self.lease_lost = True
        return owned

    async def assert_owned(self) -> None:
        """Check live token ownership in Redis right before issuing an external mutation."""
        if self.lease_lost or not self.acquired:
            raise LeaseLostError(f"Lease already lost for {self.resource_key}")
        current = await self.redis.get(self.resource_key)
        if current != self.token:
            self.lease_lost = True
            raise LeaseLostError(
                f"Lease ownership lost for {self.resource_key} (current={current!r})"
            )

    async def release(self) -> bool:
        """Stop renewal loop and atomically delete lock only if still owned by this token."""
        self.acquired = False
        if self._renew_task is not None:
            self._renew_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._renew_task
            self._renew_task = None

        res = await self.redis.eval(_LUA_RELEASE_IF_OWNED, 1, self.resource_key, self.token)  # type: ignore[misc]
        return int(res or 0) == 1
