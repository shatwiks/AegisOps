---
slug: rb-006-tls-certificate-expiry
title: "RB-006: Gateway TLS Certificate Expiration Warning"
doc_type: RUNBOOK
service_slug: member-portal-gateway
risk_tier: HIGH
permitted_playbook_id: null
applicability:
  services: ["member-portal-gateway"]
  alertnames: ["TlsCertificateExpiringSoon"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
evidence_requirements:
  - "cert_days_remaining < 7"
---

## Symptoms
TLS certificate on `member-portal-gateway` approaches expiry (`ERR_TLS_CERT_EXPIRY`).

## Evidence Requirements
- Certificate exporter metric showing `< 7` days remaining.

## Applicability & Preconditions
- Automated certificate rotation is outside the allowlisted Kubernetes remediation playbooks; always escalate.

## Expected Result
Incident enters `ESCALATED` with explicit PKI rotation instructions for `platform-edge`.

## Verification Steps
Verify new certificate chain serial and expiry timestamp post-manual rotation.

## Escalation Guidance
Page `platform-edge` on-call immediately; do not attempt pod restarts as a workaround.
