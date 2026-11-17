# AegisOps HTTP & SSE API Contract

> **Status:** All Showcase & control-plane routes verified against FastAPI OpenAPI schema (`127.0.0.1:58000`) through Showcase Phase 07 (`65/65` pytest passing including Playwright Chromium E2E, `Ruff`, `Mypy` `50` files, and `Vite` `68` modules).

## 1. Health, Ingress & Identity Routes

| Method & Path | Auth Requirement | Purpose |
|---|---|---|
| `GET /healthz` | Public | Process liveness probe |
| `GET /readyz` | Public | Dependency readiness (`postgres` pgvector, `redis`) |
| `GET /metrics` | Public (Prometheus scrape) | Control-plane Prometheus metrics (`API_REQUESTS_TOTAL`, etc.) |
| `POST /api/v1/webhooks/alertmanager` | HMAC-SHA256 / Bearer | Earliest-boundary scrubbed Alertmanager webhook ingestion (`256 KiB` cap, rate limit, SSRF guard, trusted `X-AegisOps-Provenance`, active `DemoRun` correlation) |
| `GET /api/v1/auth/config` | Public | Returns public Keycloak OIDC issuer, client ID (`aegisops-console`), and PKCE endpoints |
| `POST /api/v1/auth/oidc/exchange` | Public (PKCE `code` + `code_verifier`) | Exchanges code at Keycloak, validates ID/access RS256 JWTs, sets `HttpOnly` session cookie + CSRF token |
| `GET /api/v1/auth/me` | Authenticated (`viewer+`) | Returns current user identity, derived server role, and TOTP enrollment status |
| `POST /api/v1/auth/logout` | Authenticated + CSRF | Clears browser session & CSRF cookies |
| `POST /api/v1/auth/totp/enroll` | `approver` + CSRF | Provisions Fernet-encrypted `pyotp` secret + `otpauth://` QR provisioning URI |
| `POST /api/v1/auth/totp/verify-enrollment` | `approver` + CSRF | Confirms first OTP code (`valid_window=1`) and activates enrolled MFA state |

## 2. Core Topology, Incidents, Approvals, Metrics & Streaming Routes

| Method & Path | Auth Requirement | Purpose |
|---|---|---|
| `GET /api/v1/topology` | `visitor+` | CMDB assets, directed `depends_on` edges, 3s TTL cached read-only `k8s_live` facts (`ready_replicas/desired`, image, container, memory limit, rollout status), & optional `incident_id` diff |
| `GET /api/v1/topology/{asset_slug}/blast-radius` | `visitor+` | Cycle-safe recursive CTE upstream dependencies & downstream affected consumers |
| `GET /api/v1/incidents` | Authenticated (`viewer+`) | Filtered incident queue (`tab`, `hide_test_runs`, `provenance`, `severity`, `service`, `search`, `sort`, pagination, SQL `tab_counts`) |
| `GET /api/v1/incidents/{incident_id}` | Authenticated (`viewer+`) | Full detail: 7-step `lifecycle_steps`, 7-question `why_this_action`, RAG citations, `business_probes`, approvals, execution diffs |
| `GET /api/v1/incidents/{incident_id}/prompt` | Authenticated (`viewer+`) | Exact captured XML-delimited Ollama prompt record (or explicit uncaptured notice) + `why_this_action` |
| `GET /api/v1/incidents/{incident_id}/postmortem.md` | Authenticated (`viewer+`) | Escaped sanitized Markdown postmortem report derived from unified server snapshot |
| `GET /api/v1/incidents/{incident_id}/postmortem.pdf` | Authenticated (`viewer+`) | Pure-Python multi-page `%PDF-1.4` postmortem export without external asset fetching |
| `POST /api/v1/incidents/{incident_id}/approve` | `approver` + TOTP + CSRF | Single-use action-bound MFA approval with live Kubernetes UID & `resourceVersion` drift check |
| `POST /api/v1/incidents/{incident_id}/deny` | `approver` + CSRF | Rejects pending high-risk action and transitions incident to `ESCALATED` |
| `GET /api/v1/metrics/summary` | `visitor+` | Scoped (`live_and_demo`/`automated_test`/`all`) MTTD/MTTR distributions, business value counters, and optional `manual_baseline_minutes` (default `"Baseline not configured"`) |
| `GET /api/v1/stream/incidents` | Authenticated (`viewer+`) | Authenticated SSE stream polling PostgreSQL every `2.0s` with `after_seq` / `Last-Event-ID` catch-up & `demo_runs` snapshots |

