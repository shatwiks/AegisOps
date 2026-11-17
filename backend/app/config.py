"""Validated configuration settings for AegisOps control plane."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_SECRET_MARKERS = ("change_me", "placeholder", "example", "changeme")


def _validate_non_placeholder_secret(value: str, field_name: str, min_length: int = 16) -> str:
    stripped = value.strip()
    if len(stripped) < min_length:
        raise ValueError(f"{field_name} must be at least {min_length} characters long")
    lower = stripped.lower()
    for marker in _FORBIDDEN_SECRET_MARKERS:
        if marker in lower:
            raise ValueError(f"{field_name} cannot contain placeholder marker '{marker}'")
    return stripped


class Settings(BaseSettings):
    """Application settings loaded from environment and `.env`."""

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    aegisops_env: Literal["development", "test", "staging"] = "development"
    aegisops_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    aegisops_api_host: str = "127.0.0.1"
    aegisops_api_port: int = Field(default=58000, ge=1024, le=65535)
    aegisops_frontend_origin: str = "http://127.0.0.1:55173"
    aegisops_cors_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:55173", "http://localhost:55173"]
    )

    # Database & Redis
    aegisops_database_url: str = Field(min_length=12)
    aegisops_redis_url: str = Field(min_length=8)
    aegisops_lock_ttl_ms: int = Field(default=30_000, ge=5_000, le=300_000)

    # Security & Cryptography
    aegisops_webhook_hmac_secret: str
    aegisops_webhook_bearer_token: str
    aegisops_totp_encryption_key: str
    aegisops_session_secret: str
    aegisops_webhook_max_bytes: int = Field(default=262_144, ge=1024, le=5_242_880)
    aegisops_webhook_rate_limit_per_min: int = Field(default=120, ge=1, le=10_000)

    # Local Ollama AI
    aegisops_ollama_base_url: str = "http://127.0.0.1:11434"
    aegisops_embedding_model: str = "nomic-embed-text:latest"
    aegisops_embedding_model_digest: str = (
        "sha256:0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f"
    )
    aegisops_embedding_dimensions: int = Field(default=768, ge=1, le=4096)
    aegisops_chat_model: str = "llama3.2:3b"
    aegisops_similarity_threshold: float = Field(default=0.78, gt=0.0, le=1.0)
    aegisops_ollama_timeout_seconds: float = Field(default=45.0, ge=1.0, le=300.0)

    # Kubernetes Allowlist
    aegisops_k8s_context: str = "kind-aegisops-local"
    aegisops_k8s_allowed_contexts: list[str] = Field(
        default_factory=lambda: ["kind-aegisops-local"]
    )
    aegisops_k8s_allowed_namespaces: list[str] = Field(
        default_factory=lambda: ["aegisops-healthcare"]
    )
    aegisops_k8s_dry_run: bool = False

    # Watchdog & Telemetry
    aegisops_recovery_window_seconds: int = Field(default=60, ge=5, le=600)
    aegisops_recovery_poll_interval_seconds: int = Field(default=5, ge=1, le=60)
    aegisops_prometheus_url: str = "http://127.0.0.1:59090"

    # Identity (Keycloak OIDC)
    aegisops_oidc_issuer: str = "http://127.0.0.1:58080/realms/aegisops"
    aegisops_oidc_jwks_url: str = (
        "http://127.0.0.1:58080/realms/aegisops/protocol/openid-connect/certs"
    )
    aegisops_oidc_token_url: str = (
        "http://127.0.0.1:58080/realms/aegisops/protocol/openid-connect/token"
    )
    aegisops_oidc_client_id: str = "aegisops-console"
    aegisops_oidc_audience: str = "aegisops-api"
    aegisops_auth_required: bool = True

    # Langfuse (optional local LLM telemetry)
    aegisops_langfuse_enabled: bool = False
    langfuse_host: str = "http://127.0.0.1:53000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # Demo workload fault injection token (dev/test Chaos Lab only)
    demo_internal_fault_token: str = ""

    @field_validator("aegisops_cors_origins")
    @classmethod
    def _reject_wildcard_cors(cls, origins: list[str]) -> list[str]:
        if any(origin.strip() == "*" for origin in origins):
            raise ValueError("Wildcard '*' CORS origin is disallowed when credentials are used")
        return [o.strip().rstrip("/") for o in origins if o.strip()]

    @field_validator("aegisops_database_url")
    @classmethod
    def _validate_database_url(cls, url: str) -> str:
        if not url.startswith(("postgresql+asyncpg://", "postgresql://")):
            raise ValueError(
                "AEGISOPS_DATABASE_URL must use postgresql+asyncpg:// or postgresql://"
            )
        if "change_me" in url.lower():
            raise ValueError("AEGISOPS_DATABASE_URL cannot contain placeholder credentials")
        return url

    @field_validator("aegisops_redis_url")
    @classmethod
    def _validate_redis_url(cls, url: str) -> str:
        if not url.startswith(("redis://", "rediss://")):
            raise ValueError("AEGISOPS_REDIS_URL must start with redis:// or rediss://")
        return url

    @field_validator("aegisops_webhook_hmac_secret")
    @classmethod
    def _validate_webhook_hmac(cls, v: str) -> str:
        return _validate_non_placeholder_secret(v, "AEGISOPS_WEBHOOK_HMAC_SECRET", min_length=16)

    @field_validator("aegisops_webhook_bearer_token")
    @classmethod
    def _validate_webhook_bearer(cls, v: str) -> str:
        return _validate_non_placeholder_secret(v, "AEGISOPS_WEBHOOK_BEARER_TOKEN", min_length=16)

    @field_validator("aegisops_session_secret")
    @classmethod
    def _validate_session_secret(cls, v: str) -> str:
        return _validate_non_placeholder_secret(v, "AEGISOPS_SESSION_SECRET", min_length=24)

    @field_validator("aegisops_totp_encryption_key")
    @classmethod
    def _validate_fernet_key(cls, v: str) -> str:
        cleaned = _validate_non_placeholder_secret(v, "AEGISOPS_TOTP_ENCRYPTION_KEY", min_length=32)
        try:
            Fernet(cleaned.encode("utf-8"))
        except Exception as exc:
            raise ValueError(
                "AEGISOPS_TOTP_ENCRYPTION_KEY must be a valid URL-safe base64 32-byte Fernet key"
            ) from exc
        return cleaned

    @field_validator("aegisops_embedding_dimensions")
    @classmethod
    def _validate_vector_dimensions(cls, v: int) -> int:
        if v != 768:
            raise ValueError(
                f"AEGISOPS_EMBEDDING_DIMENSIONS={v} mismatches pgvector schema VECTOR(768); "
                "update migration schema or use nomic-embed-text (768 dims)"
            )
        return v

    @model_validator(mode="after")
    def _validate_cross_fields(self) -> Settings:
        if self.aegisops_k8s_context not in self.aegisops_k8s_allowed_contexts:
            raise ValueError(
                f"AEGISOPS_K8S_CONTEXT '{self.aegisops_k8s_context}' is not in "
                f"AEGISOPS_K8S_ALLOWED_CONTEXTS {self.aegisops_k8s_allowed_contexts}"
            )
        if not self.aegisops_k8s_allowed_namespaces:
            raise ValueError("AEGISOPS_K8S_ALLOWED_NAMESPACES cannot be empty")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached validated Settings instance."""
    return Settings()  # type: ignore[call-arg]
