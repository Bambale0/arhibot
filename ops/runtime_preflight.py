#!/usr/bin/env python3
"""Validate production runtime configuration without printing secret values."""

from __future__ import annotations

import stat
import sys
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_ACCESS_SECRET = "local-only-change-me-access-secret-32-bytes"
DEFAULT_REFRESH_SECRET = "local-only-change-me-refresh-secret-32-bytes"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _is_https(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


def validate(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    app_env = values.get("APP_ENV", "").strip().lower()
    if app_env != "production":
        errors.append("APP_ENV must be production on the public runtime")

    access = values.get("JWT_SECRET", "")
    refresh = values.get("REFRESH_TOKEN_SECRET", "")
    if not access or access == DEFAULT_ACCESS_SECRET or len(access) < 32:
        errors.append("JWT_SECRET must be an explicit secret with at least 32 characters")
    if not refresh or refresh == DEFAULT_REFRESH_SECRET or len(refresh) < 32:
        errors.append("REFRESH_TOKEN_SECRET must be an explicit secret with at least 32 characters")
    if access and refresh and access == refresh:
        errors.append("JWT_SECRET and REFRESH_TOKEN_SECRET must be different")

    media_signing = values.get("MEDIA_SIGNING_SECRET", "").strip()
    if not media_signing or len(media_signing) < 32:
        errors.append("MEDIA_SIGNING_SECRET must be an explicit secret with at least 32 characters")
    elif media_signing in {access, refresh}:
        errors.append("MEDIA_SIGNING_SECRET must be independent from auth secrets")

    for name in ("MEDIA_PUBLIC_BASE_URL", "NEXUS_BASE_URL", "TELEGRAM_WEBAPP_URL"):
        value = values.get(name, "").strip()
        if value and not _is_https(value):
            errors.append(f"{name} must use HTTPS on the public runtime")

    cors = [item.strip() for item in values.get("CORS_ORIGINS", "").split(",") if item.strip()]
    local_origins = [item for item in cors if "localhost" in item or "127.0.0.1" in item]
    if local_origins:
        errors.append("CORS_ORIGINS must not include localhost/127.0.0.1 on the public runtime")
    return errors


def validate_file_permissions(path: Path) -> list[str]:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        return ["runtime .env must not be readable or writable by group/others"]
    return []


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: runtime_preflight.py /path/to/.env", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print("runtime preflight failed: env file is missing", file=sys.stderr)
        return 1
    errors = [*validate_file_permissions(path), *validate(load_env(path))]
    if errors:
        print("AuRoom runtime preflight: FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("AuRoom runtime preflight: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
