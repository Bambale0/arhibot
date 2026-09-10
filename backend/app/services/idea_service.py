from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError
from app.db.models.admin import IdeaPublication
from app.db.models.assets import Asset
from app.db.models.generations import Generation
from app.db.models.projects import Project
from app.db.models.users import User
from app.domain.generations.enums import GenerationStatus
from app.domain.users.enums import UserRole
from app.questionnaires.generation_prompt import condition_ok
from app.repositories.admin import AdminRepository
from app.repositories.ideas import IdeaRepository
from app.schemas.admin import (
    IdeaAnswerSummary,
    IdeaCandidateResponse,
    IdeaObjectSummary,
    IdeaPublicationCreate,
    IdeaPublicationResponse,
    IdeaPublicationUpdate,
    PublicIdeaPublicationResponse,
)
from app.schemas.projects import ProjectResponse
from app.schemas.questionnaires import DesignSession, QuestionnaireProjectStartRequest
from app.services.asset_service import LocalMediaStorage
from app.services.questionnaire_project_service import QuestionnaireProjectService
from app.services.questionnaire_service import QuestionnaireService

PUBLISHABLE_ROLES = {UserRole.ADMIN, UserRole.SUPERADMIN}
PRESENTATION_COMPATIBLE_CATALOG_UPGRADES = {("2026-09-09.2", "2026-09-10.1")}


