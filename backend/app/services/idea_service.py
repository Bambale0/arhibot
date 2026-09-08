from __future__ import annotations

import asyncio
import json
import struct
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.architecture.schemas import ArchitecturePackage
from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.admin import IdeaTemplate
from app.db.models.assets import Asset
from app.db.models.projects import Project
from app.db.models.users import User
from app.domain.generations.enums import GenerationType
from app.repositories.admin import AdminRepository
from app.repositories.assets import AssetRepository
from app.repositories.projects import ProjectRepository
from app.schemas.admin import (
    IdeaCreate,
    IdeaMediaInput,
    IdeaMediaResponse,
    IdeaResponse,
    IdeaUpdate,
    PublicIdeaResponse,
)
from app.services.asset_service import LocalMediaStorage


def validate_glb(data: bytes, *, max_size_bytes: int) -> dict:
    if not data:
        raise AppError(
            type="invalid_idea_model",
            title="Invalid 3D model",
            status=422,
            detail="The uploaded GLB file is empty.",
        )
    if len(data) > max_size_bytes:
        raise AppError(
            type="idea_model_too_large",
            title="3D model is too large",
            status=413,
            detail=f"GLB model must not exceed {max_size_bytes} bytes.",
        )
    if len(data) < 20:
        raise AppError(
            type="invalid_idea_model",
            title="Invalid 3D model",
            status=422,
            detail="The file is not a valid binary glTF 2.0 model.",
        )
    try:
        magic, version, declared_length = struct.unpack_from("<4sII", data, 0)
        json_length, json_type = struct.unpack_from("<II", data, 12)
    except struct.error as exc:
        raise AppError(
            type="invalid_idea_model",
            title="Invalid 3D model",
            status=422,
            detail="The file is not a valid binary glTF 2.0 model.",
        ) from exc
    if magic != b"glTF" or version != 2 or declared_length != len(data) or json_type != 0x4E4F534A:
        raise AppError(
            type="invalid_idea_model",
            title="Invalid 3D model",
            status=422,
            detail="Only self-contained GLB models using glTF 2.0 are accepted.",
        )
    json_end = 20 + json_length
    if json_length <= 0 or json_end > len(data):
        raise AppError(
            type="invalid_idea_model",
            title="Invalid 3D model",
            status=422,
            detail="The GLB JSON chunk is invalid.",
        )
    try:
        document = json.loads(data[20:json_end].rstrip(b"\x00 \t\r\n").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError(
            type="invalid_idea_model",
            title="Invalid 3D model",
            status=422,
            detail="The GLB JSON chunk is invalid.",
        ) from exc
    asset_version = (
        str((document.get("asset") or {}).get("version", ""))
        if isinstance(document, dict)
        else ""
    )
    if not isinstance(document, dict) or not asset_version.startswith("2"):
        raise AppError(
            type="invalid_idea_model",
            title="Invalid 3D model",
            status=422,
            detail="The GLB model must declare glTF 2.x.",
        )
    for section in ("buffers", "images"):
        values = document.get(section) or []
        if not isinstance(values, list):
            raise AppError(
                type="invalid_idea_model",
                title="Invalid 3D model",
                status=422,
                detail="The GLB model structure is invalid.",
            )
        for item in values:
            if not isinstance(item, dict):
                continue
            uri = item.get("uri")
            if isinstance(uri, str) and uri and not uri.startswith("data:"):
                raise AppError(
                    type="external_idea_model_resource",
                    title="External 3D resource is not allowed",
                    status=422,
                    detail="Use a self-contained GLB with embedded geometry and textures.",
                )
    return document


class IdeaService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = AdminRepository(session)
        self.storage = LocalMediaStorage(settings)

    async def _image_url(self, asset_id: UUID | None) -> str | None:
        if asset_id is None:
            return None
        asset = await self.session.get(Asset, asset_id)
        if asset is None or asset.deleted_at is not None:
            return None
        return self.storage.public_url(asset.storage_path)

    def _model_url(self, row: IdeaTemplate) -> str | None:
        return self.storage.public_url(row.model_storage_path) if row.model_storage_path else None

    async def _media(self, raw_items: list[dict] | None) -> list[IdeaMediaResponse]:
        result: list[IdeaMediaResponse] = []
        for raw in raw_items or []:
            try:
                item = IdeaMediaInput.model_validate(raw)
            except ValidationError:
                continue
            url = await self._image_url(item.asset_id)
            if url is None:
                continue
            result.append(
                IdeaMediaResponse(
                    asset_id=item.asset_id,
                    kind=item.kind,
                    label=item.label,
                    url=url,
                )
            )
        return result

    @staticmethod
    def _architecture(raw: dict | None) -> ArchitecturePackage | None:
        if not raw:
            return None
        try:
            return ArchitecturePackage.model_validate(raw)
        except ValidationError:
            return None

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
                media=await self._media(row.media_items),
                architecture=self._architecture(row.architecture_snapshot),
                model_url=self._model_url(row),
            )
            for row in rows
        ]


