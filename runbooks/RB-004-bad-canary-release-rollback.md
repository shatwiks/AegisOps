---
slug: rb-004-bad-canary-release-rollback
title: "RB-004: Unhealthy Application Release 5xx Spike — Known-Good Image Rollback"
doc_type: RUNBOOK
service_slug: eligibility-api
risk_tier: HIGH
permitted_playbook_id: deployment_image_rollback
applicability:
  services: ["eligibility-api", "claims-processor", "provider-directory"]
  alertnames: ["High5xxErrorRate", "CanaryReleaseRegression"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
  require_known_good_image: true
evidence_requirements:
  - "5xx error ratio >= 0.10 with active traffic"
  - "ERR_CANARY_IMG_SHA_BAD_9921 or broken release_build_status == 0"
---

## Symptoms
Following a deployment update (such as `v1.9.0-broken`), HTTP 5xx error ratio surges above 10%, readiness probes degrade, and logs emit `ERR_CANARY_IMG_SHA_BAD_9921`.

## Evidence Requirements
- Prometheus alert `High5xxErrorRate` on an asset with a server-registered `known_good_image` in CMDB.
- Verified traffic coverage (`rate(http_requests_total[1m]) > 0.5`).

## Applicability & Preconditions
- Image rollback is **HIGH RISK** and MUST require authenticated `approver` + action-bound TOTP MFA approval.
- Target image is resolved strictly from `assets.known_good_image` in server state (never from LLM output).

## Expected Result
Kubernetes patches the Deployment container image back to the allowlisted known-good image (e.g., `aegisops/eligibility-api:v1.0.0-good`) and rolls out healthy pods.

## Verification Steps
1. Confirm Deployment image matches `assets.known_good_image` and rollout completes.
2. Verify `/readyz` and functional probe succeed.
3. Confirm 5xx error ratio stays `< 1%` across a 60-second sustained recovery window.

## Escalation Guidance
If rollback fails rollout readiness or 5xx errors continue on known-good image, escalate immediately as P1 to service owner.
