from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.billing import BillingSettings
from app.db.models.users import User
from app.repositories.admin import AdminRepository
from app.repositories.billing import BillingRepository
from app.schemas.admin import AdminPaymentResponse, BillingSettingsResponse, BillingSettingsUpdate
from app.services.billing_service import BillingService


class AdminBillingService:
    def __init__(self, session: AsyncSession, settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = BillingRepository(session)
        self.audit = AdminRepository(session)

    async def get_settings(self) -> BillingSettingsResponse:
        row = await self.repository.get_settings()
        if row is None:
            return BillingSettingsResponse(
                receipts_enabled=False,
                vat_code=None,
                payment_subject=None,
                payment_mode=None,
                updated_at=None,
            )
        return BillingSettingsResponse(
            receipts_enabled=row.receipts_enabled,
            vat_code=row.vat_code,
            payment_subject=row.payment_subject,
            payment_mode=row.payment_mode,
            updated_at=row.updated_at,
        )

    async def update_settings(
        self,
        actor: User,
        payload: BillingSettingsUpdate,
    ) -> BillingSettingsResponse:
        row = await self.repository.get_settings(for_update=True)
        if row is None:
            row = BillingSettings(id=1)
            self.repository.add_settings(row)
        row.receipts_enabled = payload.receipts_enabled
        row.vat_code = payload.vat_code
        row.payment_subject = (
            payload.payment_subject.strip() if payload.payment_subject else None
        )
        row.payment_mode = payload.payment_mode.strip() if payload.payment_mode else None
        row.updated_by_user_id = actor.id
        self.audit.add_audit(
            actor_user_id=actor.id,
            action="billing.settings.update",
            entity_type="billing_settings",
            entity_id="1",
            details={"receipts_enabled": row.receipts_enabled},
        )
        await self.session.commit()
        await self.session.refresh(row)
        return await self.get_settings()

    @staticmethod
    def payment_response(payment) -> AdminPaymentResponse:
        return AdminPaymentResponse(
            id=payment.id,
            user_id=payment.user_id,
            package_code=payment.package_code,
            credits=payment.credits,
            amount=payment.amount_value,
            currency=payment.currency,
            status=payment.status,
            yookassa_payment_id=payment.yookassa_payment_id,
            receipt_email=payment.receipt_email,
            refund_id=payment.refund_id,
            refund_status=payment.refund_status,
            provider_error=payment.provider_error,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
            paid_at=payment.paid_at,
            refunded_at=payment.refunded_at,
        )

    async def list_payments(self) -> list[AdminPaymentResponse]:
        return [self.payment_response(row) for row in await self.repository.list_all_payments()]

    async def reconcile_payment(self, actor: User, payment_id: UUID) -> AdminPaymentResponse:
        payment = await self.repository.get_payment(payment_id)
        if payment is None:
            raise AppError(
                type="billing_payment_not_found",
                title="Payment not found",
                status=404,
                detail="Payment does not exist.",
            )
        billing = BillingService(self.session, self.settings)
        if payment.yookassa_payment_id:
            await billing.sync_payment(payment)
        payment = await self.repository.get_payment(payment_id) or payment
        if payment.refund_id:
            await billing.sync_refund(payment)
        payment = await self.repository.get_payment(payment_id) or payment
        self.audit.add_audit(
            actor_user_id=actor.id,
            action="payment.reconcile",
            entity_type="billing_payment",
            entity_id=str(payment.id),
        )
        await self.session.commit()
        return self.payment_response(payment)

    async def refund_payment(self, actor: User, payment_id: UUID) -> AdminPaymentResponse:
        result = await BillingService(self.session, self.settings).request_full_refund(payment_id)
        current = await self.repository.get_payment(payment_id)
        self.audit.add_audit(
            actor_user_id=actor.id,
            action="payment.refund",
            entity_type="billing_payment",
            entity_id=str(payment_id),
            details={"status": result.refund_status},
        )
        await self.session.commit()
        if current is None:
            raise RuntimeError("Refunded payment disappeared")
        return self.payment_response(current)
