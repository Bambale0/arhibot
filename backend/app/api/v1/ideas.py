from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.config import Settings, get_settings
from app.schemas.admin import (
    IdeaPublicationCreate,
    IdeaPublicationResponse,
    IdeaSaveResponse,
    PublicIdeaPublicationResponse,
)
from app.schemas.projects import ProjectResponse
from app.services.idea_service import IdeaService

router = APIRouter(prefix="/ideas", tags=["Ideas"])


@router.get("", response_model=list[PublicIdeaPublicationResponse], operation_id="listIdeas")
async def list_ideas(
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[PublicIdeaPublicationResponse]:
    return await IdeaService(session, settings).list_public(user, limit=limit)


@router.post(
    "",
    response_model=IdeaPublicationResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="publishOwnIdea",
)
async def publish_idea(
    payload: IdeaPublicationCreate,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> IdeaPublicationResponse:
    return await IdeaService(session, settings).publish(user, payload)


@router.get(
    "/mine/{generation_id}",
    response_model=IdeaPublicationResponse | None,
    operation_id="getOwnIdeaPublication",
)
async def get_own_idea_publication(
    generation_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> IdeaPublicationResponse | None:
    return await IdeaService(session, settings).get_own_publication(user, generation_id)


@router.delete(
    "/mine/{generation_id}",
    response_model=IdeaPublicationResponse,
    operation_id="unpublishOwnIdea",
)
async def unpublish_idea(
    generation_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> IdeaPublicationResponse:
    return await IdeaService(session, settings).unpublish(user, generation_id)


@router.get(
    "/{idea_id}",
    response_model=PublicIdeaPublicationResponse,
    operation_id="getIdea",
)
async def get_idea(
    idea_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> PublicIdeaPublicationResponse:
    return await IdeaService(session, settings).get_public(user, idea_id)


@router.put(
    "/{idea_id}/save",
    response_model=IdeaSaveResponse,
    operation_id="saveIdea",
)
async def save_idea(
    idea_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> IdeaSaveResponse:
    return await IdeaService(session, settings).save(user, idea_id)


@router.delete(
    "/{idea_id}/save",
    response_model=IdeaSaveResponse,
    operation_id="unsaveIdea",
)
async def unsave_idea(
    idea_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> IdeaSaveResponse:
    return await IdeaService(session, settings).unsave(user, idea_id)


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