class AdminIdeaService(IdeaService):
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        super().__init__(session, settings)
        self.assets = AssetRepository(session)
        self.projects = ProjectRepository(session)

    async def _validate_owned_image(self, actor: User, asset_id: UUID | None) -> Asset | None:
        if asset_id is None:
            return None
        asset = await self.assets.get_owned(asset_id, actor.id)
        if asset is None:
            raise AppError(
                type="idea_image_not_found",
                title="Idea image not found",
                status=404,
                detail="The selected image does not exist or is not owned by this administrator.",
            )
        return asset

    async def _validate_owned_media(
        self,
        actor: User,
        media: list[IdeaMediaInput],
        *,
        existing_asset_ids: set[UUID] | None = None,
    ) -> None:
        seen: set[UUID] = set()
        existing_asset_ids = existing_asset_ids or set()
        for item in media:
            if item.asset_id in seen:
                raise AppError(
                    type="duplicate_idea_media",
                    title="Duplicate idea media",
                    status=422,
                    detail="The same media asset cannot be attached to an idea twice.",
                )
            seen.add(item.asset_id)
            if item.asset_id in existing_asset_ids:
                continue
            if await self.assets.get_owned(item.asset_id, actor.id) is None:
                raise AppError(
                    type="idea_media_not_found",
                    title="Idea media not found",
                    status=404,
                    detail=(
                        "One of the selected media assets does not exist or is not owned "
                        "by this administrator."
                    ),
                )

    @staticmethod
    def _snapshot_from_project(project: Project) -> dict:
        raw = (project.context or {}).get("architecture")
        if raw is None:
            raise AppError(
                type="idea_architecture_not_configured",
                title="Architecture not configured",
                status=422,
                detail="The selected project does not have canonical architecture geometry yet.",
            )
        try:
            return ArchitecturePackage.model_validate(raw).model_dump(
                mode="json", exclude_none=True
            )
        except ValidationError as exc:
            raise AppError(
                type="idea_architecture_invalid",
                title="Architecture is invalid",
                status=422,
                detail="The selected project contains invalid canonical architecture geometry.",
            ) from exc

    async def _snapshot_for_project(self, actor: User, project_id: UUID | None) -> dict | None:
        if project_id is None:
            return None
        project = await self.projects.get_owned(project_id, actor.id)
        if project is None:
            raise AppError(
                type="idea_architecture_project_not_found",
                title="Architecture project not found",
                status=404,
                detail=(
                    "The selected 3D source project does not exist or is not owned by "
                    "this administrator."
                ),
            )
        return self._snapshot_from_project(project)

    @staticmethod
    def _stored_media_ids(raw_items: list[dict] | None) -> set[UUID]:
        result: set[UUID] = set()
        for raw in raw_items or []:
            try:
                result.add(IdeaMediaInput.model_validate(raw).asset_id)
            except ValidationError:
                continue
        return result

    async def _default_architecture_project_id(self, asset: Asset | None) -> UUID | None:
        if asset is None or asset.project_id is None:
            return None
        project = await self.session.get(Project, asset.project_id)
        if project is None or project.deleted_at is not None:
            return None
        return project.id if (project.context or {}).get("architecture") is not None else None

    @staticmethod
    def _serialize_media(media: list[IdeaMediaInput]) -> list[dict]:
        return [item.model_dump(mode="json") for item in media]

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
            architecture_project_id=row.architecture_project_id,
            media=await self._media(row.media_items),
            architecture=self._architecture(row.architecture_snapshot),
            model_url=self._model_url(row),
            model_original_filename=row.model_original_filename,
            model_size_bytes=row.model_size_bytes,
            is_active=row.is_active,
            sort_order=row.sort_order,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def list_all(self) -> list[IdeaResponse]:
        return [await self.response(row) for row in await self.repository.list_ideas()]

    async def create(self, actor: User, payload: IdeaCreate) -> IdeaResponse:
        image = await self._validate_owned_image(actor, payload.image_asset_id)
        await self._validate_owned_media(actor, payload.media)
        architecture_project_id = payload.architecture_project_id
        if architecture_project_id is None:
            architecture_project_id = await self._default_architecture_project_id(image)
        architecture_snapshot = await self._snapshot_for_project(actor, architecture_project_id)
        row = IdeaTemplate(
            title=payload.title.strip(),
            category=payload.category.strip(),
            text=payload.text.strip(),
            generation_type=payload.generation_type.value,
            prompt=payload.prompt.strip(),
            image_asset_id=payload.image_asset_id,
            media_items=self._serialize_media(payload.media),
            architecture_project_id=architecture_project_id,
            architecture_snapshot=architecture_snapshot,
            is_active=payload.is_active,
            sort_order=payload.sort_order,
        )
        self.repository.add_idea(row)
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="idea.create",
            entity_type="idea",
            entity_id=str(row.id),
            details={
                "generation_type": row.generation_type,
                "image_asset_id": str(row.image_asset_id) if row.image_asset_id else None,
                "media_count": len(payload.media),
                "architecture_project_id": (
                    str(row.architecture_project_id) if row.architecture_project_id else None
                ),
                "has_architecture": row.architecture_snapshot is not None,
            },
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
        image: Asset | None = None
        if "image_asset_id" in payload.model_fields_set:
            if payload.image_asset_id == row.image_asset_id:
                image = (
                    await self.session.get(Asset, row.image_asset_id)
                    if row.image_asset_id
                    else None
                )
            else:
                image = await self._validate_owned_image(actor, payload.image_asset_id)
                row.image_asset_id = payload.image_asset_id
        if "architecture_project_id" in payload.model_fields_set:
            requested_project_id = payload.architecture_project_id
            if requested_project_id != row.architecture_project_id:
                row.architecture_project_id = requested_project_id
                row.architecture_snapshot = await self._snapshot_for_project(
                    actor, requested_project_id
                )
            elif requested_project_id is not None:
                owned_project = await self.projects.get_owned(requested_project_id, actor.id)
                if owned_project is not None:
                    row.architecture_snapshot = self._snapshot_from_project(owned_project)
        elif "image_asset_id" in payload.model_fields_set and row.architecture_project_id is None:
            default_project_id = await self._default_architecture_project_id(image)
            row.architecture_project_id = default_project_id
            row.architecture_snapshot = await self._snapshot_for_project(actor, default_project_id)
        if "media" in payload.model_fields_set:
            media = payload.media or []
            await self._validate_owned_media(
                actor,
                media,
                existing_asset_ids=self._stored_media_ids(row.media_items),
            )
            row.media_items = self._serialize_media(media)
        changes = payload.model_dump(
            exclude_unset=True, exclude={"image_asset_id", "architecture_project_id", "media"}
        )
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

    async def upload_model(
        self,
        actor: User,
        idea_id: UUID,
        *,
        data: bytes,
        original_filename: str | None,
    ) -> IdeaResponse:
        row = await self.repository.get_idea(idea_id)
        if row is None:
            raise AppError(
                type="idea_not_found",
                title="Idea not found",
                status=404,
                detail="Idea does not exist.",
            )
        filename = (original_filename or "model.glb").strip()[:255] or "model.glb"
        if Path(filename).suffix.lower() != ".glb":
            raise AppError(
                type="unsupported_idea_model_format",
                title="Unsupported 3D model format",
                status=422,
                detail="Upload a self-contained .glb file.",
            )
        validate_glb(data, max_size_bytes=self.settings.max_model_size_bytes)
        relative_path = f"ideas/{row.id}/models/{uuid4()}.glb"
        previous_path = row.model_storage_path
        await self.storage.write(relative_path, data)
        row.model_storage_path = relative_path
        row.model_original_filename = filename
        row.model_size_bytes = len(data)
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="idea.model.upload",
            entity_type="idea",
            entity_id=str(row.id),
            details={"filename": filename, "size_bytes": len(data)},
        )
        try:
            await self.session.commit()
            await self.session.refresh(row)
        except Exception:
            await self.session.rollback()
            target = self.storage.absolute_path(relative_path)
            if target.exists():
                await asyncio.to_thread(target.unlink)
            raise
        if previous_path and previous_path != relative_path:
            previous = self.storage.absolute_path(previous_path)
            if previous.exists():
                await asyncio.to_thread(previous.unlink)
        return await self.response(row)

    async def delete_model(self, actor: User, idea_id: UUID) -> IdeaResponse:
        row = await self.repository.get_idea(idea_id)
        if row is None:
            raise AppError(
                type="idea_not_found",
                title="Idea not found",
                status=404,
                detail="Idea does not exist.",
            )
        previous_path = row.model_storage_path
        row.model_storage_path = None
        row.model_original_filename = None
        row.model_size_bytes = None
        self.repository.add_audit(
            actor_user_id=actor.id,
            action="idea.model.delete",
            entity_type="idea",
            entity_id=str(row.id),
            details={},
        )
        await self.session.commit()
        await self.session.refresh(row)
        if previous_path:
            previous = self.storage.absolute_path(previous_path)
            if previous.exists():
                await asyncio.to_thread(previous.unlink)
        return await self.response(row)

    async def archive(self, actor: User, idea_id: UUID) -> IdeaResponse:
        return await self.update(actor, idea_id, IdeaUpdate(is_active=False))
