# AegisOps Architecture & Engineering Decisions

## DEC-001: Python 3.12 Isolated Virtual Environment via `uv`
- **Context**: Host has Python 3.14.3 default, CPython 3.12.14, and `uv.exe`.
- **Alternatives Considered**: System Python 3.14, Poetry, Conda.
- **Chosen Behavior**: Use `uv venv .venv --python 3.12` and pin dependencies cleanly so binary wheels (`asyncpg`, `pgvector`, `cryptography`, `ragas`) resolve reliably without global `pip install`.
- **Tradeoffs**: Requires `.venv\Scripts\python.exe` invocation in scripts, which aligns with `scripts/*.ps1`.
- **Affected Files**: `scripts/setup.ps1`, `backend/pyproject.toml`, `backend/requirements.lock`

## DEC-002: Project-Local `.local/bin` for Missing `kind` and `terraform` Binaries
- **Context**: `kubectl` and `k6` are present on PATH; `kind` and `terraform` are absent; prompt forbids global tool installs.
- **Alternatives Considered**: WSL-only `kind`, requiring manual user pre-install, skipping Terraform.
- **Chosen Behavior**: `scripts/setup.ps1` downloads verified Windows amd64 `kind.exe` (`v0.27.0`) and `terraform.exe` (`1.10.5`) into `.local/bin/` (gitignored) and scripts prepend `.local/bin` to `$env:PATH`.
- **Tradeoffs**: Adds ~90 MB under `.local/` inside workspace, keeping the setup completely self-contained and reversible.
- **Affected Files**: `.gitignore`, `scripts/setup.ps1`, `scripts/doctor.ps1`, `scripts/up.ps1`

## DEC-003: Non-Conflicting Host Port Allocation (`53000–59093`)
- **Context**: Host already runs unrelated Docker containers on `3000`, `5432–5437`, `5439`, `6379`, `6380`, `6382`, `15432`.
- **Alternatives Considered**: Reusing host ports (impossible/unsafe) or stopping unrelated containers (prohibited).
- **Chosen Behavior**: Allocate dedicated AegisOps host ports `55432` (Postgres), `56379` (Redis), `58080` (Keycloak), `53000` (Langfuse), `59090` (Prometheus), `59093` (Alertmanager), `55317/55318` (OTel Collector, reassigned from `54317/54318` to avoid Windows Hyper-V excluded port range `54279–54378`), `58000` (FastAPI), `55173` (Frontend), `58081–58084` (`kind` NodePorts `30081–30084`).
- **Affected Files**: `.env.example`, `infra/compose/docker-compose.yml`, `infra/k8s/kind-config.yaml`

## DEC-004: Transactional Outbox in PostgreSQL for Durable Job Coordination
- **Context**: FastAPI background tasks lose work on process crash; Redis lists without DB coupling risk divergence.
- **Alternatives Considered**: Celery, RQ, Dramatiq, raw Redis Streams.
- **Chosen Behavior**: Transactional outbox table `outbox_jobs` written atomically inside the same PostgreSQL transaction as `incidents`, claimed by dedicated worker loops via `SELECT ... FOR UPDATE SKIP LOCKED` with lease expiration and crash recovery, paired with Redis per-target lease locks for Kubernetes mutation exclusivity.
- **Tradeoffs**: Eliminates dual-write inconsistency and keeps operational footprint simple and auditable.
- **Affected Files**: `backend/app/models/entities.py`, `backend/app/worker/runner.py`

## DEC-005: Directed CMDB Edge Semantics (`source_asset_id -> target_asset_id` means `source depends_on target`)
- **Context**: Dependency graphs are ambiguous without strict edge directionality.
- **Chosen Behavior**: An edge `A -> B` states `A` (consumer) depends on `B` (provider). When `B` fails, reverse recursive traversal yields downstream impacted consumers (`A`, etc.), while forward traversal yields upstream root-cause dependencies of `B`.
- **Affected Files**: `backend/app/cmdb/graph.py`, `backend/app/models/entities.py`

