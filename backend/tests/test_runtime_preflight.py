from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _module():
    path = Path(__file__).parents[2] / "ops" / "runtime_preflight.py"
    spec = spec_from_file_location("runtime_preflight", path)
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_env() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "JWT_SECRET": "access-secret-that-is-long-enough-and-random-001",
        "REFRESH_TOKEN_SECRET": "refresh-secret-that-is-long-enough-and-random-002",
        "MEDIA_SIGNING_SECRET": "media-secret-that-is-long-enough-and-random-003",
        "MEDIA_PUBLIC_BASE_URL": "https://app.example.test",
        "NEXUS_BASE_URL": "https://nexus.example.test",
        "TELEGRAM_WEBAPP_URL": "https://app.example.test",
        "CORS_ORIGINS": "https://app.example.test",
    }


def test_runtime_preflight_accepts_hardened_public_environment() -> None:
    module = _module()
    assert module.validate(valid_env()) == []


def test_runtime_preflight_rejects_local_mode_and_default_secrets() -> None:
    module = _module()
    values = valid_env()
    values.update(
        APP_ENV="local",
        JWT_SECRET=module.DEFAULT_ACCESS_SECRET,
        REFRESH_TOKEN_SECRET=module.DEFAULT_REFRESH_SECRET,
    )
    errors = module.validate(values)
    assert any("APP_ENV" in error for error in errors)
    assert any("JWT_SECRET" in error for error in errors)
    assert any("REFRESH_TOKEN_SECRET" in error for error in errors)


def test_runtime_preflight_rejects_localhost_cors() -> None:
    module = _module()
    values = valid_env()
    values["CORS_ORIGINS"] = "https://app.example.test,http://localhost:5173"
    assert any("CORS_ORIGINS" in error for error in module.validate(values))


def test_runtime_preflight_rejects_group_or_world_readable_env(tmp_path) -> None:
    module = _module()
    env_file = tmp_path / ".env"
    env_file.write_text("APP_ENV=production\n", encoding="utf-8")
    env_file.chmod(0o644)
    assert module.validate_file_permissions(env_file)
    env_file.chmod(0o600)
    assert module.validate_file_permissions(env_file) == []
