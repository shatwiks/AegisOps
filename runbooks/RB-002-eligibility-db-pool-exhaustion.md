---
slug: rb-002-eligibility-db-pool-exhaustion
title: "RB-002: Eligibility API Database Connection Pool Exhaustion"
doc_type: RUNBOOK
service_slug: eligibility-api
risk_tier: LOW
permitted_playbook_id: stateless_deployment_restart
applicability:
  services: ["eligibility-api"]
  alertnames: ["EligibilityDbPoolExhausted", "High5xxErrorRate"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
  require_stateless_eligible: true
evidence_requirements:
  - "db_pool_active_connections / db_pool_max_connections >= 0.90"
  - "ERR_PG_POOL_TIMEOUT_57P03 or HTTP 503 pool wait timeout"
---

## Symptoms
`eligibility-api` reports `ERR_PG_POOL_TIMEOUT_57P03`, active database pool utilization above 90%, and HTTP 503 responses while `postgres-claims-db` itself remains healthy.

## Evidence Requirements
- Prometheus alert `EligibilityDbPoolExhausted` with `db_pool_active_connections` saturation.
- Confirmed `stateless_eligible=true` on `eligibility-api` in CMDB.

## Applicability & Preconditions
- Safe only for stateless services (`eligibility-api`) whose in-flight connections are wedged by leaked client handles.
- Not applicable when `postgres-claims-db` itself is unreachable or out of disk.

## Expected Result
`stateless_deployment_restart` triggers a controlled rolling restart of `eligibility-api`, draining wedged connection holders and restoring normal pool capacity.

## Verification Steps
1. Confirm `eligibility-api` rolling update completes cleanly.
2. Verify `db_pool_active_connections / db_pool_max_connections < 0.60`.
3. Confirm HTTP 5xx ratio remains `< 2%` across a 60-second sustained window.

## Escalation Guidance
If pool exhaustion recurs within 5 minutes of restart, escalate to `benefits-sre` and `data-platform` for connection leak investigation.
