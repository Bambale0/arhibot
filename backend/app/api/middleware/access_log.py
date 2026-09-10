import logging
from functools import lru_cache
from time import perf_counter

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.routing import compile_path

from app.core.metrics import observe_http_request

logger = logging.getLogger(__name__)


@lru_cache(maxsize=256)
def _path_regex(template: str):
    return compile_path(template)[0]


def _iter_route_templates(routes: list[object], prefix: str = ""):
    for route in routes:
        original_router = getattr(route, "original_router", None)
        include_context = getattr(route, "include_context", None)
        if original_router is not None and include_context is not None:
            child_prefix = prefix + str(getattr(include_context, "prefix", "") or "")
            yield from _iter_route_templates(list(original_router.routes), child_prefix)
            continue

        path = getattr(route, "path", None)
        if path is None:
            continue
        methods = getattr(route, "methods", None)
        yield prefix + str(path), methods


def _route_template(request: Request) -> str:
    request_path = request.scope.get("path", request.url.path)
    request_method = request.method.upper()
    for template, methods in _iter_route_templates(list(request.app.routes)):
        if methods and request_method not in methods:
            continue
        if _path_regex(template).match(request_path):
            return template or "/"
    return "__unmatched__"


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = perf_counter()
        response = await call_next(request)
        duration_seconds = perf_counter() - started
        duration_ms = round(duration_seconds * 1000, 2)
        route_template = _route_template(request)
        observe_http_request(
            method=request.method,
            route=route_template,
            status_code=response.status_code,
            duration_seconds=duration_seconds,
        )
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
