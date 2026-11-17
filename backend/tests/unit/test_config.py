"""Unit tests for Settings configuration validation."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.config import Settings


def _valid_kwargs() -> dict[str, object]:
    return {
        "aegisops_database_url": "postgresql+asyncpg://aegisops:secretpass123@127.0.0.1:55432/aegisops",
        "aegisops_redis_url": "redis://127.0.0.1:56379/0",
        "aegisops_webhook_hmac_secret": "a" * 32,
        "aegisops_webhook_bearer_token": "b" * 32,
        "aegisops_totp_encryption_key": Fernet.generate_key().decode("utf-8"),
        "aegisops_session_secret": "c" * 32,
        "_env_file": None,
    }


def test_valid_settings_succeed() -> None:
    cfg = Settings(**_valid_kwargs())  # type: ignore[arg-type]
    assert cfg.aegisops_embedding_dimensions == 768
    assert cfg.aegisops_k8s_context == "kind-aegisops-local"
    assert cfg.aegisops_recovery_window_seconds == 60


@pytest.mark.parametrize(
    "override",
    [
        {"aegisops_webhook_hmac_secret": "CHANGE_ME_SECRET_VALUE"},
        {"aegisops_webhook_bearer_token": "short"},
        {"aegisops_totp_encryption_key": "not-a-valid-fernet-key-at-all-123456"},
        {"aegisops_session_secret": "placeholder_secret_1234567890"},
        {"aegisops_embedding_dimensions": 1536},
        {"aegisops_k8s_context": "prod-cluster-unauthorized"},
        {"aegisops_cors_origins": ["*"]},
        {"aegisops_database_url": "sqlite:///local.db"},
        {"aegisops_recovery_window_seconds": 1},
    ],
)
def test_invalid_settings_rejected(override: dict[str, object]) -> None:
    kwargs = _valid_kwargs()
    kwargs.update(override)
    with pytest.raises(ValidationError):
        Settings(**kwargs)  # type: ignore[arg-type]
