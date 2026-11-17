# AegisOps Dependencies & Context7 Lookup Log

This document records pinned runtime dependencies, local binary/container versions, and verified Context7 documentation lookups used to design and verify AegisOps APIs.

## 1. Local Toolchain & Model Versions (Verified 2026-11-17)
- **Python**: `3.12.14` (`uv venv .venv --python 3.12`)
- **Node.js / npm**: `v26.7.0` / `11.19.0`
- **Docker / Compose**: `29.9.2` / `v5.6.1`
- **kubectl**: `v1.36.0`
- **k6**: `v2.2.0`
- **kind** (project-local `.local/bin/kind.exe`): `v0.27.0` (verified installed)
- **terraform** (project-local `.local/bin/terraform.exe`): `v1.10.5` (verified installed)
- **Ollama CLI**: `0.40.10`
  - `nomic-embed-text:latest`: manifest `sha256:0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`, config `sha256:31df23ea7daa448f9ccdbbcecce6c14689c8552222b80defd3830707c0139d4f`, **768 embedding dimensions**.
  - `llama3.2:3b`: manifest `sha256:a80c4f17acd55265feec403c7aef86be0c25983ab279d83f3bcd3abbcb5b8b72`, config `sha256:34bb5ab01051a11372a91f95f3fbbc51173eed8e7f13ec395b9ae9b8bd0e242b`.
  - `llama3.2:1b`: cached fallback.

## 2. Container Image Versions (Pinned)
- PostgreSQL + pgvector: `pgvector/pgvector:pg16`
- Redis: `redis:7.4-alpine`
- Keycloak: `quay.io/keycloak/keycloak:26.0`
- Langfuse: `langfuse/langfuse:2`
- OpenTelemetry Collector Contrib: `otel/opentelemetry-collector-contrib:0.114.0`
- Prometheus: `prom/prometheus:v2.55.1`
- Alertmanager: `prom/alertmanager:v0.27.0`
- Kubernetes `kind` node image: `kindest/node:v1.32.2`

## 3. Context7 Documentation Verification Log

