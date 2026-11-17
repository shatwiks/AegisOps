"""Fernet-encrypted TOTP enrollment, narrow time-window validation, rate limit, and replay protection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pyotp
from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.entities import UserTotpSecret


def _fernet(settings: Settings) -> Fernet:
    return Fernet(settings.aegisops_totp_encryption_key.encode("utf-8"))


async def enroll_user_totp(
    session: AsyncSession,
    *,
    user_sub: str,
    user_email: str,
    settings: Settings,
) -> dict[str, str]:
    """Generate a fresh 160-bit base32 secret, encrypt at rest, and return otpauth URI."""
    secret = pyotp.random_base32(32)
    encrypted = _fernet(settings).encrypt(secret.encode("utf-8")).decode("utf-8")
    now = datetime.now(UTC)

    row = (
        await session.execute(
            select(UserTotpSecret).where(UserTotpSecret.user_sub == user_sub).with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        row = UserTotpSecret(
            user_sub=user_sub,
            user_email=user_email,
            encrypted_secret=encrypted,
            enrolled_at=now,
            is_verified=False,
            last_used_timecode=0,
            failed_attempts=0,
            locked_until=None,
        )
        session.add(row)
    else:
        row.user_email = user_email
        row.encrypted_secret = encrypted
        row.enrolled_at = now
        row.is_verified = False
        row.last_used_timecode = 0
        row.failed_attempts = 0
        row.locked_until = None

    await session.flush()
    uri = pyotp.TOTP(secret).provisioning_uri(name=user_email, issuer_name="AegisOps")
    return {"provisioning_uri": uri, "secret_mask": f"{secret[:4]}...{secret[-4:]}"}


async def verify_and_consume_totp(
    session: AsyncSession,
    *,
    user_sub: str,
    otp_code: str,
    settings: Settings,
    activate_enrollment: bool = False,
) -> int:
    """Verify OTP within valid_window=1, enforce rate-limit lockout, and atomically block replay."""
    now = datetime.now(UTC)
    row = (
        await session.execute(
            select(UserTotpSecret).where(UserTotpSecret.user_sub == user_sub).with_for_update()
        )
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="TOTP MFA is not enrolled for this user",
        )

    if not activate_enrollment and not row.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="TOTP enrollment has not been verified yet",
        )

    if row.locked_until is not None and row.locked_until > now:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed TOTP attempts; try again later",
        )

    cleaned_otp = otp_code.strip()
    if not cleaned_otp.isdigit() or len(cleaned_otp) != 6:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OTP must be a 6-digit code",
        )

    secret = _fernet(settings).decrypt(row.encrypted_secret.encode("utf-8")).decode("utf-8")
    totp = pyotp.TOTP(secret)
    matched_timecode = totp.verify_and_get_timecode(cleaned_otp, valid_window=1)

    if matched_timecode is False:
        row.failed_attempts += 1
        if row.failed_attempts >= 5:
            row.locked_until = now + timedelta(minutes=5)
        await session.flush()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid TOTP code",
        )

    # Replay protection: reject any timecode <= last_used_timecode
    if matched_timecode <= row.last_used_timecode:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOTP code already used (replay rejected); wait for next 30s window",
        )

    row.last_used_timecode = int(matched_timecode)
    row.failed_attempts = 0
    row.locked_until = None
    if activate_enrollment:
        row.is_verified = True
    await session.flush()
    return int(matched_timecode)
