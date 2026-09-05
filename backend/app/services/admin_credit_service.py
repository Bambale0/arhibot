from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.credits import CreditTransaction, GenerationCreditPrice
from app.db.models.users import User
from app.domain.generations.enums import GenerationType
from app.repositories.credits import CreditRepository
from app.schemas.admin import (
    AdminUserResponse,
    CreditAdjustmentRequest,
    CreditTransactionResponse,
    GenerationPriceResponse,
    GenerationPriceUpdate,
)
from app.services.credit_service import CreditService


class AdminCreditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = CreditRepository(session)
        self.credit_service = CreditService(session)

    @staticmethod
    def price_response(row: GenerationCreditPrice) -> GenerationPriceResponse:
        return GenerationPriceResponse(
            generation_type=GenerationType(row.generation_type),
            credits=row.credits,
            is_active=row.is_active,
            updated_at=row.updated_at,
        )

    async def list_prices(self) -> list[GenerationPriceResponse]:
        return [self.price_response(row) for row in await self.repository.list_prices()]

    async def update_price(
        self,
        actor: User,
        generation_type: GenerationType,
        payload: GenerationPriceUpdate,
    ) -> GenerationPriceResponse:
        row = await self.repository.get_price(generation_type.value)
        if row is None:
            row = GenerationCreditPrice(
                generation_type=generation_type.value,
                credits=payload.credits,
                is_active=payload.is_active,
                updated_by_user_id=actor.id,
            )
            self.repository.add_price(row)
        else:
            row.credits = payload.credits
            row.is_active = payload.is_active
            row.updated_by_user_id = actor.id
        await self.session.commit()
        await self.session.refresh(row)
        return self.price_response(row)

    @staticmethod
    def transaction_response(row: CreditTransaction) -> CreditTransactionResponse:
        return CreditTransactionResponse(
            id=row.id,
            user_id=row.user_id,
            amount=row.amount,
            balance_after=row.balance_after,
            kind=row.kind,
            reference_type=row.reference_type,
            reference_id=row.reference_id,
            reason=row.reason,
            actor_user_id=row.actor_user_id,
            created_at=row.created_at,
        )

    async def list_transactions(
        self,
        *,
        user_id: UUID | None = None,
        limit: int = 200,
    ) -> list[CreditTransactionResponse]:
        rows = await self.repository.list_transactions(user_id=user_id, limit=limit)
        return [self.transaction_response(row) for row in rows]

    @staticmethod
    def user_response(user: User) -> AdminUserResponse:
        return AdminUserResponse(
            id=user.id,
            display_name=user.display_name,
            status=user.status,
            role=user.role,
            credits_balance=user.credits_balance,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    async def adjust_credits(
        self,
        actor: User,
        user_id: UUID,
        payload: CreditAdjustmentRequest,
    ) -> AdminUserResponse:
        await self.credit_service.apply(
            user_id=user_id,
            amount=payload.delta,
            kind="admin_adjustment",
            idempotency_key=f"admin-adjustment:{uuid4()}",
            reference_type="user",
            reference_id=str(user_id),
            reason=payload.reason.strip(),
            actor_user_id=actor.id,
        )
        await self.session.commit()
        user = await self.session.get(User, user_id)
        if user is None:
            raise AppError(
                type="user_not_found",
                title="User not found",
                status=404,
                detail="User does not exist.",
            )
        return self.user_response(user)
