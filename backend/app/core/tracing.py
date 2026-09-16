from __future__ import annotations

import logging
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from app.core.config import Settings
from app.version import __version__

logger = logging.getLogger(__name__)
_provider: TracerProvider | None = None
_instrumented = False


def _safe_url(raw: object) -> str | None:
    if raw is None:
        return None
    try:
        parsed = urlsplit(str(raw))
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


def _httpx_request_hook(span, request_info) -> None:
    if span is None or not span.is_recording():
        return
    safe = _safe_url(getattr(request_info, "url", None))
    if safe:
        # Overwrite URL attributes with a query-free value. Signed media links and
        # provider query tokens must never be retained in telemetry.
        span.set_attribute("url.full", safe)
        span.set_attribute("http.url", safe)


def _redis_request_hook(span, _instance, args, _kwargs) -> None:
    if span is None or not span.is_recording():
        return
    command = "UNKNOWN"
    if args:
        raw = str(args[0]).strip()
        if raw:
            command = raw.split(maxsplit=1)[0].upper()
    # Redis instrumentation may otherwise retain command arguments. Keep only
    # the operation name so queue IDs, auth material, or payloads never enter traces.
    span.set_attribute("db.statement", command)
    span.set_attribute("db.operation.name", command)


def configure_tracing(settings: Settings, *, app: FastAPI | None = None) -> bool:
    global _provider, _instrumented
    if not settings.otel_traces_enabled:
        return False

    if _provider is None:
        service_role = settings.runtime_role.replace("_", "-")
        resource = Resource.create(
            {
                "service.name": f"auroom-{service_role}",
                "service.namespace": "AuRoom",
                "service.version": __version__,
                "deployment.environment.name": settings.app_env,
                "auroom.release_sha": settings.release_sha[:64] or "unknown",
            }
        )
        provider = TracerProvider(
            resource=resource,
            sampler=ParentBased(TraceIdRatioBased(settings.otel_trace_sample_ratio)),
        )
        exporter = OTLPSpanExporter(
            endpoint=settings.otel_exporter_otlp_traces_endpoint,
            timeout=2.0,
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                exporter,
                max_queue_size=2048,
                schedule_delay_millis=1000,
                max_export_batch_size=256,
                export_timeout_millis=2000,
            )
        )
        trace.set_tracer_provider(provider)
        _provider = provider

    if not _instrumented:
        HTTPXClientInstrumentor().instrument(
            tracer_provider=_provider,
            request_hook=_httpx_request_hook,
        )
        SQLAlchemyInstrumentor().instrument(tracer_provider=_provider)
        RedisInstrumentor().instrument(
            tracer_provider=_provider,
            request_hook=_redis_request_hook,
        )
        _instrumented = True

    if app is not None:
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=_provider,
            excluded_urls=r"/metrics,/health/live,/health/ready,/api/v1/media/.*",
        )

    logger.info(
        "OpenTelemetry tracing configured",
        extra={
            "operation": "tracing.configure",
            "dependency": "jaeger",
        },
    )
    return True


def get_tracer(name: str):
    return trace.get_tracer(name)


def current_trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return f"{context.trace_id:032x}"


def shutdown_tracing() -> None:
    global _provider
    if _provider is None:
        return
    try:
        _provider.shutdown()
    except Exception:
        logger.exception("OpenTelemetry tracing shutdown failed")
    finally:
        _provider = None
