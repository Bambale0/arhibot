"""Safe classification: never authorize provider replay from ambiguous checkpoints."""

import pytest

from app.workers.reconciliation_triage import (
    audit_stale_generations,
    classify_pending_reconciliation,
)


@pytest.mark.parametrize(
    ("report", "provider_task_present", "expected"),
    [
        (
            {
                "requires_reconciliation": True,
                "video_request": {
                    "state": "prepared",
                    "client_request_id": "sensitive-test-value",
                    "request_body": "sensitive-test-prompt",
                },
            },
            False,
            "operator_required_video_create_outcome_unknown",
        ),
        (
            {
                "requires_reconciliation": True,
                "video_request": {"state": "accepted", "request_id": "task-private"},
            },
            True,
            "provider_accepted_check_resume_policy",
        ),
        (
            {
                "requires_reconciliation": True,
                "video_identity_request": {"state": "submitted"},
            },
            False,
            "operator_required_identity_outcome_unknown",
        ),
        (
            {"requires_reconciliation": True},
            False,
            "operator_required_provider_outcome_unknown",
        ),
        ({}, True, "provider_task_present_check_worker"),
        ({}, False, "stale_without_reconciliation_check_queue"),
        (None, False, "stale_without_reconciliation_check_queue"),
    ],
)
def test_classify_pending_reconciliation(report, provider_task_present, expected):
    classification = classify_pending_reconciliation(report, provider_task_present)
    assert classification == expected
    assert "sensitive" not in classification
    assert "task-private" not in classification


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("min_age_minutes", "limit"),
    [(0, 100), (525601, 100), (10, 0), (10, 10001)],
)
async def test_invalid_query_bounds_fail_before_accessing_database(min_age_minutes, limit):
    with pytest.raises(ValueError):
        await audit_stale_generations(min_age_minutes=min_age_minutes, limit=limit)
