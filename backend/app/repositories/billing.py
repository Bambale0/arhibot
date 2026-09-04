from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.billing import BillingPayment


class BillingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, payment: BillingPayment) -> None:
        self.session.add(payment)

    async def get_owned(self, payment_id: UUID, user_id: UUID) -> BillingPayment | None:
        result = await self.session.execute(
            select(BillingPayment).where(
                BillingPayment.id == payment_id,
                BillingPayment.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

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
