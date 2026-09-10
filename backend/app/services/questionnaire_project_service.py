from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.projects import Project
from app.db.models.users import User
from app.repositories.assets import AssetRepository
from app.repositories.projects import ProjectRepository
from app.schemas.projects import ProjectResponse
from app.schemas.questionnaires import DesignSession, QuestionnaireProjectStartRequest
from app.services.project_service import ProjectService
from app.services.questionnaire_service import QuestionnaireService


class QuestionnaireProjectService:
    """Owns the lifecycle of projects created by the questionnaire entry flow.

    A questionnaire project is intentionally hidden while it is still on the one-time
    source step. It becomes a normal project as soon as that source choice is saved.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.assets = AssetRepository(session)

    @staticmethod
    def _invalid(detail: str) -> AppError:
        return AppError(
            type="invalid_questionnaire_project",
            title="Invalid questionnaire project",
            status=422,
            detail=detail,
        )

    @staticmethod
    def _is_pristine(session: DesignSession) -> bool:
        return not (
            session.source_step_completed
            or session.source_asset_id
            or session.scene_asset_id
            or session.current_question_id
            or session.answers
            or session.accepted_objects
            or session.generation_ids
            or session.edit_question_ids
            or session.review_comments
            or session.edit_regions
            or session.lock_regions
            or session.region_mode
            or session.region_object
            or session.application_submitted
        )

    @classmethod
    def is_discardable_context(cls, context: dict | None) -> bool:
        context = context or {}
        if context.get("questionnaire_draft") is not True:
            return False
        raw = context.get("design_session")
        if not raw:
            return False
        try:
            design_session = DesignSession.model_validate(raw)
        except Exception:
            return False
        return cls._is_pristine(design_session)

    async def start(
        self,
        user: User,
        payload: QuestionnaireProjectStartRequest,
    ) -> ProjectResponse:
        requested = payload.selected_objects
        if len(requested) != len(set(requested)):
            raise self._invalid("Selected questionnaire objects must not contain duplicates.")

        catalog = await QuestionnaireService(self.session).catalog()
        ordered_keys = [key for section in catalog["sections"] for key in section["object_keys"]]
        allowed = set(ordered_keys)
        if any(key not in allowed for key in requested):
            raise self._invalid("The request contains an unknown questionnaire object.")

        requested_set = set(requested)
        selected = [key for key in ordered_keys if key in requested_set]
        if not selected:
            raise self._invalid("Select at least one questionnaire object.")

        definitions = {item["key"]: item for item in catalog["questionnaires"]}
        first_title = definitions[selected[0]]["title"]
        suffix = f" +{len(selected) - 1}" if len(selected) > 1 else ""
        name = f"{first_title}{suffix}"[:160]
        design_session = DesignSession(
            catalog_version=catalog["version"],
            selected_objects=selected,
            current_object=selected[0] if len(selected) == 1 else None,
        )
        project = Project(
            user_id=user.id,
            name=name,
            description="Проект создан через опросник AuRoom.",
            context={
                "questionnaire_draft": True,
                "design_session": design_session.model_dump(mode="json"),
            },
        )
        self.projects.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return ProjectService.to_response(project)

    async def promote_if_started(
        self,
        user: User,
        project_id: UUID,
        design_session: DesignSession,
    ) -> None:
        if not design_session.source_step_completed:
            return
        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        if (project.context or {}).get("questionnaire_draft") is not True:
            return
        project.context = {
            **(project.context or {}),
            "questionnaire_draft": False,
            "design_session": design_session.model_dump(mode="json"),
        }
        await self.session.commit()

    async def _discard_model(self, project: Project, deleted_at: datetime) -> None:
        for asset in await self.assets.list_active_for_project(project.id):
            asset.deleted_at = deleted_at
        project.deleted_at = deleted_at

    async def discard_draft(self, user: User, project_id: UUID) -> None:
        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        if not self.is_discardable_context(project.context):
            raise AppError(
                type="questionnaire_project_started",
                title="Questionnaire project already started",
                status=409,
                detail="A questionnaire project can be discarded only before the source step is completed.",
            )
        await self._discard_model(project, datetime.now(UTC))
        await self.session.commit()

    async def cleanup_expired_drafts(self, *, cutoff: datetime, limit: int = 100) -> int:
        removed = 0
        for project in await self.projects.list_expired_questionnaire_drafts(cutoff=cutoff, limit=limit):
            if not self.is_discardable_context(project.context):
                continue
            await self._discard_model(project, datetime.now(UTC))
            removed += 1
        if removed:
            await self.session.commit()
        return removed
