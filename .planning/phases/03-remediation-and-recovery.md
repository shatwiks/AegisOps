# Phase 3 — Durable Remediation and Verified Recovery

## 1. Objective, Scope, Dependencies, and Requirement IDs
- **Objective**: Build the 3 synthetic healthcare microservices (`eligibility-api`, `claims-processor`, `provider-directory`), Terraform local target (`infra/terraform/`), K8s workload manifests (`infra/k8s/workloads/`), Prometheus/Alertmanager/OTel pipelines, versioned server playbook registry, single-instance Redis lease manager, Kubernetes Python SDK executor with crash/timeout reconciliation, and sustained recovery watchdog (`VERIFYING -> RESOLVED`).
- **Dependencies**: Phase 2 `VERIFIED`, `kind-aegisops-local` cluster, Docker Compose observability services.
- **Requirement IDs**: `REQ-REM-01..09`, `REQ-OBS-01..02`, `REQ-OPS-02`.

## 2. Entry Criteria and Findings
- Phase 2 triage, refusal gate, and outbox job creation verified.

## 3. Implementation Tasks
- [x] Build `services/{eligibility-api,claims-processor,provider-directory}/` with `/healthz`, `/readyz`, `/metrics`, OTel export, Redis/Postgres calls, and fault injection modes.
- [x] Write `infra/terraform/{main.tf,variables.tf,outputs.tf}` for `aegisops-healthcare` namespace, `aegisops-remediator` ServiceAccount, least-privilege Role/RoleBinding, LimitRange, ResourceQuota.
- [x] Write `infra/k8s/workloads/*.yaml` (services, `postgres-claims-db`, `redis-session-cache`, `kube-state-metrics`).
- [x] Configure `infra/compose/{prometheus,alertmanager,otel}/` configs with traffic-guarded alert rules and authenticated Alertmanager webhook.
- [x] Implement `backend/app/playbooks/registry.py`, `backend/app/worker/locks.py`, `backend/app/k8s/executor.py`, `backend/app/worker/watchdog.py`, and `backend/app/worker/runner.py`.
- [x] Write unit and real-`kind` integration tests (`test_locks_and_reconciler.py`, `test_k8s_remediation_kind.py`, `test_recovery_watchdog.py`).
- [x] Keep high-risk operations inaccessible on public HTTP routes until Phase 4 OIDC/TOTP integration; verify high-risk execution paths only in isolated internal/integration tests.

## 4. Interfaces, Schemas, Data Flow, and Phase Decisions
- Explicit context allowlist `kind-aegisops-local`; sync K8s SDK calls executed via `asyncio.to_thread` with strict timeouts.
- Single-instance Redis lock uses `SET key token NX PX ttl_ms` + Lua ownership-checked renewal/release (`DEC-004` / Redis docs caveat: Redis leases alone do not fence in-flight K8s requests; `ExecutionAttempt` ledger + `resourceVersion` reconciliation close the gap).
- Sustained recovery window defaults to `60s` (`AEGISOPS_RECOVERY_WINDOW_SECONDS=60`).

## 5. Acceptance Criteria (Observable Behavior)
1. `terraform apply` provisions RBAC and quotas on `kind-aegisops-local` with zero ownership conflicts.
2. Demo services run healthy inside `kind` and scrape cleanly in Prometheus (`59090`).
3. Allowed playbooks (`replica_scale_out_bounded`, `stateless_deployment_restart`, `scoped_cache_key_eviction`) mutate actual K8s deployments; disallowed namespaces/bounds/contexts fail cleanly.
4. Parallel worker contention yields `SKIPPED_LOCK_CONTENTION` without marking incident resolved; simulated worker crash during `MUTATING` reconciles actual K8s state without double-scaling.
5. Watchdog refuses to resolve an incident if rollout is ready while metrics remain degraded or stale, and resolves only after sustained healthy probes over the configured window.

## 6. Verification Commands, Working Directory, and Expected Outcomes
- Working directory: repo root
- Required services: `kind-aegisops-local`, Postgres, Redis, Prometheus, Alertmanager, OTel Collector
- Commands:
  - `terraform -chdir=infra/terraform apply -auto-approve` -> exit `0`
  - `kubectl --context kind-aegisops-local get pods -n aegisops-healthcare` -> all Running/Ready
  - `.venv\Scripts\pytest.exe backend/tests/integration/test_locks_and_reconciler.py backend/tests/integration/test_k8s_remediation_kind.py backend/tests/integration/test_recovery_watchdog.py -v` -> all pass

## 7. Actual Results
- **Status of Checks**: `PASS` (`2026-11-17T05:53:40+05:30`).
- **Measured Result**:
  - `kind-aegisops-local`: `claims-processor`, `eligibility-api`, `provider-directory`, `postgres-claims-db`, `redis-session-cache`, and `kube-state-metrics` pods `Running` & `1/1 Ready`.
  - `ruff check`: `All checks passed!`.
  - `mypy`: `Success: no issues found in 41 source files`.
  - `pytest` (Phases 0–3): `55 passed in 79.06s` (unit + DB/Redis/Ollama + Redis lease + live `kind-aegisops-local` SDK scale & crash reconciliation + sustained 60s watchdog integration tests).
- **Evidence Path**: `docs/evidence/phase-03-remediation-recovery.txt`.

## 8. Defects Found and Fixes Made
- Observed `test_k8s_remediation_kind.py` leaving its synthetic `KindScaleTest` incident in `REMEDIATING` state after test exit; added cleanup in `finally:` to mark synthetic test incidents `FAILED` (without touching append-only `audit_records`).

## 9. Documentation Updates and Exit Checklist
- [x] Update `docs/ARCHITECTURE.md` and `docs/RUNBOOK.md`.
- [x] Update `.planning/REQUIREMENTS.md` (`REQ-REM-*`, `REQ-OBS-01..02`, `REQ-OPS-02`) and `.planning/STATE.md`.
- [x] Save sanitized test output to `docs/evidence/phase-03-remediation-recovery.txt`.

## 10. Current Status and Next Action
- **Status**: `VERIFIED`
- **Next Action**: Proceed to Phase 4 (`Identity, Step-Up Approval & SRE Console`).
