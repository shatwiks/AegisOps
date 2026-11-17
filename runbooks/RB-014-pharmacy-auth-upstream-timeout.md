---
slug: rb-014-pharmacy-auth-upstream-timeout
title: "RB-014: Pharmacy Prior Auth Upstream Eligibility Dependency Timeout"
doc_type: RUNBOOK
service_slug: pharmacy-prior-auth
risk_tier: LOW
permitted_playbook_id: null
applicability:
  services: ["pharmacy-prior-auth"]
  alertnames: ["PharmacyPriorAuthLatencyHigh"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
evidence_requirements:
  - "ERR_UPSTREAM_ELIGIBILITY_TIMEOUT"
---

## Symptoms
`pharmacy-prior-auth` experiences elevated upstream timeouts calling `eligibility-api` (`ERR_UPSTREAM_ELIGIBILITY_TIMEOUT`).

## Evidence Requirements
- Check CMDB upstream dependency (`eligibility-api`) before mutating `pharmacy-prior-auth`.

## Applicability & Preconditions
- When upstream `eligibility-api` is degraded, restarting `pharmacy-prior-auth` will not cure the root cause; escalate or wait for upstream incident resolution.

## Expected Result
Escalate with linked upstream `eligibility-api` CMDB trace.

## Verification Steps
Confirm `eligibility-api` latency normalizes and upstream timeout count drops to zero.

## Escalation Guidance
Cross-correlate active `eligibility-api` incidents; page `pharmacy-sre` if `eligibility-api` is already healthy.
