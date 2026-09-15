import pytest
from pydantic import ValidationError

from app.api.v1.billing import _is_yookassa_webhook_ip
from app.schemas.billing import YooKassaWebhookNotification


@pytest.mark.parametrize(
    "value",
    [
        "185.71.76.1",
        "185.71.77.31",
        "77.75.153.127",
        "77.75.156.11",
        "77.75.156.35",
        "77.75.154.200",
        "2a02:5180::1",
        "::ffff:185.71.76.2",
    ],
)
def test_yookassa_webhook_accepts_official_source_ranges(value: str) -> None:
    assert _is_yookassa_webhook_ip(value)


@pytest.mark.parametrize("value", ["127.0.0.1", "8.8.8.8", "185.71.76.33", "not-an-ip"])
def test_yookassa_webhook_rejects_untrusted_sources(value: str) -> None:
    assert not _is_yookassa_webhook_ip(value)


def test_yookassa_webhook_schema_rejects_unbounded_provider_id() -> None:
    with pytest.raises(ValidationError):
        YooKassaWebhookNotification.model_validate(
            {"event": "payment.succeeded", "object": {"id": "../arbitrary/provider/path"}}
        )


def test_yookassa_webhook_schema_ignores_provider_fields_but_keeps_envelope() -> None:
    payload = YooKassaWebhookNotification.model_validate(
        {
            "type": "notification",
            "event": "payment.succeeded",
            "object": {"id": "2f123abc-def456", "status": "succeeded", "metadata": {"x": "y"}},
        }
    )
    assert payload.event == "payment.succeeded"
    assert payload.object.id == "2f123abc-def456"
