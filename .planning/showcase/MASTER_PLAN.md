# AegisOps Showcase Upgrade — Master Plan

> **Scope:** Upgrade the verified AegisOps AIOps control plane (Phases 0–5 complete) into an interactive, dual-audience product showcase for non-technical visitors (recruiters, founders, managers) and technical reviewers (SREs, platform & security engineers), without breaking existing APIs, security boundaries, or Playwright/pytest gates.

## 1. Guiding Principles
- **Truthful Runtime State:** No fake timers masquerading as recovery verification, no invented manual baseline (`"Baseline not configured"` unless user-supplied), no equation of redacted token count with distinct patients, and explicit separation of `live_alert`, `interactive_demo`, `automated_test`, `recorded_replay`, and `unknown` provenance.
- **Least-Privilege & Visitor Safety:** Unauthenticated visitors explore a rich read-only/replay experience (plus zero-persistence privacy playground, knowledge browser, search tester, and engineering evidence). Interactive launches, probes, uploads, baseline resets, and automation pauses require `operator` + CSRF; high-risk remediation (`memory_limit_increase_bounded`, `deployment_image_rollback`) strictly requires `approver` + action-bound TOTP MFA.
- **Compatibility Preserved:** Existing Phase 0–5 Playwright selectors (`Sign In with Keycloak OIDC (PKCE)`, `AegisOps SRE Console`, `CMDB Dependency & Blast-Radius Topology`, `Stream: live`, `[Re-]enroll TOTP MFA`, `Sign Out`), webhook contracts, Redis locks, K8s RBAC impersonation, and 57 backend tests remain intact.

## 2. Phased Roadmap & Dependencies

| Phase | Title | Depends On | Key Features | Gate Requirement |
|---|---|---|---|---|
| `00` | Audit & Contracts | — | Repo audit, `.planning/showcase/*`, `OVERALL_FLOW.md` | Features A–O audited, shared API/DB contracts & phase files written |
| `01` | Events, Permissions, Readiness & Controls | `00` | `M` (`readiness`, `reset`, `pause`), `O` (`visitor` role), `E` prompt capture, `B` per-tick watchdog, Alembic `0002` | Migration applied; readiness/RBAC/reset/pause/prompt capture tested |
| `02` | Queue Filters, Provenance & 7-Step Lifecycle | `01` | `B` (7-step UI contract), `C` (queue tabs, `Hide Test Runs`, provenance, pagination, URL filters), SSE `after_seq` | Filter tabs/pagination/counts & 7-step branching verified in DB+API |
| `03` | Chaos Lab, Guided Tour & Business Probes | `01`, `02` | `A` (5-scenario 1-click Chaos Lab + conflict/idempotency), `J` (real business transaction probes), `I` (Guided Demo narration contract) | 5 scenarios + probes + conflict exclusion + Scenario 5 PII/RB-011 escalation verified |
| `04` | Technical Inspectors & Live K8s Topology | `01`, `02`, `03` | `E` (privacy playground + prompt inspector), `F` (runbook browser, `.md` upload + indexing, hybrid search tester), `G` (live K8s node facts), `K` (Why This Action card) | Playground zero-leak, upload validation/lifecycle, hybrid score breakdown, K8s node facts verified |
| `05` | Replay & Postmortem Exports (`.md` / `.pdf`) | `01`, `02`, `03` | `L` (isolated frame replay), `H` (common snapshot model -> Markdown + pure-Python `%PDF-1.4` export) | Replay frame reconstruction/isolation & `.md`/`.pdf` parity/auth verified |
| `06` | Value Metrics, Evidence View & Complete UI | `02`..`05` | `D` (honest business impact cards), `N` (Engineering Evidence page), `I`/`O` (Guided Tour UI, Visitor Mode, Executive/Technical mode, responsive & a11y UI) | `tsc`, `vite build`, a11y checks & Playwright browser flows pass |
| `07` | Integrated Verification, Graphify & Final Handoff | `06` | Full regression + browser chaos E2E, Graphify refresh, `workingflow.md` (19 sections), `SHOWCASE_GUIDE.md`, `SHOWCASE_TEST_REPORT.md`, `FILE_MAP.md` | All automated, integration & live browser suites pass; `verify_docs.py` exits `0` |
