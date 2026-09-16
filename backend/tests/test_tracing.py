from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.tracing import _redis_request_hook, _safe_url, current_trace_id


@dataclass
class _RecordingSpan:
    attributes: dict[str, object]

    def is_recording(self) -> bool:
        return True

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


def test_trace_url_sanitizer_drops_query_fragment_and_credentials() -> None:
    assert (
        _safe_url("https://user:secret@example.test:8443/media/file.png?expires=1&sig=secret#x")
        == "https://example.test:8443/media/file.png"
    )


def test_trace_url_sanitizer_rejects_non_http_urls() -> None:
    assert _safe_url("file:///tmp/private") is None
    assert _safe_url("redis://redis:6379/0") is None


def test_redis_trace_hook_keeps_only_command_name() -> None:
    span = _RecordingSpan(attributes={})
    _redis_request_hook(
        span,
        None,
        ("SET", "refresh-token:secret", "sensitive-value"),
        {},
    )
    assert span.attributes["db.statement"] == "SET"
    assert span.attributes["db.operation.name"] == "SET"
    rendered = repr(span.attributes)
    assert "refresh-token" not in rendered
    assert "sensitive-value" not in rendered


def test_tracing_settings_validate_ratio_and_endpoint() -> None:
    with pytest.raises(ValidationError, match="OTEL_TRACE_SAMPLE_RATIO"):
        Settings(otel_trace_sample_ratio=0)

    with pytest.raises(ValidationError, match="OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"):
        Settings(
            otel_traces_enabled=True,
            otel_exporter_otlp_traces_endpoint="not-a-url",
        )

    with pytest.raises(ValidationError, match="must not contain credentials"):
        Settings(
            otel_traces_enabled=True,
            otel_exporter_otlp_traces_endpoint="https://user:pass@example.test/v1/traces",
        )

    with pytest.raises(ValidationError, match="Production OTLP trace export must use HTTPS"):
        Settings(
            app_env="production",
            otel_traces_enabled=True,
            otel_exporter_otlp_traces_endpoint="http://example.test/v1/traces",
            jwt_secret="x" * 32,
            refresh_token_secret="y" * 32,
            media_signing_secret="z" * 32,
        )

    settings = Settings(
        app_env="production",
        otel_traces_enabled=True,
        otel_exporter_otlp_traces_endpoint="http://jaeger:4318/v1/traces",
        jwt_secret="x" * 32,
        refresh_token_secret="y" * 32,
        media_signing_secret="z" * 32,
    )
    assert settings.otel_traces_enabled is True


def test_no_active_span_has_no_trace_id() -> None:
    assert current_trace_id() is None
