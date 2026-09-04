import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.assets import Asset
from app.db.models.users import User
from app.domain.assets.enums import AssetPurpose, AssetType, AssetUploadPurpose
from app.repositories.assets import AssetRepository
from app.repositories.projects import ProjectRepository
from app.schemas.assets import AssetResponse


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    data: bytes
    mime_type: str
    extension: str
    width: int
    height: int


class LocalMediaStorage:
    def __init__(self, settings: Settings) -> None:
        self.root = Path(settings.media_root).resolve()
        self.public_base_url = settings.media_public_base_url.rstrip("/")

    def absolute_path(self, relative_path: str) -> Path:
        target = (self.root / relative_path).resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError("Unsafe media path")
        return target

    async def write(self, relative_path: str, data: bytes) -> None:
        target = self.absolute_path(relative_path)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, data)

    def public_url(self, relative_path: str) -> str:
        return f"{self.public_base_url}/uploads/{relative_path}"


class AssetService:
    FORMAT_MAP = {
        "JPEG": ("image/jpeg", "jpg"),
        "PNG": ("image/png", "png"),
        "WEBP": ("image/webp", "webp"),
    }

    def __init__(
        self,
        repository: AssetRepository,
        project_repository: ProjectRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.project_repository = project_repository
        self.settings = settings
        self.storage = LocalMediaStorage(settings)

    def _validate_image(self, data: bytes) -> ValidatedImage:
        if not data:
            raise AppError(
                type="invalid_image",
                title="Invalid image",
                status=422,
                detail="The uploaded file is empty.",
            )
        if len(data) > self.settings.max_image_size_bytes:
            raise AppError(
                type="file_too_large",
                title="File too large",
                status=413,
                detail=f"Image must not exceed {self.settings.max_image_size_bytes} bytes.",
            )

        try:
            with Image.open(BytesIO(data)) as image:
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image_format = image.format
                width, height = image.size
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise AppError(
                type="invalid_image",
                title="Invalid image",
                status=422,
                detail="Only valid JPEG, PNG, or WebP images are accepted.",
            ) from exc

        format_info = self.FORMAT_MAP.get(str(image_format).upper())
        if format_info is None:
            raise AppError(
                type="unsupported_image_format",
                title="Unsupported image format",
                status=422,
                detail="Only JPEG, PNG, and WebP images are accepted.",
            )
        if width <= 0 or height <= 0 or width * height > self.settings.max_image_pixels:
            raise AppError(
                type="invalid_image_dimensions",
                title="Invalid image dimensions",
                status=422,
                detail="The image dimensions are not supported.",
            )
        mime_type, extension = format_info
        return ValidatedImage(data, mime_type, extension, width, height)

    def to_response(self, asset: Asset) -> AssetResponse:
        return AssetResponse(
            id=asset.id,
            project_id=asset.project_id,
            type=asset.type,
            purpose=asset.purpose,
            original_filename=asset.original_filename,
            mime_type=asset.mime_type,
            size_bytes=asset.size_bytes,
            width=asset.width,
            height=asset.height,
            url=self.storage.public_url(asset.storage_path),
            created_at=asset.created_at,
        )

    async def upload(
        self,
        user: User,
        *,
        data: bytes,
        original_filename: str | None,
        purpose: AssetUploadPurpose,
        project_id: UUID | None,
    ) -> AssetResponse:
        if project_id is not None:
            project = await self.project_repository.get_owned(project_id, user.id)
            if not project:
                raise AppError(
                    type="project_not_found",
                    title="Project not found",
                    status=404,
                    detail="The project does not exist or is not available to this user.",
                )

        image = self._validate_image(data)
        asset_id = uuid4()
        now = datetime.now(UTC)
        relative_path = (
            f"users/{user.id}/{now:%Y/%m}/{asset_id}.{image.extension}"
        )
        await self.storage.write(relative_path, image.data)

        asset = Asset(
            id=asset_id,
            user_id=user.id,
            project_id=project_id,
            type=AssetType.IMAGE,
            purpose=AssetPurpose(purpose.value),
            original_filename=(original_filename or "")[:255] or None,
            mime_type=image.mime_type,
            size_bytes=len(image.data),
            width=image.width,
            height=image.height,
            storage_path=relative_path,
        )
        self.repository.add(asset)
        try:
            await self.repository.session.commit()
        except Exception:
            await self.repository.session.rollback()
            target = self.storage.absolute_path(relative_path)
            if target.exists():
                await asyncio.to_thread(target.unlink)
            raise
        await self.repository.session.refresh(asset)
        return self.to_response(asset)

    async def get(self, user: User, asset_id: UUID) -> AssetResponse:
        asset = await self._get_owned(user, asset_id)
        return self.to_response(asset)

    async def delete(self, user: User, asset_id: UUID) -> None:
        asset = await self._get_owned(user, asset_id)
        asset.deleted_at = datetime.now(UTC)
        await self.repository.session.commit()

    async def _get_owned(self, user: User, asset_id: UUID) -> Asset:
        asset = await self.repository.get_owned(asset_id, user.id)
        if not asset:
            raise AppError(
                type="asset_not_found",
                title="Asset not found",
                status=404,
                detail="The asset does not exist or is not available to this user.",
            )
        return asset


def build_asset_service(session: AsyncSession, settings: Settings) -> AssetService:
    return AssetService(
        AssetRepository(session),
        ProjectRepository(session),
        settings,
    )
