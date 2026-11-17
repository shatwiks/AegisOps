"""OIDC PKCE exchange, session inspection, logout, and TOTP enrollment routes."""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.oidc import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    AuthenticatedUser,
    OIDCVerifier,
    authenticate_request,
    exchange_pkce_code,
    require_role,
    sign_session_cookie,
)
from app.auth.totp import enroll_user_totp, verify_and_consume_totp
from app.config import Settings
from app.models.entities import UserTotpSecret

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class PkceExchangeRequest(BaseModel):
    code: str = Field(min_length=4)
    code_verifier: str = Field(min_length=32)
    redirect_uri: str = Field(min_length=8)
    nonce: str | None = None


class TotpVerifyRequest(BaseModel):
    otp_code: str = Field(min_length=6, max_length=6)


@router.get("/config")
async def auth_public_config(request: Request) -> dict[str, str]:
    """Expose public OIDC issuer and client ID for browser PKCE flow."""
    settings: Settings = request.app.state.settings
    return {
        "issuer": settings.aegisops_oidc_issuer,
        "client_id": settings.aegisops_oidc_client_id,
        "authorization_endpoint": f"{settings.aegisops_oidc_issuer}/protocol/openid-connect/auth",
        "end_session_endpoint": f"{settings.aegisops_oidc_issuer}/protocol/openid-connect/logout",
    }


@router.post("/oidc/exchange")
async def oidc_pkce_exchange(
    body: PkceExchangeRequest,
    request: Request,
    response: Response,
) -> dict[str, Any]:
    """Exchange PKCE code at Keycloak, validate ID & access tokens, set HttpOnly session cookie."""
    settings: Settings = request.app.state.settings
    verifier: OIDCVerifier = request.app.state.oidc_verifier

    tokens = await exchange_pkce_code(
        code=body.code,
        code_verifier=body.code_verifier,
        redirect_uri=body.redirect_uri,
        settings=settings,
    )
    access_token = str(tokens.get("access_token", ""))
    id_token = str(tokens.get("id_token", ""))

    if id_token:
        verifier.verify_id_token(id_token, nonce=body.nonce)
    user = verifier.verify_access_token(access_token)

    cookie_val = sign_session_cookie(user, settings)
    csrf_val = secrets.token_urlsafe(24)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_val,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=1800,
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_val,
        httponly=False,
        samesite="lax",
        secure=False,
        max_age=1800,
        path="/",
    )
    return {
        "authenticated": True,
        "sub": user.sub,
        "email": user.email,
        "roles": sorted(user.roles),
        "highest_role": user.highest_role,
        "csrf_token": csrf_val,
    }


@router.get("/me")
async def auth_me(request: Request) -> dict[str, Any]:
    """Return server-derived authenticated user identity and TOTP enrollment status."""
    user = authenticate_request(request, enforce_csrf=False)
    totp_enrolled = False
    totp_verified = False
    async with request.app.state.session_factory() as session:
        row = (
            await session.execute(select(UserTotpSecret).where(UserTotpSecret.user_sub == user.sub))
        ).scalar_one_or_none()
        if row is not None:
            totp_enrolled = True
            totp_verified = bool(row.is_verified)

    return {
        "sub": user.sub,
        "email": user.email,
        "roles": sorted(user.roles),
        "highest_role": user.highest_role,
        "auth_method": user.auth_method,
        "totp_enrolled": totp_enrolled,
        "totp_verified": totp_verified,
    }


@router.post("/logout")
async def auth_logout(request: Request, response: Response) -> dict[str, bool]:
    """Clear session and CSRF cookies (CSRF enforced if authenticated via cookie)."""
    authenticate_request(request, enforce_csrf=True)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    return {"logged_out": True}


@router.post("/totp/enroll")
async def totp_enroll(
    request: Request,
    user: AuthenticatedUser = Depends(require_role("approver")),
) -> dict[str, str]:
    """Provision encrypted per-user TOTP seed and otpauth provisioning URI."""
    settings: Settings = request.app.state.settings
    async with request.app.state.session_factory() as session, session.begin():
        return await enroll_user_totp(
            session, user_sub=user.sub, user_email=user.email, settings=settings
        )


@router.post("/totp/verify-enrollment")
async def totp_verify_enrollment(
    body: TotpVerifyRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_role("approver")),
) -> dict[str, Any]:
    """Verify initial TOTP code and mark enrollment active."""
    settings: Settings = request.app.state.settings
    async with request.app.state.session_factory() as session, session.begin():
        timecode = await verify_and_consume_totp(
            session,
            user_sub=user.sub,
            otp_code=body.otp_code,
            settings=settings,
            activate_enrollment=True,
        )
    return {"totp_verified": True, "timecode": timecode}
