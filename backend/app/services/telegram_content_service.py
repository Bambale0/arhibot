from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.telegram import TelegramContentSettings
from app.db.models.users import User
from app.repositories.admin import AdminRepository
from app.repositories.telegram import TelegramContentRepository
from app.schemas.telegram import TelegramContentResponse, TelegramContentUpdate


class TelegramContentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = TelegramContentRepository(session)
        self.audit = AdminRepository(session)

    @staticmethod
    def response(row: TelegramContentSettings | None) -> TelegramContentResponse:
        fields = (
            "bot_name",
            "short_description",
            "description",
            "start_text",
            "open_button_text",
            "start_command_description",
            "app_command_description",
        )
        configured = bool(row and all((getattr(row, field) or "").strip() for field in fields))
        return TelegramContentResponse(
            configured=configured,
            bot_name=row.bot_name if row else None,
            short_description=row.short_description if row else None,
            description=row.description if row else None,
            start_text=row.start_text if row else None,
            open_button_text=row.open_button_text if row else None,
            start_command_description=row.start_command_description if row else None,
            app_command_description=row.app_command_description if row else None,
            updated_at=row.updated_at if row else None,
        )

    async def get(self) -> TelegramContentResponse:
        return self.response(await self.repository.get())

    async def update(self, actor: User, payload: TelegramContentUpdate) -> TelegramContentResponse:
        row = await self.repository.get(for_update=True)
        if row is None:
            row = TelegramContentSettings(id=1)
            self.repository.add(row)
        for field, value in payload.model_dump().items():
            setattr(row, field, value)
        row.updated_by_user_id = actor.id
        self.audit.add_audit(
            actor_user_id=actor.id,
            action="telegram.content.update",
            entity_type="telegram_content_settings",
            entity_id="1",
            details={"fields": sorted(payload.model_fields_set)},
        )
        await self.session.commit()
        await self.session.refresh(row)
        return self.response(row)
