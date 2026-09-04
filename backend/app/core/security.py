from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings
from app.core.errors import AppError

password_hasher = PasswordHasher()
DUMMY_PASSWORD_HASH = password_hasher.hash("dummy-password-never-used")


@dataclass(frozen=True, slots=True)
class TelegramIdentityData:
    provider_user_id: str
    display_name: str
    auth_date: datetime


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: UUID, settings: Settings) -> tuple[str, int]:
    now = datetime.now(UTC)
    expires_in = settings.access_token_ttl_seconds
    payload = {
        "sub": str(user_id),
        "typ": "access",
        "jti": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str, settings: Settings) -> UUID:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "typ", "exp", "iat", "jti"]},
        )
        if payload.get("typ") != "access":
            raise jwt.InvalidTokenError("Unexpected token type")
        return UUID(str(payload["sub"]))
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise AppError(
            type="invalid_access_token",
            title="Invalid access token",
            status=401,
            detail="The access token is invalid or expired.",
        ) from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str, settings: Settings) -> str:
    return hmac.new(
        settings.refresh_token_secret.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_telegram_init_data(init_data: str, settings: Settings) -> TelegramIdentityData:
    if not settings.telegram_bot_token:
        raise AppError(
            type="telegram_auth_unavailable",
            title="Telegram authentication unavailable",
            status=503,
            detail="Telegram authentication is not configured on this environment.",
        )

    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    values = dict(pairs)
    if len(values) != len(pairs):
        raise _invalid_telegram_data("Telegram initData contains duplicate fields.")
    received_hash = values.pop("hash", None)
    if not received_hash:
        raise _invalid_telegram_data("Telegram initData does not contain a signature hash.")

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(
        b"WebAppData",
        settings.telegram_bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise _invalid_telegram_data("Telegram initData signature is invalid.")

    try:
        auth_date = datetime.fromtimestamp(int(values["auth_date"]), tz=UTC)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise _invalid_telegram_data("Telegram initData auth_date is invalid.") from exc

    now = datetime.now(UTC)
    if auth_date > now + timedelta(seconds=30):
        raise _invalid_telegram_data("Telegram initData auth_date is in the future.")
    if now - auth_date > timedelta(seconds=settings.telegram_init_data_ttl_seconds):
        raise _invalid_telegram_data("Telegram initData has expired.")

    try:
        user_data = json.loads(values["user"])
        telegram_user_id = str(int(user_data["id"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise _invalid_telegram_data("Telegram initData user payload is invalid.") from exc

    first_name = str(user_data.get("first_name") or "").strip()
    last_name = str(user_data.get("last_name") or "").strip()
    username = str(user_data.get("username") or "").strip()
    display_name = " ".join(part for part in (first_name, last_name) if part)
    if not display_name:
        display_name = f"@{username}" if username else f"Telegram user {telegram_user_id}"

    return TelegramIdentityData(
        provider_user_id=telegram_user_id,
        display_name=display_name[:120],
        auth_date=auth_date,
    )


def _invalid_telegram_data(detail: str) -> AppError:
    return AppError(
        type="telegram_auth_invalid",
        title="Invalid Telegram authentication data",
        status=401,
        detail=detail,
    )
