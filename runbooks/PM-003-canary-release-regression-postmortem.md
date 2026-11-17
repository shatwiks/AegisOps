---
slug: pm-003-canary-release-regression-postmortem
title: "PM-003 (Synthetic Postmortem): Broken Canary Image Rollout Regression"
doc_type: POSTMORTEM
service_slug: eligibility-api
risk_tier: HIGH
permitted_playbook_id: deployment_image_rollback
applicability:
  services: ["eligibility-api", "claims-processor"]
  alertnames: ["High5xxErrorRate", "CanaryReleaseRegression"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
  require_known_good_image: true
evidence_requirements:
  - "ERR_CANARY_IMG_SHA_BAD_9921"
---

## Symptoms
Historical synthetic incident: faulty build `v1.9.0-broken` introduced unhandled exceptions on `/api/eligibility/check`, emitting `ERR_CANARY_IMG_SHA_BAD_9921` and 500 responses.

## Evidence Requirements
- `ERR_CANARY_IMG_SHA_BAD_9921` or elevated 5xx error ratio after image change.

## Applicability & Preconditions
- Rollback strictly targets server-registered `known_good_image` and requires MFA step-up approval (`deployment_image_rollback`).

## Expected Result
Image rolled back to `aegisops/eligibility-api:v1.0.0-good`.

## Verification Steps
Verify 0% 5xx rate and `/readyz` HTTP 200 across 60s window.

## Escalation Guidance
If rollback fails rollout deadline, escalate to `benefits-sre`.
