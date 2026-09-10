from mimetypes import guess_type
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.services.asset_service import LocalMediaStorage

router = APIRouter(prefix="/media", tags=["Media"])


@router.get(
    "/{media_path:path}",
    include_in_schema=False,
)
async def get_signed_media(
    media_path: str,
    expires: int,
    signature: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
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
    media_type = guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=60",
            "X-Content-Type-Options": "nosniff",
            "X-Robots-Tag": "noindex, nofollow",
            "Referrer-Policy": "no-referrer",
        },
    )
