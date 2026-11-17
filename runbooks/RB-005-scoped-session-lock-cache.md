---
slug: rb-005-scoped-session-lock-cache
title: "RB-005: Stale Redis Session Lock Key Eviction (Scoped Prefix Only)"
doc_type: RUNBOOK
service_slug: redis-session-cache
risk_tier: LOW
permitted_playbook_id: scoped_cache_key_eviction
applicability:
  services: ["redis-session-cache", "eligibility-api"]
  alertnames: ["StaleSessionLockContention"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
  allowlisted_prefix: "session:lock:stale:*"
evidence_requirements:
  - "ERR_REDIS_STALE_LOCK_429 or lock contention spike on session:lock:stale:*"
---

## Symptoms
`eligibility-api` experiences elevated lock timeouts caused by orphaned `session:lock:stale:*` keys in `redis-session-cache` (`ERR_REDIS_STALE_LOCK_429`).

## Evidence Requirements
- Confirmed `StaleSessionLockContention` alert naming `redis-session-cache` or `eligibility-api`.
- Only keys matching `session:lock:stale:*` may be evicted. Broad `FLUSHALL` / `FLUSHDB` is strictly forbidden.

## Applicability & Preconditions
- Scoped prefix deletion (`session:lock:stale:*`) only. Never delete active auth or claims keys.

## Expected Result
Only orphaned `session:lock:stale:*` keys are removed via `SCAN` + `UNLINK`, unblocking session acquisitions without evicting valid cache entries.

## Verification Steps
1. Verify lock-timeout rate returns to zero.
2. Confirm `eligibility-api` `/readyz` remains healthy for 60 seconds.

## Escalation Guidance
Escalate to `platform-cache` if Redis memory fragmentation or AOF persistence errors are observed.
