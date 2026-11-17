# AegisOps — Overall Implementation & Verification Flow

## 1. Current Status Summary

> **Honest Build State:** All Phases `0–5` are `VERIFIED` locally (complete control plane, Keycloak PKCE + TOTP, live `kind-aegisops-local` cluster, 4 chaos scenarios, `k6` burst check, Langfuse tracing, local Ragas eval, Graphify code map, and automated tests). Note: `.github/workflows/{ci,live-cluster-chaos}.yml` are defined cleanly and locally mirror-verified, not executed on a hosted GitHub runner; destructive `scripts/reset.ps1` rebuild was not run to preserve the verified cluster state.

| Phase | Title | Status | Gate Summary | Phase File |
|---|---|---|---|---|
| Phase 0 | Discovery & Runnable Foundation | `VERIFIED` | Doctor, Compose PG/Redis, `/healthz`, `/readyz`, 11/11 pytest, Vite build passed (`docs/evidence/phase-00-foundation.txt`) | [00-discovery-and-foundation.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/phases/00-discovery-and-foundation.md) |
| Phase 1 | CMDB, Incidents & Privacy Boundary | `VERIFIED` | Alembic migration, idempotent CMDB seed (8 assets, 9 edges), redaction corpus (P=1.0/R=1.0), 42/42 pytest passed (`docs/evidence/phase-01-cmdb-privacy.txt`) | [01-cmdb-incidents-and-scrubbing.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/phases/01-cmdb-incidents-and-scrubbing.md) |
| Phase 2 | Hybrid RAG & Refusal Gate | `VERIFIED` | 18 runbooks/postmortems embedded (`nomic-embed-text` 768 dims), lexical+vector RRF, live `llama3.2:3b` diagnosis & refusal, 50/50 pytest passed (`docs/evidence/phase-02-hybrid-rag-refusal.txt`) | [02-hybrid-rag-and-refusal.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/phases/02-hybrid-rag-and-refusal.md) |
| Phase 3 | Durable Remediation & Verified Recovery | `VERIFIED` | 3 demo healthcare services on `kind-aegisops-local`, Terraform RBAC/quotas, OTel/Prom/Alertmanager, Redis locks, K8s SDK crash reconciliation, 60s watchdog, 55/55 pytest passed (`docs/evidence/phase-03-remediation-recovery.txt`) | [03-remediation-and-recovery.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/phases/03-remediation-and-recovery.md) |
| Phase 4 | SSO, Step-Up Approval & SRE Console | `VERIFIED` | Keycloak OIDC PKCE, pyotp TOTP step-up approval, RBAC/SSE API, React Console build (`59` modules), 2/2 Phase 4 integration & Playwright Chromium E2E passed (`docs/evidence/phase-04-auth-console.txt`) | [04-identity-and-sre-console.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/phases/04-identity-and-sre-console.md) |
| Phase 5 | Real Chaos, CI, Evaluation & Final Docs | `VERIFIED` | Langfuse (`53000`, `21` traces), 4 live chaos scenarios (`docs/evidence/chaos-scenarios-report.json`), k6 (`240/240`), local Ragas eval (`docs/evidence/ragas-evaluation.json`), Graphify (`1,356` nodes / `2,681` edges), full suite (`docs/evidence/phase-05-chaos-release.txt`) | [05-chaos-infrastructure-and-release.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/phases/05-chaos-infrastructure-and-release.md) |

---

## 2. Intended End-to-End Runtime Flow (Planned vs. Implemented)

**Planned Flow (to be implemented across Phases 1–5):**
1. **Fault & Telemetry**: Synthetic healthcare services (`eligibility-api`, `claims-processor`, `provider-directory`) in `kind-aegisops-local` emit Prometheus metrics and OpenTelemetry traces. Prometheus evaluates alert rules (`High5xxErrorRate`, `EligibilityDbPoolExhausted`, `ClaimsProcessorMemoryPressure`, `ProviderDirectoryHighLatencyCpu`) and routes firing/resolved alerts to Alertmanager.
2. **Authenticated Scrubbing & Durable Ingestion**: Alertmanager POSTs webhooks to FastAPI `POST /api/v1/webhooks/alertmanager`. The ingestion boundary verifies HMAC/Bearer credentials, scrubs SSNs, Member IDs, emails, JWTs, IPv4s, and contextual patient names before any log or persistence, deduplicates via partial unique index on `incidents`, and atomically inserts `Incident`, `IncidentEvent`, `AuditRecord`, and `OutboxJob(TRIAGE_INCIDENT)` inside one PostgreSQL transaction.
3. **CMDB Blast-Radius & Severity**: Cycle-safe PostgreSQL recursive CTE computes upstream dependencies (`A -> B` means `A depends_on B`) and downstream impacted services, producing a deterministic `P1–P4` severity explanation.
4. **Hybrid RAG & Refusal Gate**: The durable worker embeds the scrubbed alert summary via Ollama `nomic-embed-text:latest` (`768` dims), retrieves runbooks/postmortems via PostgreSQL FTS + `pgvector` cosine similarity combined by Reciprocal Rank Fusion (`k=60`), invokes Ollama `llama3.2:3b` with JSON schema output, validates with Pydantic, and passes the proposal through the server-side policy engine (`ALLOW_AUTO_EXECUTE`, `REQUIRE_APPROVAL`, or `REFUSE_AND_ESCALATE`).
5. **Approval & Locking**: High-risk actions (`memory_limit_increase_bounded`, `deployment_image_rollback`) enter `AWAITING_APPROVAL` and require an authenticated Keycloak `approver` user plus replay-protected `pyotp` TOTP verification bound to incident, playbook, parameter hash, target UID, and `resourceVersion`.
6. **Kubernetes Mutation & Watchdog Verification**: The worker acquires a single-instance Redis lease (`SET NX PX` + Lua renewal/release), persists `ExecutionAttempt` prior to calling the official Kubernetes Python SDK (`kind-aegisops-local` allowlisted context), executes or reconciles on crash, and transitions to `VERIFYING`. The watchdog checks rollout readiness, fresh Prometheus telemetry, traffic coverage, and functional health probes over a 60-second sustained recovery window before marking `RESOLVED`.
7. **Console & Observability**: React/Vite SRE Console displays OIDC PKCE login, `@xyflow/react` blast-radius graph, timelines, AI evidence, TOTP enrollment/approval, and measured MTTD/MTTR via REST + authenticated SSE. Local Langfuse and Ragas capture sanitized evaluations.

