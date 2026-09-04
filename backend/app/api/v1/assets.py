from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.config import Settings, get_settings
from app.domain.assets.enums import AssetUploadPurpose
from app.schemas.assets import AssetResponse
from app.schemas.errors import ProblemDetails
from app.services.asset_service import build_asset_service

router = APIRouter(prefix="/assets", tags=["Assets"])


@router.post(
    "",
    operation_id="uploadAsset",
    summary="Upload image",
    description=(
        "Uploads an image to backend-owned local media storage. The returned URL is served "
        "as static media by the public Nginx domain."
    ),
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        404: {"model": ProblemDetails, "description": "Project not found."},
        413: {"model": ProblemDetails, "description": "Image exceeds configured size limit."},
        422: {"model": ProblemDetails, "description": "Invalid or unsupported image."},
    },
)
async def upload_asset(
    user: CurrentUser,
    session: DbSession,
    file: Annotated[UploadFile, File(description="JPEG, PNG, or WebP image")],
    purpose: Annotated[AssetUploadPurpose, Form()] = AssetUploadPurpose.GENERATION_INPUT,
    project_id: Annotated[UUID | None, Form()] = None,
    settings: Settings = Depends(get_settings),
) -> AssetResponse:
    data = await file.read(settings.max_image_size_bytes + 1)
    return await build_asset_service(session, settings).upload(
        user,
        data=data,
        original_filename=file.filename,
        purpose=purpose,
        project_id=project_id,
    )


@router.get(
    "/{asset_id}",
    operation_id="getAsset",
    summary="Get asset",
    description="Returns metadata and the public static URL for an asset owned by the current user.",
    response_model=AssetResponse,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        404: {"model": ProblemDetails, "description": "Asset not found."},
    },
)
async def get_asset(
    asset_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> AssetResponse:
    return await build_asset_service(session, settings).get(user, asset_id)


@router.delete(
    "/{asset_id}",
    operation_id="deleteAsset",
    summary="Delete asset",
    description="Soft-deletes an asset owned by the current user. The file is retained for cleanup.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        404: {"model": ProblemDetails, "description": "Asset not found."},
    },
)
async def delete_asset(
    asset_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> Response:
    await build_asset_service(session, settings).delete(user, asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
