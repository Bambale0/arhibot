from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.credits import CreditTransaction
from app.repositories.credits import CreditRepository


class CreditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = CreditRepository(session)

    async def apply(
        self,
        *,
        user_id: UUID,
        amount: int,
        kind: str,
        idempotency_key: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        reason: str | None = None,
        actor_user_id: UUID | None = None,
    ) -> CreditTransaction:
        if amount == 0:
            raise ValueError("Credit transaction amount must not be zero")

        # Serialize all movements for one balance first. This also makes an
        # idempotency replay safe when duplicate webhooks arrive concurrently.
        user = await self.repository.get_user_for_update(user_id)
        if user is None:
            raise AppError(
                type="user_not_found",
                title="User not found",
                status=404,
                detail="User does not exist.",
            )

        existing = await self.repository.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return existing

        balance_after = user.credits_balance + amount
        if balance_after < 0:
            raise AppError(
                type="insufficient_credits",
                title="Insufficient credits",
                status=409,
                detail="Not enough AuRoom credits for this operation.",
            )

        user.credits_balance = balance_after
        transaction = CreditTransaction(
            user_id=user_id,
            amount=amount,
            balance_after=balance_after,
            kind=kind,
            reference_type=reference_type,
            reference_id=reference_id,
            reason=reason,
            idempotency_key=idempotency_key,
            actor_user_id=actor_user_id,
        )
        self.repository.add_transaction(transaction)
        await self.session.flush()
        return transaction

    async def list_for_user(self, user_id: UUID, *, limit: int = 50) -> list[CreditTransaction]:
        return await self.repository.list_transactions(user_id=user_id, limit=limit)