def _answer_text(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if value is True:
        return "Да"
    if value is False:
        return "Нет"
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


class IdeaService:
    """Public feed backed only by accepted questionnaire generations."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = IdeaRepository(session)
        self.storage = LocalMediaStorage(settings)

    async def _image_url(self, generation: Generation) -> str | None:
        if generation.output_asset_id is None:
            return None
        asset = await self.session.get(Asset, generation.output_asset_id)
        if asset is None or asset.deleted_at is not None:
            return None
        return self.storage.public_url(asset.storage_path)

    async def _publication_response(
        self, publication: IdeaPublication
    ) -> IdeaPublicationResponse | None:
        generation = await self.session.get(Generation, publication.generation_id)
        if generation is None or generation.status != GenerationStatus.COMPLETED:
            return None
        image_url = await self._image_url(generation)
        if image_url is None:
            return None
        snapshot = publication.presentation_snapshot or {}
        try:
            objects = [IdeaObjectSummary.model_validate(item) for item in snapshot["objects"]]
            selected_objects = [str(item) for item in snapshot["selected_objects"]]
            title = str(snapshot["title"])
            category = str(snapshot["category"])
        except (KeyError, TypeError, ValueError):
            return None
        return IdeaPublicationResponse(
            id=publication.id,
            generation_id=publication.generation_id,
            title=title,
            category=category,
            generation_type=generation.type,
            image_url=image_url,
            objects=objects,
            selected_objects=selected_objects,
            published_at=publication.created_at,
            is_active=publication.is_active,
            sort_order=publication.sort_order,
            updated_at=publication.updated_at,
        )

    async def list_public(self, *, limit: int = 50) -> list[PublicIdeaPublicationResponse]:
        result: list[PublicIdeaPublicationResponse] = []
        for publication in await self.repository.list(active_only=True, limit=limit):
            response = await self._publication_response(publication)
            if response is None:
                continue
            result.append(PublicIdeaPublicationResponse(**response.model_dump(exclude={"generation_id", "is_active", "sort_order", "updated_at"})))
        return result

    async def start_project(self, user: User, idea_id: UUID) -> ProjectResponse:
        publication = await self.repository.get(idea_id)
        if publication is None or not publication.is_active:
            raise AppError(
                type="idea_not_found",
                title="Idea not found",
                status=404,
                detail="The published work does not exist or is no longer available.",
            )
        snapshot = publication.presentation_snapshot or {}
        selected_objects = snapshot.get("selected_objects")
        if not isinstance(selected_objects, list) or not selected_objects:
            raise AppError(
                type="idea_source_invalid",
                title="Idea source is invalid",
                status=409,
                detail="The published work cannot be used to start a project.",
            )
        return await QuestionnaireProjectService(self.session).start(
            user,
            QuestionnaireProjectStartRequest(selected_objects=[str(item) for item in selected_objects]),
        )


class AdminIdeaService(IdeaService):
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        super().__init__(session, settings)
        self.audit = AdminRepository(session)

    @staticmethod
    def _accepted_object_key(session: DesignSession, generation_id: UUID) -> str | None:
        for object_key in session.accepted_objects:
            if session.generation_ids.get(object_key) == generation_id:
                return object_key
        return None

    async def _build_snapshot(self, project: Project, generation: Generation) -> dict:
        raw_session = (project.context or {}).get("design_session")
        if not raw_session:
            raise AppError(
                type="idea_source_not_accepted",
                title="Accepted work required",
                status=422,
                detail="Only an accepted result from the Create questionnaire can be published.",
            )
        try:
            design_session = DesignSession.model_validate(raw_session)
        except Exception as exc:
            raise AppError(
                type="idea_source_invalid",
                title="Idea source is invalid",
                status=422,
                detail="The source project has an invalid questionnaire session.",
            ) from exc

        object_key = self._accepted_object_key(design_session, generation.id)
        if object_key is None:
            raise AppError(
                type="idea_source_not_accepted",
                title="Accepted work required",
                status=422,
                detail="Only an accepted result from the Create questionnaire can be published.",
            )

        catalog = await QuestionnaireService(self.session).catalog()
        source_version = design_session.catalog_version
        current_version = str(catalog["version"])
        compatible_upgrade = (source_version, current_version) in PRESENTATION_COMPATIBLE_CATALOG_UPGRADES
        if source_version != current_version and not compatible_upgrade:
            raise AppError(
                type="idea_source_catalog_unavailable",
                title="Questionnaire version unavailable",
                status=409,
                detail=(
                    "This accepted work uses a questionnaire version that cannot be "
                    "rendered safely in the current Ideas feed."
                ),
            )
        definitions = {item["key"]: item for item in catalog["questionnaires"]}
        accepted_index = design_session.accepted_objects.index(object_key)
        selected_objects = design_session.accepted_objects[: accepted_index + 1]
        section_by_object = {
            key: section["title"]
            for section in catalog["sections"]
            for key in section["object_keys"]
        }
        objects: list[dict] = []
        accepted_before: list[str] = []
        for key in selected_objects:
            definition = definitions.get(key)
            if definition is None:
                continue
            answers = design_session.answers.get(key, {})
            house_accepted = "eskez-doma" in accepted_before
            summary: list[dict] = []
            for question in definition["questions"]:
                if question.get("phase") != "pre_render":
                    continue
                if not condition_ok(question.get("condition"), answers, house_accepted):
                    continue
                rendered = _answer_text(answers.get(question["id"]))
                if not rendered:
                    continue
                summary.append(
                    IdeaAnswerSummary(question=question["text"], answer=rendered).model_dump()
                )
            objects.append(
                IdeaObjectSummary(
                    key=key,
                    title=definition["title"],
                    answers=summary,
                ).model_dump()
            )
            accepted_before.append(key)

        definition = definitions[object_key]
        return {
            "catalog_version": design_session.catalog_version,
            "title": definition["title"],
            "category": section_by_object.get(object_key, "Проект"),
            "selected_objects": selected_objects,
            "object_key": object_key,
            "objects": objects,
        }

    async def list_candidates(self, *, limit: int = 200) -> list[IdeaCandidateResponse]:
        result: list[IdeaCandidateResponse] = []
        for generation, project, _owner in await self.repository.list_candidate_sources(limit=limit):
            try:
                snapshot = await self._build_snapshot(project, generation)
            except AppError:
                continue
            image_url = await self._image_url(generation)
            if image_url is None or generation.completed_at is None:
                continue
            publication = await self.repository.get_by_generation(generation.id)
            result.append(
                IdeaCandidateResponse(
                    generation_id=generation.id,
                    title=snapshot["title"],
                    category=snapshot["category"],
                    generation_type=generation.type,
                    image_url=image_url,
                    selected_objects=snapshot["selected_objects"],
                    completed_at=generation.completed_at,
                    publication_id=publication.id if publication else None,
                )
            )
        return result

    async def list_all(self, *, limit: int = 200) -> list[IdeaPublicationResponse]:
        result: list[IdeaPublicationResponse] = []
        for publication in await self.repository.list(limit=limit):
            response = await self._publication_response(publication)
            if response is not None:
                result.append(response)
        return result

    async def create(
        self, actor: User, payload: IdeaPublicationCreate
    ) -> IdeaPublicationResponse:
        if await self.repository.get_by_generation(payload.generation_id) is not None:
            raise AppError(
                type="idea_already_published",
                title="Work already published",
                status=409,
                detail="This generated work already has an Ideas publication.",
            )
        generation = await self.session.get(Generation, payload.generation_id)
        if (
            generation is None
            or generation.status != GenerationStatus.COMPLETED
            or generation.output_asset_id is None
        ):
            raise AppError(
                type="idea_generation_not_found",
                title="Completed generation required",
                status=404,
                detail="The selected completed generation does not exist.",
            )
        owner = await self.session.get(User, generation.user_id)
        if owner is None or owner.role not in PUBLISHABLE_ROLES:
            raise AppError(
                type="idea_publication_consent_required",
                title="Publication consent required",
                status=403,
                detail=(
                    "Customer generations cannot be published until an explicit consent "
                    "workflow is implemented. Use an administrator-owned accepted work."
                ),
            )
        project = await self.session.get(Project, generation.project_id)
        if project is None or project.deleted_at is not None:
            raise AppError(
                type="idea_project_not_found",
                title="Source project not found",
                status=404,
                detail="The source project does not exist.",
            )
        snapshot = await self._build_snapshot(project, generation)
        if await self._image_url(generation) is None:
            raise AppError(
                type="idea_image_not_found",
                title="Generated image not found",
                status=404,
                detail="The generated result image is no longer available.",
            )

        publication = IdeaPublication(
            generation_id=generation.id,
            published_by_user_id=actor.id,
            presentation_snapshot=snapshot,
            is_active=payload.is_active,
            sort_order=payload.sort_order,
        )
        self.repository.add(publication)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError(
                type="idea_already_published",
                title="Work already published",
                status=409,
                detail="This generated work already has an Ideas publication.",
            ) from exc
        self.audit.add_audit(
            actor_user_id=actor.id,
            action="idea.publish",
            entity_type="idea_publication",
            entity_id=str(publication.id),
            details={"generation_id": str(generation.id)},
        )
        await self.session.commit()
        await self.session.refresh(publication)
        response = await self._publication_response(publication)
        if response is None:
            raise AppError(
                type="idea_publication_invalid",
                title="Publication is invalid",
                status=500,
                detail="The new publication could not be read back.",
            )
        return response

    async def update(
        self, actor: User, idea_id: UUID, payload: IdeaPublicationUpdate
    ) -> IdeaPublicationResponse:
        publication = await self.repository.get(idea_id)
        if publication is None:
            raise AppError(
                type="idea_not_found",
                title="Idea not found",
                status=404,
                detail="The published work does not exist.",
            )
        if payload.is_active is not None:
            publication.is_active = payload.is_active
        if payload.sort_order is not None:
            publication.sort_order = payload.sort_order
        self.audit.add_audit(
            actor_user_id=actor.id,
            action="idea.update",
            entity_type="idea_publication",
            entity_id=str(publication.id),
            details={"fields": sorted(payload.model_fields_set)},
        )
        await self.session.commit()
        await self.session.refresh(publication)
        response = await self._publication_response(publication)
        if response is None:
            raise AppError(
                type="idea_publication_invalid",
                title="Publication is invalid",
                status=409,
                detail="The publication source is no longer available.",
            )
        return response

    async def archive(self, actor: User, idea_id: UUID) -> IdeaPublicationResponse:
        return await self.update(actor, idea_id, IdeaPublicationUpdate(is_active=False))
