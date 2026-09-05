from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.credits import CreditTransaction, GenerationCreditPrice
from app.db.models.users import User


class CreditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_for_update(self, user_id: UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id).with_for_update())
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, key: str) -> CreditTransaction | None:
        result = await self.session.execute(
            select(CreditTransaction).where(CreditTransaction.idempotency_key == key)
        )
        return result.scalar_one_or_none()

    def add_transaction(self, transaction: CreditTransaction) -> None:
        self.session.add(transaction)

    async def list_transactions(
        self,
        *,
        user_id: UUID | None = None,
        limit: int = 100,
    ) -> list[CreditTransaction]:
        stmt = select(CreditTransaction)
        if user_id is not None:
            stmt = stmt.where(CreditTransaction.user_id == user_id)
        result = await self.session.execute(
            stmt.order_by(CreditTransaction.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_price(self, generation_type: str) -> GenerationCreditPrice | None:
        return await self.session.get(GenerationCreditPrice, generation_type)

    async def list_prices(self) -> list[GenerationCreditPrice]:
        result = await self.session.execute(
            select(GenerationCreditPrice).order_by(GenerationCreditPrice.generation_type.asc())
        )
        return list(result.scalars().all())

    def add_price(self, price: GenerationCreditPrice) -> None:
        self.session.add(price)
