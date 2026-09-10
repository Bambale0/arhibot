from __future__ import annotations

from app.core.metrics import metrics_payload, observe_http_request


def test_http_metrics_use_route_template_labels() -> None:
    observe_http_request(
        method='GET',
        route='/api/v1/projects/{project_id}',
        status_code=200,
        duration_seconds=0.123,
    )
    payload, media_type = metrics_payload()
    rendered = payload.decode('utf-8')
    assert 'auroom_http_requests_total' in rendered
    assert 'route="/api/v1/projects/{project_id}"' in rendered
    assert 'status="200"' in rendered
    assert 'text/plain' in media_type


def test_json_formatter_includes_release_sha() -> None:
    import json
    import logging

    from app.core.logging import JsonFormatter

    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello", args=(), exc_info=None
    )
    payload = json.loads(JsonFormatter("abc123").format(record))
    assert payload["release_sha"] == "abc123"
    assert payload["message"] == "hello"
