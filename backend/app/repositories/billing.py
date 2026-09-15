from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin import BillingPlan
from app.db.models.billing import BillingPayment, BillingSettings


class BillingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, payment: BillingPayment) -> None:
        self.session.add(payment)

    def add_plan(self, plan: BillingPlan) -> None:
        self.session.add(plan)

    def add_settings(self, settings: BillingSettings) -> None:
        self.session.add(settings)

    async def get_settings(self, *, for_update: bool = False) -> BillingSettings | None:
        stmt = select(BillingSettings).where(BillingSettings.id == 1)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_plan_by_code(self, code: str) -> BillingPlan | None:
        result = await self.session.execute(
            select(BillingPlan).where(BillingPlan.code == code, BillingPlan.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_plan(self, plan_id: UUID) -> BillingPlan | None:
        return await self.session.get(BillingPlan, plan_id)

    async def get_plan_by_code(self, code: str) -> BillingPlan | None:
        result = await self.session.execute(select(BillingPlan).where(BillingPlan.code == code))
        return result.scalar_one_or_none()

    async def list_plans(self, *, active_only: bool = False) -> list[BillingPlan]:
        stmt = select(BillingPlan)
        if active_only:
            stmt = stmt.where(BillingPlan.is_active.is_(True))
        result = await self.session.execute(
            stmt.order_by(BillingPlan.sort_order.asc(), BillingPlan.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_recent_unresolved_create_for_update(
        self,
        *,
        user_id: UUID,
        package_code: str,
        receipt_email: str | None,
        since: datetime,
    ) -> BillingPayment | None:
        result = await self.session.execute(
            select(BillingPayment)
            .where(
                BillingPayment.user_id == user_id,
                BillingPayment.package_code == package_code,
                BillingPayment.receipt_email == receipt_email,
                BillingPayment.yookassa_payment_id.is_(None),
                BillingPayment.status.in_(["creating", "uncertain"]),
                BillingPayment.created_at >= since,
            )
            .order_by(BillingPayment.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_owned(self, payment_id: UUID, user_id: UUID) -> BillingPayment | None:
        result = await self.session.execute(
            select(BillingPayment).where(
                BillingPayment.id == payment_id,
                BillingPayment.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_payment(self, payment_id: UUID) -> BillingPayment | None:
        return await self.session.get(BillingPayment, payment_id)

    async def get_payment_for_update(self, payment_id: UUID) -> BillingPayment | None:
        result = await self.session.execute(
            select(BillingPayment).where(BillingPayment.id == payment_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def has_provider_payment(self, provider_id: str) -> bool:
        result = await self.session.execute(
            select(exists().where(BillingPayment.yookassa_payment_id == provider_id))
        )
        return bool(result.scalar())

    async def has_provider_refund(self, refund_id: str) -> bool:
        result = await self.session.execute(
            select(exists().where(BillingPayment.refund_id == refund_id))
        )
        return bool(result.scalar())

    async def get_by_provider_id_for_update(self, provider_id: str) -> BillingPayment | None:
        result = await self.session.execute(
            select(BillingPayment)
            .where(BillingPayment.yookassa_payment_id == provider_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_refund_id_for_update(self, refund_id: str) -> BillingPayment | None:
        result = await self.session.execute(
            select(BillingPayment)
            .where(BillingPayment.refund_id == refund_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, payment_id: UUID) -> BillingPayment | None:
        result = await self.session.execute(
            select(BillingPayment).where(BillingPayment.id == payment_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_owned(self, user_id: UUID, *, limit: int = 20) -> list[BillingPayment]:
        result = await self.session.execute(
            select(BillingPayment)
            .where(BillingPayment.user_id == user_id)
            .order_by(BillingPayment.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_all_payments(self, *, limit: int = 200) -> list[BillingPayment]:
        result = await self.session.execute(
            select(BillingPayment).order_by(BillingPayment.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