## DEC-006: Exclusive Infrastructure Resource Ownership
- **Context**: Multiple tools (`terraform`, `helm`, `kubectl apply`) mutating the same object cause drift.
- **Chosen Behavior**: Compose owns control-plane Docker containers; `kind` CLI owns cluster creation; Terraform owns namespaces, RBAC, LimitRange, and ResourceQuota; K8s YAML manifests own demo service workloads and `kube-state-metrics`.
- **Affected Files**: `infra/compose/`, `infra/k8s/`, `infra/terraform/`

## DEC-007: Database Failover Explicit Boundary
- **Context**: Prompt states database failover is an extension unless a real replicated DB with consistency checks, recovery procedure, and E2E test is built.
- **Chosen Behavior**: `postgres-claims-db` runs as a single demo primary instance; `RB-011` (`postgres_replication_lag`) explicitly refuses autonomous failover and escalates to human DBA/SRE. No simulated failover is presented as a completed feature.
- **Affected Files**: `runbooks/RB-011-postgres-replication-lag.md`, `backend/app/playbooks/registry.py`

## DEC-008: Separation of Kubernetes `readinessProbe` (`/healthz`) vs. SRE Health Gate (`/readyz`)
- **Context**: If Kubernetes `readinessProbe` points to `/readyz` and `/readyz` fails on DB pool exhaustion or broken canary `v1.9.0-broken`, `kube-proxy` removes all pods from Service/NodePort endpoints, blinding Prometheus scrapes and blocking canary rollout completion.
- **Chosen Behavior**: Kubernetes `readinessProbe` targets `/healthz` (`liveness`/process check) with `timeoutSeconds: 5` and `failureThreshold: 6` so broken canary pods finish rolling out and remain scrapable for `/metrics`. Service-level `/readyz` reflects real downstream dependencies (`postgres-claims-db`, `redis-session-cache`, canary health) and is evaluated directly by the Watchdog and Alertmanager/PromQL rules.
- **Affected Files**: `infra/k8s/workloads/eligibility-api.yaml`, `infra/k8s/workloads/claims-processor.yaml`, `infra/k8s/workloads/provider-directory.yaml`, `infra/k8s/workloads/postgres-claims-db.yaml`, `infra/k8s/workloads/redis-session-cache.yaml`, `backend/app/worker/watchdog.py`

## DEC-009: Sliding Latency Gauge (`http_recent_p95_latency_seconds`) & App Concurrency Slot (`Semaphore(2)`)
- **Context**: Aggregating `rate(http_request_duration_seconds_bucket[30s])` across multiple scaled-out replicas behind a single static NodePort scrape target produces counter-reset artifacts and PromQL binary `and` label mismatches (`cluster` label mismatch across pods vs `sum()`).
- **Chosen Behavior**: Services export an in-process 12-second sliding-window p95 gauge (`http_recent_p95_latency_seconds`) computed across the previous scrape window, scraped cleanly via `max by (service, namespace, cluster) (...)` aligned identically on both sides of PromQL traffic guards. `provider-directory` enforces `asyncio.Semaphore(2)` with `0.22s` simulated work under fault so horizontal scale-out from `1` to `3` pods measurably reduces tail latency.
- **Affected Files**: `services/shared/base_service.py`, `services/provider-directory/main.py`, `infra/compose/prometheus/alert_rules.yml`, `chaos/run_scenario.py`

## DEC-010: Literal SQL Predicate Inside `pg_insert(...).on_conflict_do_nothing(index_where=...)`
- **Context**: Passing a bound parameter via SQLAlchemy `.notin_([...])` inside `index_where` succeeds for the first four calls and then fails on the fifth call when `asyncpg` switches to a cached generic prepared plan (`InvalidColumnReferenceError` / partial index predicate mismatch).
- **Chosen Behavior**: Use an explicit literal SQL predicate `text("state NOT IN ('RESOLVED', 'FAILED')")` matching the exact DDL definition of `ix_incidents_active_dedup_key` in `0001_initial_schema.py`.
- **Affected Files**: `backend/app/api/webhooks.py`, `backend/migrations/versions/0001_initial_schema.py`
