from fastapi import APIRouter

from app.api.v1.assets import router as assets_router
from app.api.v1.auth import router as auth_router
from app.api.v1.billing import router as billing_router
from app.api.v1.generations import router as generations_router
from app.api.v1.projects import router as projects_router
from app.api.v1.users import router as users_router
from app.core.config import get_settings
from app.schemas.api import ApiInfoResponse

settings = get_settings()
router = APIRouter()


@router.get(
    "",
    operation_id="getApiV1Info",
    summary="API v1 information",
    description="Returns metadata for the first public API contract.",
    tags=["Meta"],
    response_model=ApiInfoResponse,
)
async def api_v1_info() -> ApiInfoResponse:
    return ApiInfoResponse(name=settings.app_name, version="v1", contract="/openapi.json")


router.include_router(auth_router)
router.include_router(users_router)
router.include_router(projects_router)
router.include_router(assets_router)
router.include_router(generations_router)
router.include_router(billing_router)
