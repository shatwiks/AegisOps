"""Keycloak OIDC RS256 token verification, PKCE exchange, RBAC, and signed session cookies."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import HTTPException, Request, status
from jwt import PyJWKClient

from app.config import Settings

ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 1,
    "operator": 2,
    "approver": 3,
}

SESSION_COOKIE_NAME = "aegisops_session"
CSRF_COOKIE_NAME = "aegisops_csrf"


@dataclass(frozen=True)
class AuthenticatedUser:
    """Verified server-derived identity and effective RBAC roles."""

    sub: str
    email: str
    roles: frozenset[str]
    highest_role: str
    auth_method: str

    def has_role(self, required_role: str) -> bool:
        req_lvl = ROLE_HIERARCHY.get(required_role, 99)
        return ROLE_HIERARCHY.get(self.highest_role, 0) >= req_lvl


def derive_roles_from_claims(claims: dict[str, Any]) -> tuple[frozenset[str], str]:
    """Derive RBAC roles strictly from validated JWT claims (never from request parameters)."""
    raw_roles: list[str] = []
    if isinstance(claims.get("roles"), list):
        raw_roles.extend(str(r) for r in claims["roles"])
    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict) and isinstance(realm_access.get("roles"), list):
        raw_roles.extend(str(r) for r in realm_access["roles"])

    valid_roles = frozenset(r for r in raw_roles if r in ROLE_HIERARCHY)
    if not valid_roles:
        return frozenset({"viewer"}), "viewer"
    highest = max(valid_roles, key=lambda r: ROLE_HIERARCHY[r])
    return valid_roles, highest


class OIDCVerifier:
    """Verifies Keycloak RS256 access tokens & ID tokens via JWKS."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._jwk_client = PyJWKClient(settings.aegisops_oidc_jwks_url, cache_keys=True)

    def verify_access_token(self, token: str) -> AuthenticatedUser:
        """Validate access token signature (RS256), issuer, audience, and expiry."""
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.settings.aegisops_oidc_issuer,
                audience=self.settings.aegisops_oidc_audience,
                options={"require": ["exp", "iat", "sub", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid or expired access token: {type(exc).__name__}",
            ) from exc

        roles, highest = derive_roles_from_claims(claims)
        return AuthenticatedUser(
            sub=str(claims["sub"]),
            email=str(claims.get("email") or claims.get("preferred_username") or claims["sub"]),
            roles=roles,
            highest_role=highest,
            auth_method="oidc-bearer",
        )

    def verify_id_token(self, id_token: str, *, nonce: str | None = None) -> dict[str, Any]:
        """Validate OIDC ID token distinctly from API access token (aud == client_id)."""
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.settings.aegisops_oidc_issuer,
                audience=self.settings.aegisops_oidc_client_id,
                options={"require": ["exp", "iat", "sub", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid OIDC ID token: {type(exc).__name__}",
            ) from exc
        if nonce is not None and claims.get("nonce") != nonce:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="OIDC ID token nonce mismatch",
            )
        return dict(claims)


async def exchange_pkce_code(
    *,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    settings: Settings,
) -> dict[str, Any]:
    """Exchange Authorization Code + PKCE code_verifier at Keycloak token endpoint."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            settings.aegisops_oidc_token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": settings.aegisops_oidc_client_id,
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OIDC PKCE exchange failed (HTTP {resp.status_code})",
        )
    return dict(resp.json())


def sign_session_cookie(
    user: AuthenticatedUser, settings: Settings, ttl_seconds: int = 1800
) -> str:
    """Create HMAC-SHA256 signed session payload for HttpOnly cookie storage."""
    payload = {
        "sub": user.sub,
        "email": user.email,
        "roles": sorted(user.roles),
        "highest_role": user.highest_role,
        "exp": int(time.time()) + ttl_seconds,
        "jti": secrets.token_hex(12),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(
        settings.aegisops_session_secret.encode("utf-8"), raw, hashlib.sha256
    ).hexdigest()
    import base64

    b64 = base64.urlsafe_b64encode(raw).decode("ascii")
    return f"{b64}.{sig}"


def verify_session_cookie(cookie_value: str, settings: Settings) -> AuthenticatedUser:
    """Verify signed HttpOnly session cookie."""
    import base64

    try:
        b64, provided_sig = cookie_value.split(".", 1)
        raw = base64.urlsafe_b64decode(b64.encode("ascii"))
        expected_sig = hmac.new(
            settings.aegisops_session_secret.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(provided_sig, expected_sig):
            raise ValueError("Signature mismatch")
        payload = json.loads(raw.decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("Session expired")
        roles = frozenset(r for r in payload.get("roles", []) if r in ROLE_HIERARCHY)
        highest = str(payload.get("highest_role", "viewer"))
        if highest not in ROLE_HIERARCHY:
            highest = "viewer"
        return AuthenticatedUser(
            sub=str(payload["sub"]),
            email=str(payload["email"]),
            roles=roles or frozenset({"viewer"}),
            highest_role=highest,
            auth_method="session-cookie",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session cookie",
        ) from exc


def authenticate_request(request: Request, *, enforce_csrf: bool = False) -> AuthenticatedUser:
    """Authenticate request via Bearer JWT or HttpOnly signed session cookie."""
    settings: Settings = request.app.state.settings
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        verifier: OIDCVerifier = request.app.state.oidc_verifier
        return verifier.verify_access_token(token)

    cookie_val = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_val:
        user = verify_session_cookie(cookie_val, settings)
        if enforce_csrf and request.method in ("POST", "PUT", "PATCH", "DELETE"):
            csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
            csrf_header = request.headers.get("X-CSRF-Token", "")
            if (
                not csrf_cookie
                or not csrf_header
                or not hmac.compare_digest(csrf_cookie, csrf_header)
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Missing or invalid CSRF token",
                )
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


def optional_authenticate_request(request: Request) -> AuthenticatedUser | None:
    """Return authenticated user when valid Bearer or session cookie is supplied; otherwise None (visitor)."""
    settings: Settings = request.app.state.settings
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        verifier: OIDCVerifier = request.app.state.oidc_verifier
        return verifier.verify_access_token(token)

    cookie_val = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_val:
        try:
            return verify_session_cookie(cookie_val, settings)
        except HTTPException:
            return None
    return None


def require_role(required_role: str) -> Any:
    """FastAPI dependency factory enforcing RBAC role & CSRF for cookie mutations."""

    async def _dependency(request: Request) -> AuthenticatedUser:
        user = authenticate_request(request, enforce_csrf=True)
        if not user.has_role(required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required; caller holds '{user.highest_role}'",
            )
        return user

    return _dependency
