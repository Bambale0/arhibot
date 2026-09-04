import hashlib
import hmac
import json
from datetime import UTC, datetime
from urllib.parse import urlencode
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    normalize_email,
    verify_password,
    verify_telegram_init_data,
)


def test_password_hash_is_not_plaintext_and_verifies() -> None:
    password = "correct-horse-battery-staple"
    encoded = hash_password(password)
    assert encoded != password
    assert encoded.startswith("$argon2")
    assert verify_password(password, encoded) is True
    assert verify_password("wrong-password", encoded) is False


def test_email_normalization() -> None:
    assert normalize_email("  Igor@Example.COM ") == "igor@example.com"


def test_access_token_round_trip() -> None:
    settings = Settings(
        jwt_secret="a" * 40,
        refresh_token_secret="b" * 40,
        jwt_issuer="test-issuer",
        jwt_audience="test-audience",
    )
    user_id = uuid4()
    token, expires_in = create_access_token(user_id, settings)
    assert expires_in == 900
    assert decode_access_token(token, settings) == user_id


def test_refresh_token_hash_uses_server_secret() -> None:
    token = "random-client-token"
    first = Settings(jwt_secret="a" * 40, refresh_token_secret="b" * 40)
    second = Settings(jwt_secret="a" * 40, refresh_token_secret="c" * 40)
    assert hash_refresh_token(token, first) != hash_refresh_token(token, second)


def test_valid_telegram_init_data() -> None:
    bot_token = "123456:TEST_BOT_TOKEN"
    settings = Settings(
        jwt_secret="a" * 40,
        refresh_token_secret="b" * 40,
        telegram_bot_token=bot_token,
    )
    values = {
        "auth_date": str(int(datetime.now(UTC).timestamp())),
        "query_id": "AAEAAAE",
        "user": json.dumps(
            {"id": 123456789, "first_name": "Igor", "last_name": "Test"},
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    result = verify_telegram_init_data(urlencode(values), settings)
    assert result.provider_user_id == "123456789"
    assert result.display_name == "Igor Test"


def test_invalid_telegram_signature_is_rejected() -> None:
    settings = Settings(
        jwt_secret="a" * 40,
        refresh_token_secret="b" * 40,
        telegram_bot_token="123456:TEST_BOT_TOKEN",
    )
    init_data = urlencode(
        {
            "auth_date": str(int(datetime.now(UTC).timestamp())),
            "user": json.dumps({"id": 1, "first_name": "Igor"}),
            "hash": "0" * 64,
        }
    )
    with pytest.raises(AppError) as exc_info:
        verify_telegram_init_data(init_data, settings)
    assert exc_info.value.type == "telegram_auth_invalid"
