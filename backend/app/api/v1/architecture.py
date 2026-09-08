from uuid import UUID

from fastapi import APIRouter, Response

from app.api.dependencies.auth import CurrentUser, DbSession
from app.architecture.schemas import (
    ArchitecturePackage,
    ArchitectureSaveResponse,
    GeometryValidationReport,
)
from app.repositories.projects import ProjectRepository
from app.schemas.errors import ProblemDetails
from app.services.architecture_service import ArchitectureService

router = APIRouter(prefix="/projects/{project_id}/architecture", tags=["Architecture"])


@router.post(
    "/validate",
    operation_id="validateProjectArchitecture",
    summary="Validate canonical house geometry",
    response_model=GeometryValidationReport,
)
async def validate_architecture(
    project_id: UUID,
    payload: ArchitecturePackage,
    user: CurrentUser,
    session: DbSession,
) -> GeometryValidationReport:
    service = ArchitectureService(ProjectRepository(session))
    return await service.validate_project(user, project_id, payload)


@router.put(
    "",
    operation_id="saveProjectArchitecture",
    summary="Save canonical house geometry",
    description=(
        "Stores program, world-coordinate geometry and appearance as one source of truth. "
        "Invalid geometry is rejected before persistence."
    ),
    response_model=ArchitectureSaveResponse,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        404: {"model": ProblemDetails, "description": "Project not found."},
        422: {"model": ProblemDetails, "description": "Geometry validation failed."},
    },
)
async def save_architecture(
    project_id: UUID,
    payload: ArchitecturePackage,
    user: CurrentUser,
    session: DbSession,
) -> ArchitectureSaveResponse:
    return await ArchitectureService(ProjectRepository(session)).save(user, project_id, payload)


@router.get(
    "",
    operation_id="getProjectArchitecture",
    summary="Get canonical house geometry",
    response_model=ArchitecturePackage,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        404: {"model": ProblemDetails, "description": "Architecture not found."},
    },
)
async def get_architecture(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> ArchitecturePackage:
    return await ArchitectureService(ProjectRepository(session)).get(user, project_id)


@router.get(
    "/plan.svg",
    operation_id="renderProjectPlanSheet",
    summary="Render deterministic floor-plan sheet",
    response_class=Response,
)
async def render_plan_sheet(project_id: UUID, user: CurrentUser, session: DbSession) -> Response:
    svg = await ArchitectureService(ProjectRepository(session)).render_plan(user, project_id)
    return Response(content=svg, media_type="image/svg+xml")


@router.get(
    "/massing.svg",
    operation_id="renderProjectMassing",
    summary="Render deterministic geometry-locked massing",
    response_class=Response,
)
async def render_massing(project_id: UUID, user: CurrentUser, session: DbSession) -> Response:
    svg = await ArchitectureService(ProjectRepository(session)).render_massing(user, project_id)
    return Response(content=svg, media_type="image/svg+xml")


@router.get(
    "/model.glb",
    operation_id="renderProjectCanonicalGlb",
    summary="Render deterministic canonical 3D massing as glTF 2.0 GLB",
    description=(
        "Builds a real binary glTF mesh in meters directly from the saved ArchitecturePackage. "
        "The endpoint never infers facade openings or photoreal textures that are not present in "
        "canonical geometry. Renderer fidelity warnings are exposed in a response header and in "
        "the GLB asset extras."
    ),
    response_class=Response,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        404: {"model": ProblemDetails, "description": "Architecture not found."},
        422: {"model": ProblemDetails, "description": "Saved geometry is invalid."},
    },
)
async def render_canonical_glb(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    result = await ArchitectureService(ProjectRepository(session)).render_glb(user, project_id)
    headers = {
        "Content-Disposition": f'inline; filename="auroom-{project_id}.glb"',
        "X-AuRoom-Model-Source": "canonical-geometry",
    }
    if result.warnings:
        headers["X-AuRoom-Model-Warnings"] = ",".join(result.warnings)
    return Response(content=result.data, media_type="model/gltf-binary", headers=headers)
