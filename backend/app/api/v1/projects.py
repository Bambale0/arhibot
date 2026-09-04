from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies.auth import CurrentUser, DbSession
from app.repositories.projects import ProjectRepository
from app.schemas.errors import ProblemDetails
from app.schemas.projects import (
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post(
    "",
    operation_id="createProject",
    summary="Create project",
    description="Creates a project owned by the current user.",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        422: {"model": ProblemDetails, "description": "Invalid project data."},
    },
)
async def create_project(
    payload: ProjectCreateRequest,
    user: CurrentUser,
    session: DbSession,
) -> ProjectResponse:
    return await ProjectService(ProjectRepository(session)).create(user, payload)


@router.get(
    "",
    operation_id="listProjects",
    summary="List projects",
    description="Lists non-deleted projects owned by the current user using cursor pagination.",
    response_model=ProjectListResponse,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        422: {"model": ProblemDetails, "description": "Invalid pagination cursor."},
    },
)
async def list_projects(
    user: CurrentUser,
    session: DbSession,
    cursor: str | None = Query(default=None, description="Opaque cursor from the previous page."),
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProjectListResponse:
    return await ProjectService(ProjectRepository(session)).list(user, cursor=cursor, limit=limit)


@router.get(
    "/{project_id}",
    operation_id="getProject",
    summary="Get project",
    description="Returns one project when it belongs to the current user.",
    response_model=ProjectResponse,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        404: {"model": ProblemDetails, "description": "Project not found."},
    },
)
async def get_project(project_id: UUID, user: CurrentUser, session: DbSession) -> ProjectResponse:
    return await ProjectService(ProjectRepository(session)).get(user, project_id)


@router.patch(
    "/{project_id}",
    operation_id="updateProject",
    summary="Update project",
    description="Updates editable fields of a project owned by the current user.",
    response_model=ProjectResponse,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        404: {"model": ProblemDetails, "description": "Project not found."},
        422: {"model": ProblemDetails, "description": "Invalid project data."},
    },
)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdateRequest,
    user: CurrentUser,
    session: DbSession,
) -> ProjectResponse:
    return await ProjectService(ProjectRepository(session)).update(user, project_id, payload)


@router.delete(
    "/{project_id}",
    operation_id="deleteProject",
    summary="Delete project",
    description="Soft-deletes a project owned by the current user.",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        404: {"model": ProblemDetails, "description": "Project not found."},
    },
)
async def delete_project(project_id: UUID, user: CurrentUser, session: DbSession) -> Response:
    await ProjectService(ProjectRepository(session)).delete(user, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
