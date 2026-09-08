from __future__ import annotations

from uuid import UUID

from app.architecture.glb import CanonicalGlbBuilder, GlbBuildResult
from app.architecture.rendering import MassingRenderer, PlanSheetRenderer
from app.architecture.schemas import (
    ArchitecturePackage,
    ArchitectureSaveResponse,
    GeometryValidationReport,
)
from app.architecture.validation import GeometryValidator
from app.core.errors import AppError
from app.db.models.projects import Project
from app.db.models.users import User
from app.repositories.projects import ProjectRepository


class ArchitectureService:
    """Project-level seam for canonical geometry persistence and deterministic renderers."""

    def __init__(
        self,
        repository: ProjectRepository,
        glb_builder: CanonicalGlbBuilder | None = None,
    ) -> None:
        self.repository = repository
        self.validator = GeometryValidator()
        self.plan_renderer = PlanSheetRenderer()
        self.massing_renderer = MassingRenderer()
        self.glb_builder = glb_builder or CanonicalGlbBuilder()

    async def _get_project(self, user: User, project_id: UUID) -> Project:
        project = await self.repository.get_owned(project_id, user.id)
        if project is None:
            raise AppError(
                type="project_not_found",
                title="Project not found",
                status=404,
                detail="The project does not exist or is not available to this user.",
            )
        return project

    def validate(self, package: ArchitecturePackage) -> GeometryValidationReport:
        return self.validator.validate(package.geometry, package=package)

    def _require_valid(self, package: ArchitecturePackage) -> GeometryValidationReport:
        report = self.validate(package)
        if report.valid:
            return report
        summary = "; ".join(
            issue.message for issue in report.issues if issue.severity == "error"
        )
        raise AppError(
            type="invalid_architectural_geometry",
            title="Architectural geometry is invalid",
            status=422,
            detail=summary[:2000] or "The geometry failed validation.",
        )

    async def validate_project(
        self,
        user: User,
        project_id: UUID,
        package: ArchitecturePackage,
    ) -> GeometryValidationReport:
        await self._get_project(user, project_id)
        return self.validate(package)

    async def save(
        self,
        user: User,
        project_id: UUID,
        package: ArchitecturePackage,
    ) -> ArchitectureSaveResponse:
        project = await self._get_project(user, project_id)
        report = self._require_valid(package)
        context = dict(project.context or {})
        context["architecture"] = package.model_dump(mode="json", exclude_none=True)
        project.context = context
        await self.repository.session.commit()
        await self.repository.session.refresh(project)
        return ArchitectureSaveResponse(architecture=package, validation=report)

    async def get(self, user: User, project_id: UUID) -> ArchitecturePackage:
        project = await self._get_project(user, project_id)
        raw = (project.context or {}).get("architecture")
        if raw is None:
            raise AppError(
                type="architecture_not_found",
                title="Architecture not found",
                status=404,
                detail="This project does not have a canonical architecture model yet.",
            )
        return ArchitecturePackage.model_validate(raw)

    async def render_plan(self, user: User, project_id: UUID) -> str:
        package = await self.get(user, project_id)
        return self.plan_renderer.render(package)

    async def render_massing(self, user: User, project_id: UUID) -> str:
        package = await self.get(user, project_id)
        return self.massing_renderer.render(package)

    async def render_glb(self, user: User, project_id: UUID) -> GlbBuildResult:
        package = await self.get(user, project_id)
        self._require_valid(package)
        return self.glb_builder.build(package)