## 3. Runbook Knowledge Base & Showcase Control Endpoints

| Method & Path | Auth Requirement | Purpose |
|---|---|---|
| `GET /api/v1/runbooks` | `visitor+` | Searchable runbook/postmortem browser returning real DB indexed `counts` |
| `GET /api/v1/runbooks/{slug}` | `visitor+` | Full sanitized Markdown document and risk/playbook metadata |
| `POST /api/v1/runbooks/upload` | `operator+` + CSRF | Validates `.md` (<= `64 KiB`, UTF-8, XSS guard, YAML frontmatter, `PLAYBOOK_REGISTRY` checks), persists through `UPLOADED -> VALIDATING -> INDEXING -> READY/FAILED` |
| `POST /api/v1/runbooks/{slug}/retry-index` | `operator+` + CSRF | Retries local Ollama embedding generation for failed/pending uploaded runbooks |
| `POST /api/v1/runbooks/search` | `visitor+` | Interactive Hybrid Search Tester returning lexical rank/score, vector cosine similarity, RRF (`k=60`), `0.78` threshold gate, and plain-English explanation |
| `GET /api/v1/showcase/overview` | `visitor+` | Role-aware executive summary & frontend capability flags |
| `GET /api/v1/showcase/readiness` | `visitor+` | Global (`Ready`/`Degraded`/`Blocked`/`Unknown`) & per-scenario dependency readiness check |
| `GET /api/v1/showcase/controls` | `visitor+` | Current backend-enforced automation control flags |
| `POST /api/v1/showcase/controls/automation` | `operator+` + CSRF | Toggles `automation_paused` switch (holds future dispatches without mutating prior rollouts) |
| `POST /api/v1/showcase/reset/preview` | `operator+` + CSRF | Previews exact deployment diffs in `aegisops-healthcare` before restoring baseline |
| `POST /api/v1/showcase/reset/execute` | `operator+` + CSRF | Idempotent scoped demo baseline reset preserving audit history (`manual_reset_assisted` labeling if active runs closed) |
| `GET /api/v1/showcase/scenarios` | `visitor+` | Returns 5-scenario Chaos Lab catalog + recent `DemoRun` history |
| `POST /api/v1/showcase/scenarios/{scenario_id}/launch` | `operator+` + CSRF | Idempotent durable `DemoRun` launcher (`202 Accepted`, `409 Conflict` across dependent workloads) |
| `GET /api/v1/showcase/runs/{run_id}` | `visitor+` | Returns `DemoRun`, event-driven Guided Tour `narration`, correlated probes & 7-step lifecycle |
| `GET /api/v1/showcase/probes` | `visitor+` | Bounded history of semantic business transaction recovery probes |
| `POST /api/v1/showcase/probes/run` | `operator+` + CSRF | Executes SSRF-safe allowlisted business probe (`eligibility-api`, `claims-processor`, `provider-directory`, `postgres-claims-db`) |
| `GET /api/v1/showcase/privacy/presets` | `visitor+` | Returns 3 fictional synthetic log presets and regex/key-allowlist coverage notes |
| `POST /api/v1/showcase/privacy/preview` | `visitor+` | Zero-persistence, zero-log in-memory deterministic scrubber playground (`<= 8 KiB`, Redis `30 req/60s` rate limit) |
| `GET /api/v1/showcase/replays` | `visitor+` | Lists `captured_live_run` timelines and clearly labeled `illustrative_fixture` replays |
| `GET /api/v1/showcase/replays/{replay_id}` | `visitor+` | Read-only frame reconstruction without mutating live DB, Redis, or Kubernetes |
| `GET /api/v1/showcase/evidence` | `visitor+` | Serves live build/git/Alembic metadata, Ragas/k6 benchmarks, test gate artifacts, and architectural limits |