| Library | Context7 ID | Source URL | Question | Resulting Decision |
|---|---|---|---|---|
| FastAPI | `/websites/fastapi_tiangolo` | `https://fastapi.tiangolo.com/advanced/events/` | Lifespan context manager & dependency `yield` | Use `@asynccontextmanager async def lifespan(app: FastAPI)` for engine/Redis pool startup & teardown, and `yield` dependencies for per-request `AsyncSession`. |
| SQLAlchemy | `/websites/sqlalchemy_en_20_orm` | `https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html`, `https://docs.sqlalchemy.org/en/20/orm/queryguide/query.html` | `async_sessionmaker`, `with_for_update`, and `cte(recursive=True)` | Configure `async_sessionmaker(engine, expire_on_commit=False)`, use `SELECT ... FOR UPDATE` for state transitions & outbox claims, and use `WITH RECURSIVE` CTEs with cycle path guard. |
| pgvector-python | `/pgvector/pgvector-python` | `https://github.com/pgvector/pgvector-python` | `VECTOR(dim)` column & `cosine_distance` | Define `Mapped[list[float]] = mapped_column(VECTOR(768))` and compute cosine similarity as `1.0 - Runbook.embedding.cosine_distance(query_vec)` with HNSW `vector_cosine_ops` index. |
| Ollama Python | `/ollama/ollama-python` | `https://github.com/ollama/ollama-python/blob/main/_autodocs/api-reference/module-functions.md` | Structured outputs & `/api/embed` | Pass `format=DiagnosisProposal.model_json_schema()` and `options={'temperature': 0}` to `chat`, then `DiagnosisProposal.model_validate_json(...)`; use `/api/embed` (`EmbedResponse.embeddings`) with dimension check. |
| Kubernetes Python Client | `/kubernetes-client/python` | `https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/AppsV1Api.md` | `patch_namespaced_deployment` & `CoreV1Api` | Load explicit kubeconfig context via `load_kube_config(context="kind-aegisops-local")`, wrap sync `AppsV1Api.patch_namespaced_deployment` in `asyncio.to_thread`, and enforce `_request_timeout`. |
| redis-py | `/redis/redis-py` | `https://github.com/redis/redis-py/blob/master/redis/lock.py` | Atomic acquisition, Lua ownership release/renewal | Use `SET key token NX PX ttl_ms` and atomic Lua scripts comparing `redis.call('get', KEYS[1]) == ARGV[1]` for extend/release (`LockNotOwnedError` handling). |
| Langfuse Python SDK | `/langfuse/langfuse-python` | `https://github.com/langfuse/langfuse-python` | Trace correlation & redaction safety | Use `langfuse==2.60.10` `Langfuse(...)` client (`client.trace(...)` / `.generation(...)`) passing pre-scrubbed inputs exclusively with `incident_id` correlation. |
| Ragas | `/vibrantlabsai/ragas` | `https://github.com/vibrantlabsai/ragas/blob/main/docs/howtos/llm-adapters.md` | Local Ollama adapter | Context7 documented `llm_factory(..., provider="openai")` for Ragas `>=0.3`; against the installed `ragas==0.2.15` package in `backend/requirements.lock`, `backend/app/observability/ragas_eval.py` wraps `ChatOpenAI(api_key="ollama", base_url="http://127.0.0.1:11434/v1")` and `OpenAIEmbeddings` with `LangchainLLMWrapper` / `LangchainEmbeddingsWrapper` and sequential `RunConfig(max_workers=1, timeout=180)`. |
| PyJWT | `/jpadilla/pyjwt` | `https://github.com/jpadilla/pyjwt/blob/master/docs/usage.rst` | `PyJWKClient` RS256 OIDC JWT validation | Fetch JWKS via `PyJWKClient(jwks_url)` and call `jwt.decode(..., algorithms=["RS256"], issuer=..., audience=...)` with explicit `verify_exp` & `verify_nbf`. |
| PyOTP | `/pyauth/pyotp` | `https://github.com/pyauth/pyotp/blob/main/_autodocs/api-reference/totp.md` | Secret generation & replay prevention | Use `pyotp.random_base32(32)` and `TOTP.verify_and_get_timecode(otp, valid_window=1)` paired with stored `last_used_timecode` comparison inside a DB transaction. |
| React Flow | `/websites/reactflow_dev` | `https://reactflow.dev/learn/tutorials/slide-shows-with-react-flow` | Custom nodes, edges, `onNodeClick`, `fitView` | Use `@xyflow/react` `<ReactFlow>` with typed custom nodes and `useReactFlow().fitView` for interactive blast-radius focusing. |

## 4. Python & Frontend Package Pinning
- **Backend lockfile**: [backend/requirements.lock](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/backend/requirements.lock) (`136` resolved packages):
  - `fastapi==0.115.14`, `uvicorn==0.34.3`, `pydantic==2.11.10`, `pydantic-settings==2.8.1`
  - `sqlalchemy==2.0.58`, `asyncpg==0.30.0`, `psycopg-binary==3.2.13`, `alembic==1.15.2`, `pgvector==0.3.6`
  - `redis==5.3.1`, `httpx==0.28.1`, `ollama==0.5.4`, `kubernetes==32.0.1`
  - `pyjwt==2.11.0`, `cryptography==45.0.7`, `pyotp==2.12.0`
  - `prometheus-client==0.22.1`, `opentelemetry-api==1.31.1`, `opentelemetry-sdk==1.31.1`
  - `langfuse==2.60.10`, `ragas==0.2.15`, `openai==1.109.1`
  - `pytest==8.4.2`, `pytest-asyncio==0.26.0`, `ruff==0.10.0`, `mypy==1.15.0`, `playwright==1.52.0`
- **Frontend lockfile**: [frontend/package-lock.json](file:///d:/PROJECTS/AegisOps%20An%20Autonomous%20AIOps,%20CMDB%20Blast-Radius%20&%20Self-Healing%20Kubernetes%20Control/frontend/package-lock.json):
  - `react@18.3.1`, `react-dom@18.3.1`, `@xyflow/react@12.4.4`, `lucide-react@0.474.0`, `qrcode.react@4.2.0`, `typescript@5.7.3`, `vite@6.0.11`
