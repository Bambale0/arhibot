from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin import BillingPlan
from app.db.models.billing import BillingPayment


class BillingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, payment: BillingPayment) -> None:
        self.session.add(payment)

    def add_plan(self, plan: BillingPlan) -> None:
        self.session.add(plan)

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

    async def get_by_provider_id_for_update(self, provider_id: str) -> BillingPayment | None:
        result = await self.session.execute(
            select(BillingPayment)
            .where(BillingPayment.yookassa_payment_id == provider_id)
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
