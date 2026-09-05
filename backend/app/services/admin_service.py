from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.admin import BillingPlan, BroadcastCampaign, GenerationPromptTemplate, GenerationRuntimeSettings, IdeaTemplate
from app.db.models.users import User
from app.domain.generations.enums import GenerationType
from app.domain.users.enums import UserRole
from app.repositories.admin import AdminRepository
from app.repositories.billing import BillingRepository
from app.schemas.admin import (
    AdminOverviewResponse,
    AdminPaymentResponse,
    AdminUserResponse,
    AuditLogResponse,
    BillingPlanCreate,
    BillingPlanResponse,
    BillingPlanUpdate,
    BroadcastCreate,
    BroadcastResponse,
    CreditAdjustmentRequest,
    GenerationRuntimeResponse,
    GenerationRuntimeUpdate,
    IdeaCreate,
    IdeaResponse,
    IdeaUpdate,
    PromptTemplateResponse,
    PromptTemplateUpdate,
    PublicIdeaResponse,
    UserStateUpdate,
)
from app.services.billing_service import BillingService
from app.telegram_bot.broadcast import send_broadcast
from app.telegram_bot.main import TelegramBotApi


class AdminService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = AdminRepository(session)
        self.billing_repository = BillingRepository(session)

    def overview(self) -> AdminOverviewResponse:
        return AdminOverviewResponse(
            yookassa_configured=bool(
                (self.settings.yookassa_shop_id or "").strip()
                and (self.settings.yookassa_secret_key or "").strip()
            ),
            nexus_configured=bool((self.settings.nexus_api_key or "").strip()),
            telegram_configured=bool((self.settings.telegram_bot_token or "").strip()),
        )

    @staticmethod
    def plan_response(plan: BillingPlan) -> BillingPlanResponse:
        return BillingPlanResponse(
            id=plan.id,
            code=plan.code,
            name=plan.name,
            description=plan.description,
            credits=plan.credits,
            amount=plan.amount_value,
            currency=plan.currency,
            is_active=plan.is_active,
            sort_order=plan.sort_order,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    async def list_plans(self) -> list[BillingPlanResponse]:
        return [self.plan_response(item) for item in await self.billing_repository.list_plans()]

    async def create_plan(self, actor: User, payload: BillingPlanCreate) -> BillingPlanResponse:
        if await self.billing_repository.get_plan_by_code(payload.code):
            raise AppError(
                type="billing_plan_code_conflict",
                title="Billing plan code already exists",
                status=409,
                detail="Choose another tariff code.",
            )
        plan = BillingPlan(
            code=payload.code,
            name=payload.name.strip(),
            description=payload.description.strip() if payload.description else None,
            credits=payload.credits,
            amount_value=Decimal(payload.amount).quantize(Decimal("0.01")),
            currency=payload.currency,
            is_active=payload.is_active,
            sort_order=payload.sort_order,
        )
        self.billing_repository.add_plan(plan)
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="tariff.create",
            entity_type="billing_plan",
            entity_id=str(plan.id),
            details={"code": plan.code},
        )
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                type="billing_plan_code_conflict",
                title="Billing plan code already exists",
                status=409,
                detail="Choose another tariff code.",
            ) from exc
        await self.session.refresh(plan)
        return self.plan_response(plan)

    async def update_plan(self, actor: User, plan_id: UUID, payload: BillingPlanUpdate) -> BillingPlanResponse:
        plan = await self.billing_repository.get_plan(plan_id)
        if plan is None:
            raise AppError(type="billing_plan_not_found", title="Tariff not found", status=404, detail="Tariff does not exist.")
        changes = payload.model_dump(exclude_unset=True)
        if "amount" in changes:
            plan.amount_value = Decimal(changes.pop("amount")).quantize(Decimal("0.01"))
        for key, value in changes.items():
            if key == "name" and value is not None:
                value = value.strip()
            if key == "description" and value is not None:
                value = value.strip() or None
            setattr(plan, key, value)
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="tariff.update",
            entity_type="billing_plan",
            entity_id=str(plan.id),
            details={"fields": sorted(payload.model_fields_set)},
        )
        await self.session.commit()
        await self.session.refresh(plan)
        return self.plan_response(plan)

    async def archive_plan(self, actor: User, plan_id: UUID) -> BillingPlanResponse:
        return await self.update_plan(actor, plan_id, BillingPlanUpdate(is_active=False))

    @staticmethod
    def idea_response(idea: IdeaTemplate) -> IdeaResponse:
        return IdeaResponse(
            id=idea.id,
            title=idea.title,
            category=idea.category,
            text=idea.text,
            generation_type=GenerationType(idea.generation_type),
            prompt=idea.prompt,
            is_active=idea.is_active,
            sort_order=idea.sort_order,
            created_at=idea.created_at,
            updated_at=idea.updated_at,
        )

    async def list_ideas(self) -> list[IdeaResponse]:
        return [self.idea_response(item) for item in await self.repository.list_ideas()]

    async def list_public_ideas(self) -> list[PublicIdeaResponse]:
        return [
            PublicIdeaResponse(
                id=item.id,
                title=item.title,
                category=item.category,
                text=item.text,
                generation_type=GenerationType(item.generation_type),
                prompt=item.prompt,
            )
            for item in await self.repository.list_ideas(active_only=True)
        ]

    async def create_idea(self, actor: User, payload: IdeaCreate) -> IdeaResponse:
        idea = IdeaTemplate(
            title=payload.title.strip(),
            category=payload.category.strip(),
            text=payload.text.strip(),
            generation_type=payload.generation_type.value,
            prompt=payload.prompt.strip(),
            is_active=payload.is_active,
            sort_order=payload.sort_order,
        )
        self.repository.add_idea(idea)
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="idea.create",
            entity_type="idea",
            entity_id=str(idea.id),
            details={"generation_type": idea.generation_type},
        )
        await self.session.commit()
        await self.session.refresh(idea)
        return self.idea_response(idea)

    async def update_idea(self, actor: User, idea_id: UUID, payload: IdeaUpdate) -> IdeaResponse:
        idea = await self.repository.get_idea(idea_id)
        if idea is None:
            raise AppError(type="idea_not_found", title="Idea not found", status=404, detail="Idea does not exist.")
        changes = payload.model_dump(exclude_unset=True)
        generation_type = changes.pop("generation_type", None)
        if generation_type is not None:
            idea.generation_type = generation_type.value
        for key, value in changes.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(idea, key, value)
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="idea.update",
            entity_type="idea",
            entity_id=str(idea.id),
            details={"fields": sorted(payload.model_fields_set)},
        )
        await self.session.commit()
        await self.session.refresh(idea)
        return self.idea_response(idea)

    async def archive_idea(self, actor: User, idea_id: UUID) -> IdeaResponse:
        return await self.update_idea(actor, idea_id, IdeaUpdate(is_active=False))

    async def get_generation_settings(self) -> GenerationRuntimeResponse:
        row = await self.repository.get_generation_settings()
        if row is None:
            raise AppError(
                type="generation_settings_missing",
                title="Generation settings missing",
                status=503,
                detail="Generation runtime settings have not been configured.",
            )
        return GenerationRuntimeResponse(
            primary_model=row.primary_model,
            fallback_model=row.fallback_model,
            primary_params=row.primary_params or {},
            fallback_params=row.fallback_params or {},
            mode_params=row.mode_params or {},
            updated_at=row.updated_at,
        )

    async def update_generation_settings(
        self, actor: User, payload: GenerationRuntimeUpdate
    ) -> GenerationRuntimeResponse:
        row = await self.repository.get_generation_settings(for_update=True)
        if row is None:
            row = GenerationRuntimeSettings(id=1, primary_model=payload.primary_model)
            self.repository.add_generation_settings(row)
        row.primary_model = payload.primary_model
        row.fallback_model = payload.fallback_model
        row.primary_params = payload.primary_params
        row.fallback_params = payload.fallback_params
        row.mode_params = payload.mode_params
        row.updated_by_user_id = actor.id
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="generation.settings.update",
            entity_type="generation_settings",
            entity_id="1",
        )
        await self.session.commit()
        await self.session.refresh(row)
        return await self.get_generation_settings()

    async def list_prompts(self) -> list[PromptTemplateResponse]:
        rows = await self.repository.list_prompt_templates()
        return [
            PromptTemplateResponse(
                generation_type=GenerationType(row.generation_type),
                template=row.template,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def update_prompt(
        self, actor: User, generation_type: GenerationType, payload: PromptTemplateUpdate
    ) -> PromptTemplateResponse:
        row = await self.repository.get_prompt_template(generation_type.value, for_update=True)
        if row is None:
            row = GenerationPromptTemplate(
                generation_type=generation_type.value,
                template=payload.template,
                updated_by_user_id=actor.id,
            )
            self.repository.add_prompt_template(row)
        else:
            row.template = payload.template
            row.updated_by_user_id = actor.id
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="generation.prompt.update",
            entity_type="generation_prompt",
            entity_id=generation_type.value,
        )
        await self.session.commit()
        await self.session.refresh(row)
        return PromptTemplateResponse(
            generation_type=generation_type,
            template=row.template,
            updated_at=row.updated_at,
        )

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

    async def list_users(self) -> list[AdminUserResponse]:
        return [self.user_response(item) for item in await self.repository.list_users()]

    async def adjust_credits(
        self, actor: User, user_id: UUID, payload: CreditAdjustmentRequest
    ) -> AdminUserResponse:
        target = await self.repository.get_user_for_update(user_id)
        if target is None:
            raise AppError(type="user_not_found", title="User not found", status=404, detail="User does not exist.")
        new_balance = target.credits_balance + payload.delta
        if new_balance < 0:
            raise AppError(
                type="insufficient_credits",
                title="Insufficient credits",
                status=409,
                detail="Credit adjustment would make the balance negative.",
            )
        target.credits_balance = new_balance
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="user.credits.adjust",
            entity_type="user",
            entity_id=str(target.id),
            details={"delta": payload.delta, "reason": payload.reason, "new_balance": new_balance},
        )
        await self.session.commit()
        await self.session.refresh(target)
        return self.user_response(target)

    async def update_user_state(
        self, actor: User, user_id: UUID, payload: UserStateUpdate
    ) -> AdminUserResponse:
        target = await self.repository.get_user_for_update(user_id)
        if target is None:
            raise AppError(type="user_not_found", title="User not found", status=404, detail="User does not exist.")
        if target.role == UserRole.SUPERADMIN and actor.role != UserRole.SUPERADMIN:
            raise AppError(type="superadmin_required", title="Superadmin required", status=403, detail="Only a superadmin can modify a superadmin account.")
        if payload.role is not None:
            if actor.role != UserRole.SUPERADMIN:
                raise AppError(type="superadmin_required", title="Superadmin required", status=403, detail="Only a superadmin can change user roles.")
            if actor.id == target.id and payload.role != UserRole.SUPERADMIN:
                raise AppError(type="cannot_demote_self", title="Cannot demote current superadmin", status=409, detail="Use another superadmin to change this role.")
            target.role = payload.role
        if payload.status is not None:
            if actor.id == target.id and payload.status.value != "active":
                raise AppError(type="cannot_disable_self", title="Cannot disable current account", status=409, detail="Use another admin account.")
            target.status = payload.status
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="user.state.update",
            entity_type="user",
            entity_id=str(target.id),
            details={"fields": sorted(payload.model_fields_set)},
        )
        await self.session.commit()
        await self.session.refresh(target)
        return self.user_response(target)

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
            provider_error=payment.provider_error,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
            paid_at=payment.paid_at,
        )

    async def list_payments(self) -> list[AdminPaymentResponse]:
        return [self.payment_response(item) for item in await self.billing_repository.list_all_payments()]

    async def reconcile_payment(self, actor: User, payment_id: UUID) -> AdminPaymentResponse:
        payment = await self.billing_repository.get_payment(payment_id)
        if payment is None:
            raise AppError(type="billing_payment_not_found", title="Payment not found", status=404, detail="Payment does not exist.")
        if payment.yookassa_payment_id:
            service = BillingService(self.session, self.settings)
            await service.sync_payment(payment)
            payment = await self.billing_repository.get_payment(payment_id) or payment
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="payment.reconcile",
            entity_type="billing_payment",
            entity_id=str(payment.id),
        )
        await self.session.commit()
        return self.payment_response(payment)

    @staticmethod
    def broadcast_response(item: BroadcastCampaign) -> BroadcastResponse:
        return BroadcastResponse(
            id=item.id,
            text=item.text,
            status=item.status,
            recipient_count=item.recipient_count,
            sent_count=item.sent_count,
            failed_count=item.failed_count,
            created_at=item.created_at,
            updated_at=item.updated_at,
            sent_at=item.sent_at,
        )

    async def list_broadcasts(self) -> list[BroadcastResponse]:
        return [self.broadcast_response(item) for item in await self.repository.list_broadcasts()]

    async def create_broadcast(self, actor: User, payload: BroadcastCreate) -> BroadcastResponse:
        campaign = BroadcastCampaign(created_by_user_id=actor.id, text=payload.text.strip())
        self.repository.add_broadcast(campaign)
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="broadcast.create",
            entity_type="broadcast",
            entity_id=str(campaign.id),
        )
        await self.session.commit()
        await self.session.refresh(campaign)
        return self.broadcast_response(campaign)

    async def send_broadcast(self, actor: User, campaign_id: UUID) -> BroadcastResponse:
        campaign = await self.repository.get_broadcast(campaign_id, for_update=True)
        if campaign is None:
            raise AppError(type="broadcast_not_found", title="Broadcast not found", status=404, detail="Broadcast does not exist.")
        if campaign.status == "sent":
            return self.broadcast_response(campaign)
        token = (self.settings.telegram_bot_token or "").strip()
        if not token:
            raise AppError(type="telegram_not_configured", title="Telegram not configured", status=503, detail="Telegram bot token is not configured.")
        recipients = await self.repository.list_active_telegram_ids()
        campaign.status = "sending"
        campaign.recipient_count = len(recipients)
        await self.session.commit()

        sent, failed = await asyncio.to_thread(send_broadcast, TelegramBotApi(token), recipients, campaign.text)

        campaign = await self.repository.get_broadcast(campaign_id, for_update=True) or campaign
        campaign.sent_count = sent
        campaign.failed_count = failed
        campaign.status = "sent" if failed == 0 else "partial"
        campaign.sent_at = datetime.now(UTC)
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="broadcast.send",
            entity_type="broadcast",
            entity_id=str(campaign.id),
            details={"recipients": len(recipients), "sent": sent, "failed": failed},
        )
        await self.session.commit()
        await self.session.refresh(campaign)
        return self.broadcast_response(campaign)

    async def list_audit(self) -> list[AuditLogResponse]:
        return [
            AuditLogResponse(
                id=row.id,
                actor_user_id=row.actor_user_id,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                details=row.details or {},
                created_at=row.created_at,
            )
            for row in await self.repository.list_audit()
        ]
