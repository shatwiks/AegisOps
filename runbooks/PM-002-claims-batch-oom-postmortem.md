---
slug: pm-002-claims-batch-oom-postmortem
title: "PM-002 (Synthetic Postmortem): Claims Processor Batch Allocation OOM (Exit 137)"
doc_type: POSTMORTEM
service_slug: claims-processor
risk_tier: HIGH
permitted_playbook_id: memory_limit_increase_bounded
applicability:
  services: ["claims-processor"]
  alertnames: ["ClaimsProcessorMemoryPressure", "PodOOMKilled"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
  max_memory_limit_mi: 512
evidence_requirements:
  - "ERR_OOM_EXIT_137_CLAIMS_BATCH"
---

## Symptoms
Historical synthetic incident: `claims-processor` batch adjudication spiked above `192Mi` container ceiling, logging `ERR_OOM_EXIT_137_CLAIMS_BATCH` before kernel OOM killer terminated pods.

## Evidence Requirements
- Presence of `ERR_OOM_EXIT_137_CLAIMS_BATCH` or memory utilization >= 85%.

## Applicability & Preconditions
- Bounded memory increase to `384Mi` requires MFA-authenticated `approver` sign-off (`memory_limit_increase_bounded`).

## Expected Result
Container memory limit raised within `512Mi` policy cap after SRE approval.

## Verification Steps
Monitor `simulated_memory_allocated_bytes` vs container limit for 60s post-rollout.

## Escalation Guidance
Escalate to `claims-sre` if heap growth continues past `384Mi`.
