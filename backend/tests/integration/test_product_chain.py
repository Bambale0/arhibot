import os
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip("set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True)

from app.core.config import get_settings  # noqa: E402
from app.core.redis import redis_client  # noqa: E402
from app.db.models.users import User  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.domain.users.enums import UserRole  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.nexus import NexusImageProvider, NexusProviderError  # noqa: E402
from app.providers.yookassa import YooKassaPayment, YooKassaProvider, YooKassaRefund  # noqa: E402
from app.services.generation_service import GENERATION_QUEUE_KEY  # noqa: E402
from app.workers.generation_worker import process_generation  # noqa: E402


async def _register_admin(client: AsyncClient) -> tuple[dict, dict[str, str]]:
    email = f"product-{uuid4()}@example.com"
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "display_name": "Product Chain Admin",
        },
    )
    assert register.status_code == 201, register.text
    tokens = register.json()
    user_id = UUID(tokens["user"]["id"])
    async with get_session_factory()() as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.role = UserRole.SUPERADMIN
        await session.commit()
    return tokens, {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.mark.asyncio
async def test_generation_reserves_credit_and_refunds_technical_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tokens, headers = await _register_admin(client)
        user_id = tokens["user"]["id"]

        runtime = await client.put(
            "/api/v1/admin/generation",
            headers=headers,
            json={
                "primary_model": "integration-image-model",
                "fallback_model": None,
                "primary_params": {},
                "fallback_params": {},
                "mode_params": {},
            },
        )
        assert runtime.status_code == 200, runtime.text
        prompt = await client.put(
            "/api/v1/admin/prompts/floor_plan",
            headers=headers,
            json={"template": "Create a floor plan. {user_prompt}"},
        )
        assert prompt.status_code == 200, prompt.text
        price = await client.put(
            "/api/v1/admin/generation-prices/floor_plan",
            headers=headers,
            json={"credits": 2, "is_active": True},
        )
        assert price.status_code == 200, price.text
        credit = await client.post(
            f"/api/v1/admin/users/{user_id}/credits",
            headers=headers,
            json={"delta": 5, "reason": "integration generation budget"},
        )
        assert credit.status_code == 200, credit.text
        assert credit.json()["credits_balance"] == 5

        ops = await client.put(
            "/api/v1/admin/operations",
            headers=headers,
            json={
                "auth_rate_limit_per_minute": None,
                "generation_rate_limit_per_minute": 50,
                "payment_rate_limit_per_minute": 20,
                "media_retention_days": 30,
                "backup_interval_hours": 24,
                "backup_retention_days": 14,
            },
        )
        assert ops.status_code == 200, ops.text
        assert ops.json()["backup_interval_hours"] == 24

        project = await client.post(
            "/api/v1/projects",
            headers=headers,
            json={"name": "Text-only floor plan", "context": {"house_area_m2": 120, "floors": 2}},
        )
        assert project.status_code == 201, project.text

        generation = await client.post(
            "/api/v1/generations",
            headers=headers,
            json={
                "project_id": project.json()["id"],
                "input_asset_id": None,
                "type": "floor_plan",
                "prompt": "Three bedrooms and a kitchen-living room",
            },
        )
        assert generation.status_code == 202, generation.text
        row = generation.json()
        assert row["credits_charged"] == 2
        assert row["input_asset_id"] is None

        me_after_reserve = await client.get("/api/v1/me", headers=headers)
        assert me_after_reserve.status_code == 200
        assert me_after_reserve.json()["credits_balance"] == 3

        async def provider_failure(self, **kwargs):  # noqa: ANN001, ARG001
            raise NexusProviderError("integration provider failure", retryable=False)

        monkeypatch.setattr(NexusImageProvider, "generate", provider_failure)
        await process_generation(UUID(row["id"]), get_settings())

        failed = await client.get(f"/api/v1/generations/{row['id']}", headers=headers)
        assert failed.status_code == 200, failed.text
        assert failed.json()["status"] == "failed"

        me_after_refund = await client.get("/api/v1/me", headers=headers)
        assert me_after_refund.json()["credits_balance"] == 5

        ledger = await client.get(
            f"/api/v1/admin/credit-transactions?user_id={user_id}&limit=50",
            headers=headers,
        )
        assert ledger.status_code == 200, ledger.text
        movements = [(item["kind"], item["amount"]) for item in ledger.json()]
        assert ("generation_reserve", -2) in movements
        assert ("generation_refund", 2) in movements

        debit = await client.post(
            f"/api/v1/admin/users/{user_id}/credits",
            headers=headers,
            json={"delta": -5, "reason": "integration zero balance"},
        )
        assert debit.status_code == 200, debit.text
        insufficient = await client.post(
            "/api/v1/generations",
            headers=headers,
            json={"project_id": project.json()["id"], "type": "floor_plan", "prompt": "retry"},
        )
        assert insufficient.status_code == 409, insufficient.text
        assert insufficient.json()["type"] == "insufficient_credits"

        await redis_client.lpop(GENERATION_QUEUE_KEY)


@pytest.mark.asyncio
async def test_yookassa_payment_webhook_credits_once_and_full_refund(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tokens, headers = await _register_admin(client)
        user_id = tokens["user"]["id"]
        plan_code = f"itest-{uuid4().hex[:10]}"
        remote_payment_id = f"pay-{uuid4().hex}"

        tariff = await client.post(
            "/api/v1/admin/tariffs",
            headers=headers,
            json={
                "code": plan_code,
                "name": "Integration pack",
                "credits": 7,
                "amount": "100.00",
                "currency": "RUB",
                "is_active": True,
                "sort_order": 0,
            },
        )
        assert tariff.status_code == 201, tariff.text

        async def create_payment(self, *, amount, currency, description, return_url, metadata, idempotence_key, receipt=None):  # noqa: ANN001, ARG001
            return YooKassaPayment(
                id=remote_payment_id,
                status="pending",
                amount=Decimal("100.00"),
                currency="RUB",
                metadata=metadata,
                confirmation_url="https://payments.example.test/confirm",
            )

        monkeypatch.setattr(YooKassaProvider, "create_payment", create_payment)
        created = await client.post(
            "/api/v1/billing/payments",
            headers=headers,
            json={"package_code": plan_code},
        )
        assert created.status_code == 201, created.text
        local_payment_id = created.json()["id"]

        succeeded_remote = YooKassaPayment(
            id=remote_payment_id,
            status="succeeded",
            amount=Decimal("100.00"),
            currency="RUB",
            metadata={
                "billing_payment_id": local_payment_id,
                "user_id": user_id,
                "package_code": plan_code,
            },
        )

        async def get_payment(self, payment_id):  # noqa: ANN001, ARG001
            return succeeded_remote

        monkeypatch.setattr(YooKassaProvider, "get_payment", get_payment)
        webhook = {"event": "payment.succeeded", "object": {"id": remote_payment_id}}
        first = await client.post("/api/v1/billing/webhooks/yookassa", json=webhook)
        assert first.status_code == 200, first.text
        second = await client.post("/api/v1/billing/webhooks/yookassa", json=webhook)
        assert second.status_code == 200, second.text

        me_paid = await client.get("/api/v1/me", headers=headers)
        assert me_paid.json()["credits_balance"] == 7

        remote_refund_id = f"refund-{uuid4().hex}"

        async def create_refund(self, *, payment_id, amount, currency, description, idempotence_key):  # noqa: ANN001, ARG001
            return YooKassaRefund(
                id=remote_refund_id,
                payment_id=remote_payment_id,
                status="succeeded",
                amount=Decimal("100.00"),
                currency="RUB",
            )

        monkeypatch.setattr(YooKassaProvider, "create_refund", create_refund)
        refunded = await client.post(
            f"/api/v1/admin/payments/{local_payment_id}/refund",
            headers=headers,
        )
        assert refunded.status_code == 200, refunded.text
        assert refunded.json()["status"] == "refunded"
        assert refunded.json()["refund_status"] == "succeeded"

        me_refunded = await client.get("/api/v1/me", headers=headers)
        assert me_refunded.json()["credits_balance"] == 0

        ledger = await client.get(
            f"/api/v1/admin/credit-transactions?user_id={user_id}&limit=50",
            headers=headers,
        )
        assert ledger.status_code == 200, ledger.text
        movements = [(item["kind"], item["amount"]) for item in ledger.json()]
        assert movements.count(("payment_credit", 7)) == 1
        assert movements.count(("payment_refund_debit", -7)) == 1