**Implemented Flow Today (Verified As-Built Across Phases 0–5):**
All seven stages above are implemented, running locally, and end-to-end verified in PostgreSQL (`55432`), Redis (`56379`), Keycloak (`58080`), Langfuse (`53000`), Ollama (`11434`), `kind-aegisops-local`, FastAPI (`58000`), Outbox Worker, and React Console (`55173`), with step-by-step code paths and measured results documented in [workingflow.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/workingflow.md) and [docs/VERIFICATION_REPORT.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/VERIFICATION_REPORT.md).

---

## 3. Resource Ownership & Boundary Map

| Resource Scope | Exclusive Owner | Notes |
|---|---|---|
| Control-plane Postgres/pgvector (`55432`), Redis (`56379`), Keycloak (`58080`), Langfuse (`53000`), OTel (`55317/55318`), Prometheus (`59090`), Alertmanager (`59093`) | `infra/compose/docker-compose.yml` | Isolated from existing host containers |
| Local Kubernetes cluster `kind-aegisops-local` | `kind` CLI + `infra/k8s/kind-config.yaml` | Maps NodePorts `30081–30084` to `58081–58084` |
| Namespaces (`aegisops-healthcare`, `aegisops-system`), RBAC (`aegisops-remediator`), `LimitRange`, `ResourceQuota` | Terraform (`infra/terraform/`) | Explicit `kube_context = "kind-aegisops-local"` |
| Healthcare services & demo DB/cache (`eligibility-api`, `claims-processor`, `provider-directory`, `postgres-claims-db`, `redis-session-cache`, `kube-state-metrics`) | Kubernetes manifests (`infra/k8s/workloads/`) | Logically isolated from control-plane storage |
| Database schema & HNSW/GIN indexes | Alembic (`backend/migrations/`) | Single source of truth for control-plane DDL |


---

## 4. Showcase Upgrade Program (Phases 00–07 — Visitor, Operator & Replay Architecture)

The Showcase Upgrade ([.planning/showcase/MASTER_PLAN.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/showcase/MASTER_PLAN.md)) extends the verified control plane with 15 user-facing & engineering features (`Features A–O`) while strictly preserving existing safety boundaries:

- **Audience vs. Authorization Separation**:
  - **Visitor Mode (Unauthenticated)**: Read-only exploration of Overview, sanitized Topology, Recorded Replay (`isolated from live cluster`), Fictional Privacy Scrubber Playground, Hybrid Search Tester, Engineering Evidence Page, and Recorded Guided Demo. Zero live cluster mutations, `.md` uploads, operational prompt dumps, or MFA approvals permitted.
  - **Operator (`operator`)**: Adds authenticated Chaos Lab launches (`5` scenarios), manual Business Transaction Probes (`Check Patient Eligibility`), Markdown runbook uploads (`PLAYBOOK_REGISTRY`-constrained), Baseline Reset (`aegisops-healthcare` scoped), and Pause Automation control.
  - **Approver (`approver`)**: Adds action-bound `pyotp` TOTP step-up approvals for `HIGH`-risk playbooks (`deployment_image_rollback` and `memory_limit_increase_bounded`).
  - **Presentation Toggle (`Executive Overview` vs. `Technical Deep-Dive`)**: Pure UI disclosure mode; never changes authorization or permissions.

| Showcase Phase | Title | Status | Phase File |
|---|---|---|---|
| Showcase Phase 00 | Repository Audit & Contracts | `VERIFIED` | [00-audit-and-contracts.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/showcase/phases/00-audit-and-contracts.md) |
| Showcase Phase 01 | Events, Permissions, Readiness & Controls | `VERIFIED` | [01-events-permissions-and-readiness.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/showcase/phases/01-events-permissions-and-readiness.md) |
| Showcase Phase 02 | Queue Filters, Provenance & 7-Step Lifecycle | `VERIFIED` | [02-dashboard-queue-and-lifecycle.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/showcase/phases/02-dashboard-queue-and-lifecycle.md) |
| Showcase Phase 03 | 5-Scenario Chaos Lab, Guided Tour & Business Probes | `VERIFIED` | [03-chaos-tour-and-business-probes.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/showcase/phases/03-chaos-tour-and-business-probes.md) |
| Showcase Phase 04 | Technical Inspectors, Knowledge Base & Live K8s Nodes | `VERIFIED` | [04-technical-inspectors.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/showcase/phases/04-technical-inspectors.md) |
| Showcase Phase 05 | Recorded Replay & Markdown/PDF Postmortems | `VERIFIED` | [05-replay-and-postmortems.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/showcase/phases/05-replay-and-postmortems.md) |
| Showcase Phase 06 | Value Metrics, Engineering Evidence & UI Polish | `VERIFIED` | [06-value-evidence-and-polish.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/showcase/phases/06-value-evidence-and-polish.md) |
| Showcase Phase 07 | Integrated Verification, Graphify & Final Handoff | `VERIFIED` | [07-regression-and-handoff.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/.planning/showcase/phases/07-regression-and-handoff.md) |
