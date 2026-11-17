---
slug: rb-009-claims-processor-crashloop
title: "RB-009: Claims Processor CrashLoopBackOff Without OOM Signal"
doc_type: RUNBOOK
service_slug: claims-processor
risk_tier: HIGH
permitted_playbook_id: deployment_image_rollback
applicability:
  services: ["claims-processor"]
  alertnames: ["PodCrashLoopBackOff"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
  require_known_good_image: true
evidence_requirements:
  - "container waiting reason CrashLoopBackOff with non-OOM exit code"
---

## Symptoms
`claims-processor` enters `CrashLoopBackOff` with non-137 exit code (`ERR_BOOT_CONFIG_CRASH_01`) after deployment change.

## Evidence Requirements
- `PodCrashLoopBackOff` alert with exit code != 137.

## Applicability & Preconditions
- Requires `approver` MFA approval for rollback to `known_good_image`; otherwise escalate.

## Expected Result
Rollback restores previous `known_good_image` release.

## Verification Steps
Confirm `claims-processor` pods transition to `Running` / `Ready` and remain healthy for 60s.

## Escalation Guidance
If `known_good_image` also crashes, check ConfigMap/Secret dependencies and escalate to `claims-sre`.
