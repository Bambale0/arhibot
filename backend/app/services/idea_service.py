from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.admin import IdeaTemplate
from app.db.models.assets import Asset
from app.db.models.users import User
from app.domain.generations.enums import GenerationType
from app.repositories.admin import AdminRepository
from app.repositories.assets import AssetRepository
from app.schemas.admin import IdeaCreate, IdeaResponse, IdeaUpdate, PublicIdeaResponse
from app.services.asset_service import LocalMediaStorage


class IdeaService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.repository = AdminRepository(session)
        self.storage = LocalMediaStorage(settings)

    async def _image_url(self, asset_id: UUID | None) -> str | None:
        if asset_id is None:
            return None
        asset = await self.session.get(Asset, asset_id)
        if asset is None or asset.deleted_at is not None:
            return None
        return self.storage.public_url(asset.storage_path)

    async def list_public(self) -> list[PublicIdeaResponse]:
        rows = await self.repository.list_ideas(active_only=True)
        return [
            PublicIdeaResponse(
                id=row.id,
                title=row.title,
                category=row.category,
                text=row.text,
                generation_type=GenerationType(row.generation_type),
                prompt=row.prompt,
                image_url=await self._image_url(row.image_asset_id),
            )
            for row in rows
        ]


class AdminIdeaService(IdeaService):
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        super().__init__(session, settings)
        self.assets = AssetRepository(session)

    async def _validate_owned_image(self, actor: User, asset_id: UUID | None) -> None:
        if asset_id is None:
            return
        asset = await self.assets.get_owned(asset_id, actor.id)
        if asset is None:
            raise AppError(
                type="idea_image_not_found",
                title="Idea image not found",
                status=404,
                detail="The selected image does not exist or is not owned by this administrator.",
            )

    async def response(self, row: IdeaTemplate) -> IdeaResponse:
        return IdeaResponse(
            id=row.id,
            title=row.title,
            category=row.category,
            text=row.text,
            generation_type=GenerationType(row.generation_type),
            prompt=row.prompt,
            image_asset_id=row.image_asset_id,
            image_url=await self._image_url(row.image_asset_id),
            is_active=row.is_active,
            sort_order=row.sort_order,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def list_all(self) -> list[IdeaResponse]:
        return [await self.response(row) for row in await self.repository.list_ideas()]

    async def create(self, actor: User, payload: IdeaCreate) -> IdeaResponse:
        await self._validate_owned_image(actor, payload.image_asset_id)
        row = IdeaTemplate(
            title=payload.title.strip(),
            category=payload.category.strip(),
            text=payload.text.strip(),
            generation_type=payload.generation_type.value,
            prompt=payload.prompt.strip(),
            image_asset_id=payload.image_asset_id,
            is_active=payload.is_active,
            sort_order=payload.sort_order,
        )
        self.repository.add_idea(row)
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="idea.create",
            entity_type="idea",
            entity_id=str(row.id),
            details={"generation_type": row.generation_type, "image_asset_id": str(row.image_asset_id) if row.image_asset_id else None},
        )
        await self.session.commit()
        await self.session.refresh(row)
        return await self.response(row)

    async def update(self, actor: User, idea_id: UUID, payload: IdeaUpdate) -> IdeaResponse:
        row = await self.repository.get_idea(idea_id)
        if row is None:
            raise AppError(
                type="idea_not_found",
                title="Idea not found",
                status=404,
                detail="Idea does not exist.",
            )
        if "image_asset_id" in payload.model_fields_set:
            await self._validate_owned_image(actor, payload.image_asset_id)
            row.image_asset_id = payload.image_asset_id
        changes = payload.model_dump(exclude_unset=True, exclude={"image_asset_id"})
        generation_type = changes.pop("generation_type", None)
        if generation_type is not None:
            row.generation_type = generation_type.value
        for key, value in changes.items():
            if isinstance(value, str):
                value = value.strip()
            setattr(row, key, value)
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="idea.update",
            entity_type="idea",
            entity_id=str(row.id),
            details={"fields": sorted(payload.model_fields_set)},
        )
        await self.session.commit()
        await self.session.refresh(row)
        return await self.response(row)

    async def archive(self, actor: User, idea_id: UUID) -> IdeaResponse:
        return await self.update(actor, idea_id, IdeaUpdate(is_active=False))
