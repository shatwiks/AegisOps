---
slug: rb-007-edi-837-queue-backlog
title: "RB-007: EDI 837 Ingestion Queue Backlog Growth"
doc_type: RUNBOOK
service_slug: edi-837-ingest
risk_tier: HIGH
permitted_playbook_id: null
applicability:
  services: ["edi-837-ingest"]
  alertnames: ["EdiQueueLagHigh"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
evidence_requirements:
  - "edi_queue_depth > 5000"
---

## Symptoms
Synthetic EDI 837 claim batch ingestion queue depth exceeds 5,000 messages (`ERR_EDI_BATCH_LAG`).

## Evidence Requirements
- Queue backlog metric and downstream `claims-processor` health check.

## Applicability & Preconditions
- `edi-837-ingest` is marked `stateless_eligible=false` (stateful file cursor); autonomous restart is unsafe.

## Expected Result
Escalate cleanly to `claims-sre` with CMDB upstream/downstream dependency context.

## Verification Steps
Verify queue lag drains cleanly without duplicate claim ingestion.

## Escalation Guidance
Escalate to `claims-sre`; check if downstream `claims-processor` is healthy before adjusting batch concurrency.
