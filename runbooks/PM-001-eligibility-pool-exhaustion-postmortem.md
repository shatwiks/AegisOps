---
slug: pm-001-eligibility-pool-exhaustion-postmortem
title: "PM-001 (Synthetic Postmortem): Eligibility API Connection Pool Saturation"
doc_type: POSTMORTEM
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
  - "ERR_PG_POOL_TIMEOUT_57P03"
---

## Symptoms
Historical synthetic incident on `eligibility-api`: threads held idle database sessions indefinitely causing `ERR_PG_POOL_TIMEOUT_57P03` and cascading 503 failures across `member-portal-gateway` and `claims-processor`.

## Evidence Requirements
- Exact error token `ERR_PG_POOL_TIMEOUT_57P03` in sanitized summary or high `db_pool_active_connections` ratio.

## Applicability & Preconditions
- Validated stateless rolling restart via `stateless_deployment_restart` resolved connection exhaustion in past incidents.

## Expected Result
Stateless rolling restart drains leaked pool holders cleanly.

## Verification Steps
Confirm pool ratio < 60% and 5xx ratio < 1% for 60s.

## Escalation Guidance
Follow `RB-002` escalation path if pool saturates again immediately after restart.
