---
slug: rb-001-claims-processor-oom
title: "RB-001: Claims Processor OOMKilled and Sustained Memory Pressure"
doc_type: RUNBOOK
service_slug: claims-processor
risk_tier: HIGH
permitted_playbook_id: memory_limit_increase_bounded
applicability:
  services: ["claims-processor"]
  alertnames: ["ClaimsProcessorMemoryPressure", "PodOOMKilled", "ContainerOOMKilled"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
  max_memory_limit_mi: 512
evidence_requirements:
  - "memory_ratio >= 0.85 or OOMKilled exit code 137"
  - "target deployment is claims-processor in aegisops-healthcare"
---

## Symptoms
`claims-processor` exhibits sustained heap/working-set growth above 85% of container memory limit, `ERR_OOM_EXIT_137_CLAIMS_BATCH`, or repeated container exit code 137 (`OOMKilled`) during synthetic batch adjudication.

## Evidence Requirements
- Prometheus alert `ClaimsProcessorMemoryPressure` or kube-state-metrics `OOMKilled` signal.
- Confirmed target `claims-processor` in `aegisops-healthcare`.

## Applicability & Preconditions
- Applicable strictly to `claims-processor` within bounded container ceiling `512Mi` (`memory_limit_increase_bounded`, target `384Mi`).
- Memory limit changes are classified **HIGH RISK** and require authenticated SRE `approver` TOTP step-up approval before Kubernetes mutation.

## Expected Result
Deployment container memory limit increases to `384Mi` (with aligned memory request) and memory-pressure fault mode settles below 70% utilization.

## Verification Steps
1. Verify Kubernetes rollout finishes with `updated_replicas == replicas == available_replicas`.
2. Probe `/readyz` on `claims-processor` (`HTTP 200`).
3. Confirm Prometheus memory utilization remains below threshold over a 60-second sustained recovery window.

## Escalation Guidance
If memory usage continues climbing past `512Mi` (unbounded memory leak), refuse further limit increases and escalate to the Claims SRE team for heap profiling.
