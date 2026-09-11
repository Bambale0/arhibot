import asyncio
from io import BytesIO
from mimetypes import guess_type
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.services.asset_service import LocalMediaStorage

router = APIRouter(prefix="/media", tags=["Media"])

TELEGRAM_PREVIEW_MAX_BYTES = 4_500_000
TELEGRAM_PREVIEW_MAX_SIDE = 2560
TELEGRAM_PHOTO_MAX_ASPECT_RATIO = 20
_PREVIEW_QUALITIES = (88, 82, 76, 70, 64, 58)
_PREVIEW_SIDES = (2560, 2048, 1600, 1280)


def _normalize_telegram_aspect(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width > height * TELEGRAM_PHOTO_MAX_ASPECT_RATIO:
        target_height = (width + TELEGRAM_PHOTO_MAX_ASPECT_RATIO - 1) // TELEGRAM_PHOTO_MAX_ASPECT_RATIO
        canvas = Image.new("RGB", (width, target_height), "white")
        canvas.paste(image, (0, (target_height - height) // 2))
        return canvas
    if height > width * TELEGRAM_PHOTO_MAX_ASPECT_RATIO:
        target_width = (height + TELEGRAM_PHOTO_MAX_ASPECT_RATIO - 1) // TELEGRAM_PHOTO_MAX_ASPECT_RATIO
        canvas = Image.new("RGB", (target_width, height), "white")
        canvas.paste(image, ((target_width - width) // 2, 0))
        return canvas
    return image


def _telegram_preview(path: Path) -> bytes:
    try:
        with Image.open(path) as source:
            # Downsample in-place before EXIF transposition or RGB conversion so a
            # valid high-pixel-count upload cannot require multiple full-size rasters.
            source.thumbnail(
                (TELEGRAM_PREVIEW_MAX_SIDE, TELEGRAM_PREVIEW_MAX_SIDE),
                Image.Resampling.LANCZOS,
                reducing_gap=3.0,
            )
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValueError("Source image cannot be converted for Telegram") from exc

    image = _normalize_telegram_aspect(image)
    for max_side in _PREVIEW_SIDES:
        if max(image.size) > max_side:
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS, reducing_gap=3.0)
        for quality in _PREVIEW_QUALITIES:
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=quality, optimize=True)
            data = buffer.getvalue()
            if len(data) <= TELEGRAM_PREVIEW_MAX_BYTES:
                return data
    raise ValueError("Telegram preview could not be reduced below the size limit")


def _media_headers() -> dict[str, str]:
    return {
        "Cache-Control": "private, max-age=60",
        "X-Content-Type-Options": "nosniff",
        "X-Robots-Tag": "noindex, nofollow",
        "Referrer-Policy": "no-referrer",
    }


@router.get(
    "/{media_path:path}",
    include_in_schema=False,
)
async def get_signed_media(
    media_path: str,
    expires: int,
    signature: str,
    settings: Annotated[Settings, Depends(get_settings)],
    preview: str | None = None,
) -> Response:
    storage = LocalMediaStorage(settings)
    if not storage.verify_signature(media_path, expires=expires, signature=signature):
        raise AppError(
            type="media_link_invalid",
            title="Media link invalid",
            status=403,
            detail="This media link is invalid or has expired.",
        )
    try:
        path = storage.absolute_path(media_path)
    except ValueError as exc:
        raise AppError(
            type="media_not_found",
            title="Media not found",
            status=404,
            detail="The requested media does not exist.",
        ) from exc
    if not path.is_file():
        raise AppError(
            type="media_not_found",
            title="Media not found",
            status=404,
            detail="The requested media does not exist.",
        )

    if preview == "telegram":
        try:
            data = await asyncio.to_thread(_telegram_preview, path)
        except ValueError as exc:
            raise AppError(
                type="media_preview_unavailable",
                title="Media preview unavailable",
                status=422,
                detail="This media cannot be prepared for Telegram delivery.",
            ) from exc
        return Response(
            content=data,
            media_type="image/jpeg",
            headers=_media_headers(),
        )

    media_type = guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        headers=_media_headers(),
    )
