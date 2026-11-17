---
slug: rb-011-postgres-replication-lag
title: "RB-011: Postgres Claims DB Replication Lag and Failover Boundary (Escalate Only)"
doc_type: RUNBOOK
service_slug: postgres-claims-db
risk_tier: HIGH
permitted_playbook_id: null
applicability:
  services: ["postgres-claims-db"]
  alertnames: ["PostgresReplicationLagHigh", "PostgresPrimaryDown"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
evidence_requirements:
  - "ERR_PG_REPLICATION_LAG or stateful database unavailability"
---

## Symptoms
`postgres-claims-db` exhibits primary/replica lag, WAL bloat, or connection refusal (`ERR_PG_REPLICATION_LAG`).

## Evidence Requirements
- Alert targeting stateful asset `postgres-claims-db` (`stateless_eligible=false`).

## Applicability & Preconditions
- **EXPLICIT ARCHITECTURAL BOUNDARY**: AegisOps runs a single-instance demo `postgres-claims-db` without automated multi-node replication failover, split-brain fencing, or WAL consistency verification. Automated database failover is **NOT supported** and MUST ALWAYS refuse autonomous remediation.

## Expected Result
Incident immediately transitions to `ESCALATED` with full CMDB P1 blast-radius list (`eligibility-api`, `claims-processor`, `member-portal-gateway`, `pharmacy-prior-auth`, `edi-837-ingest`).

## Verification Steps
Human DBA validates database integrity (`pg_stat_replication`, disk space, checkpoint state) before manually closing the incident.

## Escalation Guidance
Page `data-platform` primary DBA immediately; never run `stateless_deployment_restart` on stateful database assets.
