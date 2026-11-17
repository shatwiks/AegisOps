---
slug: rb-008-coredns-resolution-errors
title: "RB-008: Cluster CoreDNS Lookup Latency and NXDOMAIN Spike"
doc_type: RUNBOOK
service_slug: member-portal-gateway
risk_tier: HIGH
permitted_playbook_id: null
applicability:
  services: ["member-portal-gateway", "eligibility-api", "claims-processor"]
  alertnames: ["CoreDnsResolutionFailures"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
evidence_requirements:
  - "ERR_DNS_SERVFAIL_CORE"
---

## Symptoms
Cross-service HTTP requests fail with DNS lookup timeouts or `SERVFAIL` (`ERR_DNS_SERVFAIL_CORE`).

## Evidence Requirements
- Multiple services experiencing synchronous DNS failures concurrently.

## Applicability & Preconditions
- Cluster-wide `kube-system` CoreDNS mutations are outside `aegisops-healthcare` namespace RBAC; escalate.

## Expected Result
Safe refusal and escalation to cluster platform team.

## Verification Steps
Confirm internal Kubernetes service DNS (`eligibility-api.aegisops-healthcare.svc.cluster.local`) resolves in `< 10ms`.

## Escalation Guidance
Escalate to cluster platform administrators immediately.
