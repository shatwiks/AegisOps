# AegisOps Showcase Upgrade — Requirements (`REQ-SHOW-*`)

Statuses: `MISSING`, `PARTIAL`, `IMPLEMENTED`, `VERIFIED`, `BLOCKED`.

## Feature A — Five-Scenario One-Click Chaos Lab
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-A01` | Top-level Chaos Lab displaying all 5 understandable scenarios (`traffic_spike`, `db_pool_freeze`, `bad_canary_update`, `oom_memory_crash`, `pii_leak_and_db_failure`), preconditions, expected actions, and launch state without CLI scripts. | `MISSING` | `MISSING` |
| `REQ-SHOW-A02` | Server-owned durable `DemoRun` orchestration (`202 Accepted`), launch idempotency, bounded runtime, audit events, and resource-scoped conflict exclusion returning the blocking run/incident. | `MISSING` | `MISSING` |
| `REQ-SHOW-A03` | Scenarios 1–4 inject real workload faults triggering real Prometheus alerts -> remediation -> 60s verification (with MFA step-up required for `bad_canary_update` rollback and `oom_memory_crash` 192Mi->384Mi adjustment); Scenario 5 injects fictional PII + demo `postgres-claims-db` fault forcing redaction + safe `RB-011` human DBA escalation. | `PARTIAL` (CLI 1–4 exist; UI/Scenario 5 missing) | `PARTIAL` |

## Feature B — Seven-Step Incident Lifecycle & Live Verification Progress
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-B01` | Horizontal (wide) / vertical (narrow) 7-step lifecycle derived from persisted backend events & timestamps (`Alert Caught` -> `Sensitive Data Scrubbed` -> `Service Impact Mapped` -> `Runbooks & AI Diagnosis` -> `Policy / MFA Decision` -> `Recovery Verification` -> `Terminal Outcome`). | `MISSING` | `MISSING` |
| `REQ-SHOW-B02` | Live Watchdog sample progress persisted every tick (`verification_state_json`: e.g. `"Checking service stability: 35 of 60 seconds observed"`, reset counts, missing/stale failure handling); terminal `ESCALATED`/`FAILED` runs never render a green Resolved step. | `PARTIAL` | `PARTIAL` |
| `REQ-SHOW-B03` | Ordered monotonic event sequence numbers + SSE/snapshot resync on refresh/reconnect preserving selected incident/run state. | `PARTIAL` | `PARTIAL` |

## Feature C — Incident Queue Filters & Trusted Provenance
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-C01` | Tabs `Active`, `Resolved`, `Escalated`, `Failed`, `All` + **Hide Test Runs** toggle (ON by default) + severity, service, search, sort, and SQL-backed pagination/tab counts preserved in URL query params. | `PARTIAL` | `PARTIAL` |
| `REQ-SHOW-C02` | Trusted `source_provenance` classification (`live_alert`, `interactive_demo`, `automated_test`, `recorded_replay`, `unknown`) set from trusted webhook/runner metadata rather than fragile title string guessing. | `MISSING` | `MISSING` |

## Feature D — Honest Business Impact & Measured Value
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-D01` | Plain-English value summary cards (redacted tokens, CMDB potential vs observed degraded services, business probe recoveries, MTTD/MTTR timestamps & sample counts, and `"Baseline not configured"` unless a user-supplied assumption is entered). | `PARTIAL` | `PARTIAL` |
| `REQ-SHOW-D02` | Metrics API & UI separate `live_and_demo`, `automated_test`, and `all` scopes consistently and distinguish mutation time vs sustained observation window vs end-to-end MTTR. | `PARTIAL` | `PARTIAL` |

## Feature E — Privacy Scrubber Playground & Sanitized Prompt Inspector
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-E01` | Zero-persistence, rate-limited Privacy Playground using production `scrub_text` with fictional presets, side-by-side redacted output, counts, and documented regex/name coverage boundaries. | `PARTIAL` | `PARTIAL` |
| `REQ-SHOW-E02` | Authorized Sanitized Prompt Inspector showing the actual delimited prompt, context citations, model/version, timestamp, latency, and validated output captured at Ollama call time (or `"not captured"` for legacy rows). | `MISSING` | `MISSING` |

## Feature F — Runbook Browser, Markdown Upload & Hybrid Search Tester
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-F01` | Searchable Runbook/Postmortem browser displaying real DB count, doc type, version, source, tags, risk tier, permitted playbook, indexing status, and safe rendered/raw Markdown view. | `MISSING` | `MISSING` |
| `REQ-SHOW-F02` | Authorized `.md` upload (`<= 64KiB`, UTF-8, frontmatter validation, XSS stripping, scrubbing, `PLAYBOOK_REGISTRY` policy enforcement so uploads cannot invent commands or lower risk tiers) with `UPLOADED -> VALIDATING -> INDEXING -> READY/FAILED` lifecycle & retry. | `MISSING` | `MISSING` |
| `REQ-SHOW-F03` | Interactive **Test Hybrid Search** calling `hybrid_search_runbooks`, showing lexical score/rank, cosine similarity, RRF score/rank, model dimensions (`768`), and explicit `0.78` cosine vs non-probabilistic RRF explanation + degraded/empty states. | `MISSING` | `MISSING` |

