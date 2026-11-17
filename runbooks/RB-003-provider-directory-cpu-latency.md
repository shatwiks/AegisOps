---
slug: rb-003-provider-directory-cpu-latency
title: "RB-003: Provider Directory Sustained CPU Saturation and Latency Spike"
doc_type: RUNBOOK
service_slug: provider-directory
risk_tier: LOW
permitted_playbook_id: replica_scale_out_bounded
applicability:
  services: ["provider-directory"]
  alertnames: ["ProviderDirectoryHighLatencyCpu", "HighRequestLatencyP95"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
  max_replicas: 4
evidence_requirements:
  - "p95 request latency > 0.8s or cpu_pressure_active == 1"
  - "current replicas < max_replicas (4)"
---

## Symptoms
`provider-directory` exhibits sustained high p95 response latency (`> 0.8s`), `ERR_CPU_SATURATION_P95_SLOW`, and elevated CPU saturation on single-replica deployments during clinic directory search load.

## Evidence Requirements
- Prometheus alert `ProviderDirectoryHighLatencyCpu` with sustained request volume.
- Single or under-provisioned replica count below ceiling `4`.

## Applicability & Preconditions
- Applicable when load exceeds single-pod concurrency capacity and target deployment replicas are below `max_replicas=4`.
- Bounded `replica_scale_out_bounded` sets deterministic target `replicas=3`.

## Expected Result
Kubernetes scales `provider-directory` to 3 ready pods, distributing concurrent search traffic and dropping p95 latency below `0.4s`.

## Verification Steps
1. Confirm `provider-directory` Deployment reaches `ready_replicas == 3`.
2. Verify `/readyz` returns HTTP 200 across pods.
3. Confirm Prometheus p95 latency stays `< 0.5s` for 60 continuous seconds.

## Escalation Guidance
If scaling to `3` replicas does not reduce latency (e.g., upstream `redis-session-cache` outage), escalate to `directory-sre`.
