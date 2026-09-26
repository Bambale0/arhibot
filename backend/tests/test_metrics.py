from __future__ import annotations

from app.core.metrics import (
    metrics_payload,
    observe_http_request,
    record_generation_quality_retry_success,
    record_interior_request_blocked,
    record_masked_edit_boundary_failure,
    record_masked_edit_quality_rejected,
    record_masked_edit_retry,
    record_masked_edit_started,
)


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


def test_exterior_refinement_metrics_are_exported() -> None:
    record_masked_edit_started()
    record_masked_edit_boundary_failure()
    record_masked_edit_retry()
    record_generation_quality_retry_success()
    record_masked_edit_quality_rejected()
    record_interior_request_blocked()

    payload, _ = metrics_payload()
    rendered = payload.decode("utf-8")

    for metric in (
        "auroom_masked_edit_total",
        "auroom_masked_edit_boundary_failure_total",
        "auroom_masked_edit_retry_total",
        "auroom_generation_quality_retry_success_total",
        "auroom_masked_edit_quality_rejected_total",
        "auroom_interior_request_blocked_total",
    ):
        assert metric in rendered
