---
slug: rb-010-provider-directory-redis-timeout
title: "RB-010: Provider Directory Redis Cache Connection Timeout"
doc_type: RUNBOOK
service_slug: provider-directory
risk_tier: LOW
permitted_playbook_id: stateless_deployment_restart
applicability:
  services: ["provider-directory"]
  alertnames: ["ProviderDirectoryRedisTimeouts"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
  require_stateless_eligible: true
evidence_requirements:
  - "ERR_REDIS_CONN_RESET_PD in provider-directory while redis-session-cache is up"
---

## Symptoms
`provider-directory` reports `ERR_REDIS_CONN_RESET_PD` on stale pooled connections to `redis-session-cache` while Redis itself passes `PING`.

## Evidence Requirements
- Confirmed healthy `redis-session-cache` and isolated timeout errors in `provider-directory`.

## Applicability & Preconditions
- `provider-directory` is stateless (`stateless_eligible=true`), making controlled rolling restart safe.

## Expected Result
`stateless_deployment_restart` recycles `provider-directory` pods and re-establishes fresh Redis connections.

## Verification Steps
Verify Redis cache hit ratio normalizes and `/readyz` returns 200 for 60s.

## Escalation Guidance
If `redis-session-cache` itself is unreachable, escalate to `platform-cache` immediately instead of restarting clients.
