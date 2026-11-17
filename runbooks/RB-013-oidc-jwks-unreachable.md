---
slug: rb-013-oidc-jwks-unreachable
title: "RB-013: Identity Provider JWKS Endpoint Unreachable"
doc_type: RUNBOOK
service_slug: member-portal-gateway
risk_tier: HIGH
permitted_playbook_id: null
applicability:
  services: ["member-portal-gateway", "eligibility-api"]
  alertnames: ["OidcJwksFetchFailed"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
evidence_requirements:
  - "ERR_OIDC_JWKS_UNREACHABLE or HTTP 401 surge across valid sessions"
---

## Symptoms
Services reject valid OIDC JWT bearer tokens because Keycloak JWKS metadata cannot be fetched (`ERR_OIDC_JWKS_UNREACHABLE`).

## Evidence Requirements
- Elevated 401 failures correlated with JWKS refresh failures.

## Applicability & Preconditions
- Identity infrastructure mutations are excluded from autonomous playbooks; escalate immediately.

## Expected Result
Incident enters `ESCALATED` without mutating application pods.

## Verification Steps
Confirm `/protocol/openid-connect/certs` returns HTTP 200 and JWKS cache refreshes.

## Escalation Guidance
Escalate to identity/security platform team; never bypass JWT validation.
