from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.config import Settings, get_settings
from app.schemas.errors import ProblemDetails
from app.schemas.generations import GenerationCreate, GenerationListResponse, GenerationResponse
from app.services.generation_service import build_generation_service

router = APIRouter(prefix="/generations", tags=["Generations"])


@router.post(
    "",
    operation_id="createGeneration",
    summary="Create generation",
    description="Queues an AuRoom image generation. Poll the generation resource until completed or failed.",
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        404: {"model": ProblemDetails, "description": "Project or input asset not found."},
        409: {"model": ProblemDetails, "description": "Insufficient credits."},
        422: {"model": ProblemDetails, "description": "Reference image required for this scenario."},
        503: {"model": ProblemDetails, "description": "Provider, price, or queue unavailable."},
    },
)
async def create_generation(
    payload: GenerationCreate,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> GenerationResponse:
    return await build_generation_service(session, settings).create(user, payload)


@router.get(
    "",
    operation_id="listGenerations",
    summary="Generation history",
    response_model=GenerationListResponse,
)
async def list_generations(
    user: CurrentUser,
    session: DbSession,
    project_id: UUID | None = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    settings: Settings = Depends(get_settings),
) -> GenerationListResponse:
    return await build_generation_service(session, settings).list(
        user,
        project_id=project_id,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/{generation_id}",
    operation_id="getGeneration",
    summary="Get generation",
    response_model=GenerationResponse,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        404: {"model": ProblemDetails, "description": "Generation not found."},
    },
)
async def get_generation(
    generation_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> GenerationResponse:
    return await build_generation_service(session, settings).get(user, generation_id)
