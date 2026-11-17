---
slug: rb-015-schema-migration-lock-contention
title: "RB-015: Claims Database DDL Lock Contention Blocking Workers"
doc_type: RUNBOOK
service_slug: claims-processor
risk_tier: HIGH
permitted_playbook_id: null
applicability:
  services: ["claims-processor", "postgres-claims-db"]
  alertnames: ["DatabaseLockContentionHigh"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
evidence_requirements:
  - "ERR_PG_LOCK_WAIT_55P03 or blocked_queries > 5"
---

## Symptoms
`claims-processor` queries stall behind `AccessExclusiveLock` in `postgres-claims-db` (`ERR_PG_LOCK_WAIT_55P03`).

## Evidence Requirements
- PostgreSQL lock wait metrics or `55P03` SQLSTATE logs.

## Applicability & Preconditions
- Scaling or restarting `claims-processor` amplifies lock storms; always refuse automation and escalate.

## Expected Result
Safe refusal -> `ESCALATED`.

## Verification Steps
Confirm `pg_locks` contention clears and transaction latency returns below 100ms.

## Escalation Guidance
Escalate to `data-platform` and `claims-sre` to inspect blocking migration PID.
