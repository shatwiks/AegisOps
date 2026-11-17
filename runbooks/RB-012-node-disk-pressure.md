---
slug: rb-012-node-disk-pressure
title: "RB-012: Kubernetes Node DiskPressure Eviction Warning"
doc_type: RUNBOOK
service_slug: claims-processor
risk_tier: HIGH
permitted_playbook_id: null
applicability:
  services: ["claims-processor", "eligibility-api", "provider-directory"]
  alertnames: ["KubeNodeDiskPressure"]
  namespaces: ["aegisops-healthcare"]
preconditions:
  require_known_asset: true
evidence_requirements:
  - "node_filesystem_avail_bytes / node_filesystem_size_bytes < 0.15"
---

## Symptoms
Cluster node emits `DiskPressure` taint or image GC eviction warnings (`ERR_NODE_DISK_FULL`).

## Evidence Requirements
- Node disk utilization > 85%.

## Applicability & Preconditions
- Host node filesystem cleanup cannot be remediated safely via pod scaling or restarts; escalate to infrastructure team.

## Expected Result
Incident escalates with affected node and scheduled workload list.

## Verification Steps
Confirm `DiskPressure` condition clears on node object.

## Escalation Guidance
Escalate to cluster infrastructure operator for container image pruning or volume expansion.
