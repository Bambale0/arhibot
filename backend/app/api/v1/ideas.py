from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.config import Settings, get_settings
from app.schemas.admin import PublicIdeaPublicationResponse
from app.schemas.projects import ProjectResponse
from app.services.idea_service import IdeaService

router = APIRouter(prefix="/ideas", tags=["Ideas"])


@router.get("", response_model=list[PublicIdeaPublicationResponse], operation_id="listIdeas")
async def list_ideas(
    _user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[PublicIdeaPublicationResponse]:
    return await IdeaService(session, settings).list_public(limit=limit)


@router.post(
    "/{idea_id}/project",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="startProjectFromIdea",
)
async def start_project_from_idea(
    idea_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> ProjectResponse:
    return await IdeaService(session, settings).start_project(user, idea_id)