## Feature G — Live Kubernetes Facts on Topology Nodes
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-G01` | Read-only backend K8s summary attached to CMDB topology nodes (`ready / desired` label, container image/version, target container memory limit, rollout status, freshness timestamp) + before/after node diff for selected run + accessible Table View toggle. | `PARTIAL` | `PARTIAL` |

## Feature H — Postmortem Export in Markdown and PDF
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-H01` | Unified server-side incident snapshot model exporting authorized `.md` and multi-page `%PDF-1.4` reports (no remote asset fetching, safe filenames, escaped content, resolved vs escalation/failure labeling, zero TOTP/secret leakage). | `MISSING` | `MISSING` |

## Feature I — Guided Tour & Explore Freely
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-I01` | Prominent **Start Guided Demo** experience with event-driven narration synced to persisted stages, panel focus cues, Pause/Skip/Exit controls, refresh persistence, reduced-motion support, and replay mode support for visitors. | `MISSING` | `MISSING` |

## Feature J — Real Business Transaction Recovery Probe
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-J01` | Allowlisted **Check Patient Eligibility** & service transaction probes verifying JSON semantics, latency, bounded history correlation, and manual trigger (`operator+`), cleanly separating app failure from probe unavailability. | `MISSING` | `MISSING` |

## Feature K — "Why This Action?" Decision Explanation
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-K01` | Structured 7-question decision card separating AI Hypothesis Recommendation, Server Policy Authorization, Step-Up MFA / Execution, and Observed Outcome with explicit blockers and recorded alternatives. | `PARTIAL` | `PARTIAL` |

## Feature L — Recorded Incident Replay
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-L01` | Play/Pause/Speed/Step/Seek timeline reconstruction of captured runs & labeled illustrative fixtures without mutating live cluster/DB state or polluting live caches. | `MISSING` | `MISSING` |

## Feature M — Readiness, Restore Demo Baseline & Operator Controls
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-M01` | Global and per-scenario readiness endpoint (`Ready`/`Degraded`/`Blocked`/`Unknown`) checking cluster context, workloads, telemetry freshness, PG/Redis/worker, Ollama models, runbook index, and Keycloak JWKS. | `PARTIAL` | `PARTIAL` |
| `REQ-SHOW-M02` | Previewable, idempotent **Restore Demo Baseline** (`operator+`) strictly scoped to `aegisops-healthcare` demo resources, preserving incident/audit history and labeling resolved active incidents as `manual_reset_assisted` rather than autonomous recovery. | `MISSING` | `MISSING` |
| `REQ-SHOW-M03` | Backend-enforced `automation_paused` operator toggle holding automated execution safely with explicit in-flight boundary notice. | `MISSING` | `MISSING` |

## Feature N — Engineering Evidence Page
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-N01` | Dedicated reviewer page displaying architecture/trust boundaries, active git commit/version metadata, parsed test/chaos/k6/Ragas reports with dates/scopes/caveats, and links to `workingflow.md` & docs. | `MISSING` | `MISSING` |

## Feature O — Visitor Access, Operator Access & Presentation Modes
| ID | Requirement | Initial Audit | Status |
|---|---|---|---|
| `REQ-SHOW-O01` | Safe **Visitor Mode** allowing unauthenticated exploration of Overview, Topologies (sanitized), Replays, Privacy Playground, Hybrid Search Tester, Evidence Page, and Tour without granting operator mutations or operational prompt/approval leakage. | `MISSING` | `MISSING` |
| `REQ-SHOW-O02` | Server-enforced RBAC matrix (`visitor`, `viewer`, `operator`, `approver`) across all new HTTP routes, SSE, exports, uploads, prompt inspector, plus `Executive Overview` vs `Technical Deep-Dive` presentation toggle that never escalates privileges. | `PARTIAL` | `PARTIAL` |
