# AegisOps Architecture

> **Status:** Phases 0–5 implemented and verified end-to-end (`kind-aegisops-local`, CMDB + privacy scrubber, Hybrid RAG + Ollama refusal gate, Terraform RBAC, Redis leases, K8s Python SDK executor, 60s sustained watchdog, Keycloak OIDC PKCE + TOTP console, Langfuse traces, and 4 live chaos scenarios).

## 1. System Boundaries & Isolation
- **Control-Plane Storage** (`aegisops-postgres` on `127.0.0.1:55432`, `aegisops-redis` on `127.0.0.1:56379`): Isolated on Docker Compose network; never targeted by chaos scenarios. (`01-init.sql` also bootstraps isolated `aegisops_langfuse` database.)
- **Target Cluster** (`kind-aegisops-local`): Runs `aegisops-healthcare` namespace (`eligibility-api`, `claims-processor`, `provider-directory`, `postgres-claims-db`, `redis-session-cache`) and `aegisops-system` (`kube-state-metrics`).
- **Observability Plane**: OTel Collector (`55317/55318`), Prometheus (`59090`), Alertmanager (`59093`), Langfuse (`53000`), `kube-state-metrics` (`58084`).
- **Identity Plane**: Keycloak `26.0` (`58080`, realm `aegisops`, S256 PKCE client `aegisops-console`).
- **Local AI Plane**: Ollama (`127.0.0.1:11434`, `nomic-embed-text:latest` 768-dim, `llama3.2:3b`).

## 2. Implemented Component & Data-Flow Diagram
```mermaid
flowchart LR
    subgraph Kind["kind-aegisops-local (aegisops-healthcare)"]
        E["eligibility-api (:58081)"]
        C["claims-processor (:58082)"]
        P["provider-directory (:58083)"]
        PGD["postgres-claims-db"]
        RDD["redis-session-cache"]
        E --> PGD
        E --> RDD
        C --> PGD
        C --> E
        P --> RDD
    end
    subgraph Obs["Observability (Compose)"]
        OTEL["OTel Collector"]
        PROM["Prometheus (:59090)"]
        AM["Alertmanager (:59093)"]
        LF["Langfuse (:53000)"]
    end
    subgraph CP["AegisOps Control Plane"]
        API["FastAPI API (:58000)"]
        SCRUB["PHI/PII Scrubber"]
        DB[("Postgres + pgvector (:55432)")]
        RED[("Redis Locks (:56379)")]
        WRK["Durable Outbox Worker & Watchdog"]
        OLL["Ollama (:11434)"]
        KC["Keycloak OIDC (:58080)"]
        UI["React Console (:55173)"]
    end
    E & C & P --> OTEL
    PROM -->|scrape| E & C & P & API
    PROM --> AM -->|authenticated webhook| API
    API --> SCRUB --> DB
    WRK <--> DB & RED & OLL
    WRK -->|K8s SDK| Kind
    WRK --> LF
    UI <-->|PKCE| KC
    UI <-->|REST + SSE| API
```
