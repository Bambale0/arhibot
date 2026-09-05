from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin import (
    AdminAuditLog,
    BroadcastCampaign,
    GenerationPromptTemplate,
    GenerationRuntimeSettings,
    IdeaTemplate,
)
from app.db.models.users import AuthIdentity, User
from app.domain.users.enums import AuthProvider, UserStatus


class AdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add_idea(self, idea: IdeaTemplate) -> None:
        self.session.add(idea)

    async def list_ideas(self, *, active_only: bool = False) -> list[IdeaTemplate]:
        stmt = select(IdeaTemplate)
        if active_only:
            stmt = stmt.where(IdeaTemplate.is_active.is_(True))
        result = await self.session.execute(
            stmt.order_by(IdeaTemplate.sort_order.asc(), IdeaTemplate.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_idea(self, idea_id: UUID) -> IdeaTemplate | None:
        return await self.session.get(IdeaTemplate, idea_id)

    async def get_generation_settings(self, *, for_update: bool = False) -> GenerationRuntimeSettings | None:
        stmt = select(GenerationRuntimeSettings).where(GenerationRuntimeSettings.id == 1)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def add_generation_settings(self, settings: GenerationRuntimeSettings) -> None:
        self.session.add(settings)

    async def list_prompt_templates(self) -> list[GenerationPromptTemplate]:
        result = await self.session.execute(
            select(GenerationPromptTemplate).order_by(GenerationPromptTemplate.generation_type.asc())
        )
        return list(result.scalars().all())

    async def get_prompt_template(
        self, generation_type: str, *, for_update: bool = False
    ) -> GenerationPromptTemplate | None:
        stmt = select(GenerationPromptTemplate).where(
            GenerationPromptTemplate.generation_type == generation_type
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def add_prompt_template(self, template: GenerationPromptTemplate) -> None:
        self.session.add(template)

    async def list_users(self, *, limit: int = 200) -> list[User]:
        result = await self.session.execute(
            select(User).order_by(User.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_user_for_update(self, user_id: UUID) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    def add_broadcast(self, campaign: BroadcastCampaign) -> None:
        self.session.add(campaign)

    async def list_broadcasts(self, *, limit: int = 100) -> list[BroadcastCampaign]:
        result = await self.session.execute(
            select(BroadcastCampaign).order_by(BroadcastCampaign.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_broadcast(self, campaign_id: UUID, *, for_update: bool = False) -> BroadcastCampaign | None:
        stmt = select(BroadcastCampaign).where(BroadcastCampaign.id == campaign_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_telegram_ids(self) -> list[str]:
        rows = await self.session.execute(
            select(AuthIdentity.provider_user_id)
            .join(User, User.id == AuthIdentity.user_id)
            .where(
                AuthIdentity.provider == AuthProvider.TELEGRAM,
                User.status == UserStatus.ACTIVE,
            )
            .order_by(AuthIdentity.created_at.asc())
        )
        return [value for value in rows.scalars().all() if value]

    def add_audit(
        self,
        *,
        actor_user_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        details: dict | None = None,
    ) -> AdminAuditLog:
        row = AdminAuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )
        self.session.add(row)
        return row

    async def list_audit(self, *, limit: int = 200) -> list[AdminAuditLog]:
        result = await self.session.execute(
            select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
