# AegisOps Verification Report

> **Status:** `PASS` (Local Complete Verification across Base Phases `0–5` and Showcase Phases `00–07` as of `2026-11-17T11:18+05:30`). Hosted GitHub Actions runner execution and destructive `scripts/reset.ps1` cluster deletion remain explicitly unexecuted locally (see Section 4).

## 1. Phase Gate Summary
| Phase | Status | Evidence Artifact |
|---|---|---|
| Base Phases `0–5` | `PASS` (`57/57` prior gate) | [phase-00-foundation.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/evidence/phase-00-foundation.txt) .. [phase-05-chaos-release.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/evidence/phase-05-chaos-release.txt), [chaos-scenarios-report.json](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/evidence/chaos-scenarios-report.json), [k6-summary.json](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/evidence/k6-summary.json), [ragas-evaluation.json](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/evidence/ragas-evaluation.json) |
| Showcase Phases `00–07` | `PASS` (`65/65` final gate) | [showcase-test-gate.txt](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/evidence/showcase-test-gate.txt), [SHOWCASE_TEST_REPORT.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/SHOWCASE_TEST_REPORT.md) |

## 2. Final Automated Showcase Gate (`.\scripts\test.ps1` -> `docs/evidence/showcase-test-gate.txt`)
- **Timestamp**: `2026-11-17T11:18+05:30` (`ExitCode: 0`)
- **Ruff (`ruff check --config backend/pyproject.toml backend`)**: `All checks passed!`
- **Mypy (`mypy --config-file backend/pyproject.toml backend/app`)**: `Success: no issues found in 50 source files`
- **Pytest (`backend/tests`)**: `65 passed in 220.05s` (`0` failed, `0` skipped), spanning:
  - `32` unit checks (`config`, `scrubber` precision=1.0/recall=1.0, `policy_refusal`, `state_machine`)
  - `2` Playwright Chromium E2E tests (`test_browser_console.py` + `test_showcase_browser.py` covering Visitor Mode, Recorded Replay, Privacy Playground, Hybrid Search Tester, Engineering Evidence page, Keycloak OIDC PKCE, `Check Patient Eligibility`, TOTP QR modal, and Baseline Reset modal)
  - `31` live integration tests against Postgres `0002`, Redis, Ollama, Keycloak, and `kind-aegisops-local` (plus explicit mocked failure/timeout/missing-telemetry checks)
- **Frontend Build**: `tsc -b` + `vite build` transformed `68` modules cleanly in `5.06s`.

## 3. Benchmarks & Graphify Mapping
- **Live 4-Scenario Chaos Suite**: Executed via `chaos/run_scenario.py` (`docs/evidence/chaos-scenarios-report.json`); all 4 scenarios verified fault persistence, remediated, completed 60s watchdog verification, and reached `RESOLVED`. Showcase Scenario 5 (`pii_leak_and_db_failure`) verified end-to-end via `test_showcase_scenarios_and_probes.py`.
- **`k6` Burst Benchmark**: `240/240` checks (`100.00%`), `0.00%` `http_req_failed` across `120` requests, `p95=1109.0ms < 1500ms` (`docs/evidence/k6-summary.json`).
- **Local Sequential Ragas**: `faithfulness=0.7083`, `context_recall=0.8586` (`3/5` scored, `2/5` `NaN` due to local `llama3.2:3b` output formatting/timeout variance in NLI statements -> `docs/evidence/ragas-evaluation.json`).
- **Graphify Knowledge Graph**: Refreshed after Showcase completion (see [CODEMAP.md](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/docs/CODEMAP.md)).

## 4. Explicit Verification Boundaries (Unclaimed / Not Executed Here)
- **GitHub Actions Hosted Runners**: `.github/workflows/ci.yml` and `.github/workflows/live-cluster-chaos.yml` are checked locally and not executed on remote GitHub runners.
- **Destructive Clean Reset (`scripts/reset.ps1`)**: Omitted on the verified cluster to preserve verified live state; operator `Restore Demo Baseline` (`aegisops-healthcare` scoped) is tested live.
- **Database Failover Extension & Non-Clinical Disclaimer**: `RB-011` refuses automated DB failover on single-instance `postgres-claims-db`; synthetic corpus metrics do not imply HIPAA compliance or clinical production readiness.
