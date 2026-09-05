from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.admin import BillingPlan
from app.db.models.billing import BillingPayment
from app.db.models.users import User
from app.providers.yookassa import YooKassaError, YooKassaPayment, YooKassaProvider
from app.repositories.billing import BillingRepository
from app.schemas.billing import BillingPackageResponse, BillingPaymentResponse, BillingSummaryResponse
from app.services.credit_service import CreditService


class BillingService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = BillingRepository(session)

    @property
    def provider_configured(self) -> bool:
        return bool(
            (self.settings.yookassa_shop_id or "").strip()
            and (self.settings.yookassa_secret_key or "").strip()
        )

    @staticmethod
    def _package_response(plan: BillingPlan) -> BillingPackageResponse:
        return BillingPackageResponse(
            code=plan.code,
            label=plan.name,
            credits=plan.credits,
            amount=plan.amount_value,
            currency=plan.currency,
        )

    @staticmethod
    def _payment_response(payment: BillingPayment) -> BillingPaymentResponse:
        return BillingPaymentResponse(
            id=payment.id,
            package_code=payment.package_code,
            credits=payment.credits,
            amount=payment.amount_value,
            currency=payment.currency,
            status=payment.status,
            confirmation_url=payment.confirmation_url,
            created_at=payment.created_at,
            paid_at=payment.paid_at,
        )

    async def summary(self, user: User) -> BillingSummaryResponse:
        payments = await self.repository.list_owned(user.id)
        plans = await self.repository.list_plans(active_only=True)
        return BillingSummaryResponse(
            enabled=self.provider_configured and bool(plans),
            credits_balance=user.credits_balance,
            packages=[self._package_response(item) for item in plans],
            payments=[self._payment_response(item) for item in payments],
        )

    async def create_payment(self, user: User, package_code: str) -> BillingPaymentResponse:
        if not self.provider_configured:
            raise AppError(
                type="billing_not_configured",
                title="Billing is not configured",
                status=503,
                detail="YooKassa credentials are not configured.",
            )
        package = await self.repository.get_active_plan_by_code(package_code)
        if package is None:
            raise AppError(
                type="billing_package_not_found",
                title="Billing package not found",
                status=404,
                detail="The selected billing package is not available.",
            )

        local_id = uuid4()
        idempotence_key = str(uuid4())
        payment = BillingPayment(
            id=local_id,
            user_id=user.id,
            package_code=package.code,
            credits=package.credits,
            amount_value=Decimal(package.amount_value).quantize(Decimal("0.01")),
            currency=package.currency,
            status="creating",
            idempotence_key=idempotence_key,
        )
        self.repository.add(payment)
        await self.session.commit()

        return_url = (
            (self.settings.yookassa_return_url or "").strip()
            or (self.settings.telegram_webapp_url or "").strip()
        )
        if not return_url:
            payment.status = "failed"
            payment.provider_error = "YooKassa return URL is not configured"
            await self.session.commit()
            raise AppError(
                type="billing_not_configured",
                title="Billing is not configured",
                status=503,
                detail="YooKassa return URL is not configured.",
            )

        separator = "&" if "?" in return_url else "?"
        return_url = f"{return_url}{separator}billing=return&payment_id={payment.id}"
        provider = YooKassaProvider(self.settings)
        try:
            remote = await provider.create_payment(
                amount=payment.amount_value,
                currency=payment.currency,
                description=f"AuRoom: {package.name}",
                return_url=return_url,
                metadata={
                    "billing_payment_id": str(payment.id),
                    "user_id": str(user.id),
                    "package_code": package.code,
                },
                idempotence_key=idempotence_key,
            )
        except YooKassaError as exc:
            payment.status = "failed"
            payment.provider_error = str(exc)[:1000]
            await self.session.commit()
            raise AppError(
                type="payment_provider_unavailable",
                title="Payment provider unavailable",
                status=502,
                detail="YooKassa could not create the payment. Please try again.",
            ) from exc

        payment.yookassa_payment_id = remote.id
        payment.status = remote.status
        payment.confirmation_url = remote.confirmation_url
        payment.provider_error = None
        await self.session.commit()
        await self.session.refresh(payment)
        return self._payment_response(payment)

    async def get_owned_and_sync(self, user: User, payment_id: UUID) -> BillingPaymentResponse:
        payment = await self.repository.get_owned(payment_id, user.id)
        if payment is None:
            raise AppError(
                type="billing_payment_not_found",
                title="Payment not found",
                status=404,
                detail="The payment does not exist or belongs to another user.",
            )
        if (
            payment.yookassa_payment_id
            and payment.status not in {"succeeded", "canceled", "failed"}
            and self.provider_configured
        ):
            await self.sync_payment(payment)
            payment = await self.repository.get_owned(payment.id, user.id) or payment
        return self._payment_response(payment)

    async def sync_payment(self, payment: BillingPayment) -> None:
        if not payment.yookassa_payment_id or not self.provider_configured:
            return
        remote = await YooKassaProvider(self.settings).get_payment(payment.yookassa_payment_id)
        await self.apply_remote(remote, expected_local_id=payment.id)

    async def apply_remote(self, remote: YooKassaPayment, *, expected_local_id: UUID | None = None) -> None:
        local_id_raw = remote.metadata.get("billing_payment_id")
        local_id: UUID | None = expected_local_id
        if local_id is None and local_id_raw:
            try:
                local_id = UUID(local_id_raw)
            except ValueError:
                local_id = None

        payment = await self.repository.get_by_provider_id_for_update(remote.id)
        if payment is None and local_id is not None:
            payment = await self.repository.get_by_id_for_update(local_id)
        if payment is None:
            return

        if payment.yookassa_payment_id and payment.yookassa_payment_id != remote.id:
            raise YooKassaError("YooKassa payment id does not match local payment")
        if remote.amount != payment.amount_value or remote.currency != payment.currency:
            raise YooKassaError("YooKassa payment amount does not match local payment")
        if remote.metadata.get("user_id") != str(payment.user_id):
            raise YooKassaError("YooKassa payment user metadata does not match")
        if remote.metadata.get("package_code") != payment.package_code:
            raise YooKassaError("YooKassa payment package metadata does not match")

        payment.yookassa_payment_id = remote.id
        payment.provider_error = None
        if remote.status == "succeeded":
            if payment.status != "succeeded":
                await CreditService(self.session).apply(
                    user_id=payment.user_id,
                    amount=payment.credits,
                    kind="payment_credit",
                    idempotency_key=f"payment:{payment.id}:credit",
                    reference_type="billing_payment",
                    reference_id=str(payment.id),
                    reason=f"YooKassa payment {payment.package_code}",
                )
                payment.status = "succeeded"
                payment.paid_at = datetime.now(UTC)
        elif remote.status == "canceled":
            payment.status = "canceled"
        else:
            payment.status = remote.status
        await self.session.commit()

    async def handle_webhook(self, payload: dict) -> None:
        event = str(payload.get("event") or "")
        obj = payload.get("object") or {}
        provider_id = str(obj.get("id") or "").strip()
        if event not in {"payment.succeeded", "payment.canceled", "payment.waiting_for_capture"} or not provider_id:
            return
        if not self.provider_configured:
            raise YooKassaError("YooKassa webhook received while billing is not configured")
        remote = await YooKassaProvider(self.settings).get_payment(provider_id)
        await self.apply_remote(remote)


def build_billing_service(session: AsyncSession, settings: Settings) -> BillingService:
    return BillingService(session, settings)
