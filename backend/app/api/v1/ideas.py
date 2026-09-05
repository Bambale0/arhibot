from fastapi import APIRouter, Depends

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.config import Settings, get_settings
from app.schemas.admin import PublicIdeaResponse
from app.services.admin_service import AdminService

router = APIRouter(prefix="/ideas", tags=["Ideas"])


@router.get("", response_model=list[PublicIdeaResponse], operation_id="listIdeas")
async def list_ideas(
    _user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> list[PublicIdeaResponse]:
    return await AdminService(session, settings).list_public_ideas()
