from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models.assets import Asset
from app.db.models.projects import Project
from app.db.models.questionnaires import (
    QuestionnaireApplication,
    QuestionnaireCatalogConfig,
    QuestionnaireCatalogRevision,
)
from app.db.models.users import User
from app.domain.generations.enums import GenerationStatus, GenerationType
from app.questionnaires.application_brief import build_application_brief
from app.questionnaires.generation_prompt import (
    build_initial_concept_prompt,
    build_questionnaire_generation_prompt,
)
from app.questionnaires.generation_prompt import (
    condition_ok as questionnaire_condition_ok,
)
from app.repositories.admin import AdminRepository
from app.repositories.assets import AssetRepository
from app.repositories.credits import CreditRepository
from app.repositories.generations import GenerationRepository
from app.repositories.projects import ProjectRepository
from app.repositories.questionnaires import QuestionnaireRepository
from app.schemas.generations import GenerationCreate
from app.schemas.questionnaires import (
    DesignSession,
    QuestionnaireGenerationCostResponse,
    QuestionnaireApplicationResponse,
    QuestionnaireCatalogAdminResponse,
    QuestionnaireCatalogAdminUpdate,
    QuestionnaireCatalogResponse,
)
from app.services.asset_service import LocalMediaStorage
from app.services.project_service import ProjectService


class QuestionnaireService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.assets = AssetRepository(session)
        self.credits = CreditRepository(session)
        self.generations = GenerationRepository(session)
        self.repository = QuestionnaireRepository(session)
        self.admin_repository = AdminRepository(session)

    async def catalog(self) -> dict:
        row = await self.repository.get_catalog()
        if row is None:
            raise AppError(
                type="questionnaire_catalog_missing",
                title="Questionnaire catalog missing",
                status=503,
                detail="The questionnaire catalog has not been configured.",
            )
        return QuestionnaireCatalogResponse.model_validate(row.catalog).model_dump(mode="json")

    async def catalog_for_version(self, version: str) -> dict | None:
        row = await self.repository.get_catalog()
        if row is not None and row.version == version:
            return QuestionnaireCatalogResponse.model_validate(row.catalog).model_dump(mode="json")
        revision = await self.repository.get_catalog_revision(version)
        if revision is None:
            return None
        return QuestionnaireCatalogResponse.model_validate(revision.catalog).model_dump(mode="json")

    async def get_session(self, user: User, project_id: UUID) -> DesignSession | None:
        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        raw = (project.context or {}).get("design_session")
        return DesignSession.model_validate(raw) if raw else None

    async def save_session(
        self, user: User, project_id: UUID, payload: DesignSession
    ) -> DesignSession:
        if payload.application_submitted:
            raise self._invalid("Submit the application through the application endpoint.")
        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        previous = self._stored_session(project.context)
        catalog = await self.catalog()
        self._validate(payload, catalog, allow_submitted=False, previous=previous)
        self._validate_accepted_object_locks(previous, payload, catalog)
        self._validate_acceptance_completion(previous, payload, catalog)
        await self._validate_assets(user, project.id, payload)
        await self._validate_generations(
            user, project.id, payload, catalog=catalog, previous=previous
        )
        project.context = {
            **(project.context or {}),
            "design_session": payload.model_dump(mode="json"),
        }
        await self.session.commit()
        await self.session.refresh(project)
        return payload

    async def submit_application(
        self, user: User, project_id: UUID, payload: DesignSession
    ) -> tuple[DesignSession, QuestionnaireApplicationResponse]:
        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        previous = self._stored_session(project.context)
        catalog = await self.catalog()
        self._validate(payload, catalog, allow_submitted=True, previous=previous)
        self._validate_accepted_object_locks(previous, payload, catalog)
        self._validate_acceptance_completion(previous, payload, catalog)
        if not payload.application_submitted:
            raise self._invalid("The application must be marked submitted.")
        await self._validate_assets(user, project.id, payload)
        await self._validate_generations(
            user, project.id, payload, catalog=catalog, previous=previous
        )

        existing = await self.repository.get_application_by_session(payload.session_id)
        if existing is not None:
            if existing.user_id != user.id or existing.project_id != project.id:
                raise self._invalid("This questionnaire session belongs to another application.")
            return payload, QuestionnaireApplicationResponse.model_validate(existing)

        application = QuestionnaireApplication(
            session_id=payload.session_id,
            project_id=project.id,
            user_id=user.id,
            catalog_version=payload.catalog_version,
            selected_objects=list(payload.selected_objects),
            accepted_objects=list(payload.accepted_objects),
            answers=payload.answers,
            scene_asset_id=payload.scene_asset_id,
            status="new",
        )
        self.repository.add_application(application)
        project.context = {
            **(project.context or {}),
            "design_session": payload.model_dump(mode="json"),
        }
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.repository.get_application_by_session(payload.session_id)
            if existing is None or existing.user_id != user.id or existing.project_id != project.id:
                raise
            return payload, QuestionnaireApplicationResponse.model_validate(existing)
        await self.session.refresh(application)
        await self.session.refresh(project)
        return payload, QuestionnaireApplicationResponse.model_validate(application)

    async def generation_cost(self, user: User) -> QuestionnaireGenerationCostResponse:
        price = await self.credits.get_price(GenerationType.MASTER_PLAN.value)
        if price is None or not price.is_active:
            return QuestionnaireGenerationCostResponse(
                credits=None,
                is_available=False,
            )
        credits = 0 if user.role.value in {"admin", "superadmin"} else price.credits
        return QuestionnaireGenerationCostResponse(
            credits=credits,
            is_available=True,
        )

    async def add_refinement_object(
        self, user: User, project_id: UUID, object_key: str
    ) -> DesignSession:
        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        current = self._stored_session(project.context)
        if (
            current is None
            or not current.initial_concept_mode
            or not current.initial_concept_accepted
            or current.application_submitted
        ):
            raise self._invalid(
                "Objects can be added only after accepting an initial concept."
            )
        if current.current_object is not None or current.region_mode is not None:
            raise self._invalid("Finish the current refinement before adding another object.")
        if object_key in current.selected_objects:
            raise self._invalid("This object is already part of the project.")

        catalog = await self.catalog_for_version(current.catalog_version)
        if catalog is None:
            raise self._invalid("The project questionnaire catalog is unavailable.")
        definitions = {
            item["key"]: item
            for item in catalog["questionnaires"]
            if item["key"] != catalog.get("application_key")
        }
        definition = definitions.get(object_key)
        if definition is None:
            raise self._invalid("The requested questionnaire object is unknown.")

        next_session = current.model_copy(deep=True)
        next_session.selected_objects.append(object_key)
        next_session.current_object = object_key
        answers: dict[str, object] = {}
        house_reference_available = "eskez-doma" in next_session.accepted_objects
        first = next(
            (
                question
                for question in definition["questions"]
                if question["phase"] == "pre_render"
                and self._condition_ok(
                    question.get("condition"), answers, house_reference_available
                )
            ),
            None,
        )
        next_session.current_question_id = first["id"] if first else None
        project.context = {
            **(project.context or {}),
            "design_session": next_session.model_dump(mode="json"),
        }
        await self.session.commit()
        await self.session.refresh(project)
        return next_session

    async def start_object_removal(
        self, user: User, project_id: UUID, object_key: str
    ) -> DesignSession:
        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        current = self._stored_session(project.context)
        if (
            current is None
            or not current.initial_concept_mode
            or not current.initial_concept_accepted
            or current.application_submitted
        ):
            raise self._invalid(
                "Objects can be removed only from an accepted initial concept."
            )
        if current.current_object is not None or current.region_mode is not None:
            raise self._invalid("Finish the current refinement before removing another object.")
        if current.pending_removal_object is not None:
            raise self._invalid("Finish the pending object removal first.")
        if object_key not in current.accepted_objects:
            raise self._invalid("Only an object currently present in the accepted scene can be removed.")

        next_session = current.model_copy(deep=True)
        next_session.current_object = object_key
        next_session.current_question_id = None
        next_session.pending_removal_object = object_key
        next_session.region_mode = "edit"
        next_session.region_object = object_key
        project.context = {
            **(project.context or {}),
            "design_session": next_session.model_dump(mode="json"),
        }
        await self.session.commit()
        await self.session.refresh(project)
        return next_session

    async def cancel_object_removal(
        self, user: User, project_id: UUID
    ) -> DesignSession:
        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        current = self._stored_session(project.context)
        if current is None or current.pending_removal_object is None:
            raise self._invalid("There is no pending object removal.")
        next_session = current.model_copy(deep=True)
        next_session.current_object = None
        next_session.current_question_id = None
        next_session.pending_removal_object = None
        next_session.region_mode = None
        next_session.region_object = None
        project.context = {
            **(project.context or {}),
            "design_session": next_session.model_dump(mode="json"),
        }
        await self.session.commit()
        await self.session.refresh(project)
        return next_session

    async def accept_object_removal(
        self, user: User, project_id: UUID
    ) -> DesignSession:
        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        current = self._stored_session(project.context)
        object_key = current.pending_removal_object if current is not None else None
        if (
            current is None
            or not current.initial_concept_mode
            or not current.initial_concept_accepted
            or object_key is None
            or object_key not in current.accepted_objects
        ):
            raise self._invalid("There is no pending accepted-object removal.")

        generation_id = current.generation_ids.get(object_key)
        if generation_id is None:
            raise self._invalid("The removal has no generation task.")
        generation = await self.generations.get_owned(generation_id, user.id)
        if (
            generation is None
            or generation.project_id != project.id
            or generation.status != GenerationStatus.COMPLETED
            or generation.output_asset_id is None
        ):
            raise self._invalid("The object-removal generation is not completed.")
        if generation.type != GenerationType.MASTER_PLAN:
            raise self._invalid("Object removal must use master_plan generation.")
        if generation.input_asset_id != current.scene_asset_id:
            raise self._invalid("Object removal must use the currently accepted scene.")
        if generation.composition_mode != "masked_edit":
            raise self._invalid("Object removal must use deterministic masked composition.")
        edit_region = current.edit_regions.get(object_key)
        if edit_region is None or generation.edit_region != edit_region.model_dump(mode="json"):
            raise self._invalid("Object removal must match the selected edit region.")
        if '"operation":"remove_object"' not in generation.prompt:
            raise self._invalid("The object-removal generation prompt is not canonical.")

        catalog = await self.catalog_for_version(current.catalog_version)
        if catalog is None:
            raise self._invalid("The project questionnaire catalog is unavailable.")
        definition = next(
            item for item in catalog["questionnaires"] if item["key"] == object_key
        )
        review_question = next(
            (
                question
                for question in definition["questions"]
                if question["phase"] == "review"
                and question.get("options")
                and str(question["options"][0]).startswith("Да")
            ),
            None,
        )
        review_answer = (
            current.answers.get(object_key, {}).get(review_question["id"])
            if review_question
            else None
        )
        if not isinstance(review_answer, str) or not review_answer.startswith("Да"):
            raise self._invalid("Accept the removal result before updating the scene.")

        removed = current.model_copy(deep=True)
        removed.accepted_objects = [
            key for key in current.accepted_objects if key != object_key
        ]
        if object_key not in removed.removed_objects:
            removed.removed_objects.append(object_key)
        removed.scene_asset_id = generation.output_asset_id
        removed.scene_generation_id = generation.id
        removed.current_object = None
        removed.current_question_id = None
        removed.pending_removal_object = None
        removed.region_mode = None
        removed.region_object = None
        removed.lock_regions.pop(object_key, None)
        removed.edit_regions.pop(object_key, None)
        removed.review_comments.pop(object_key, None)
        project.context = {
            **(project.context or {}),
            "design_session": removed.model_dump(mode="json"),
        }
        await self.session.commit()
        await self.session.refresh(project)
        return removed

    async def build_generation_request(
        self, user: User, project_id: UUID
    ) -> tuple[GenerationCreate, DesignSession, str]:
        """Build either the one-shot initial concept or one paid refinement."""

        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        session = self._stored_session(project.context)
        if session is None or not session.source_step_completed:
            raise self._invalid("Start the questionnaire before requesting a generation.")
        if session.application_submitted:
            raise self._invalid("A submitted questionnaire cannot create another sketch.")

        catalog = await self.catalog_for_version(session.catalog_version)
        if catalog is None:
            raise AppError(
                type="questionnaire_catalog_version_unavailable",
                title="Questionnaire version unavailable",
                status=409,
                detail="The questionnaire revision for this project is unavailable.",
            )
        definitions = {item["key"]: item for item in catalog["questionnaires"]}

        if session.initial_concept_mode and not session.initial_concept_accepted:
            if session.initial_generation_id is not None:
                raise self._invalid("The initial concept already has a generation task.")
            if set(session.survey_completed_objects) != set(session.selected_objects):
                raise self._invalid(
                    "Complete every selected questionnaire before creating the initial concept."
                )
            house_reference_available = "eskez-doma" in session.selected_objects
            for object_key in session.selected_objects:
                definition = definitions.get(object_key)
                if definition is None:
                    raise self._invalid(
                        f"Questionnaire object {object_key} is not in the catalog."
                    )
                answers = session.answers.get(object_key, {})
                active = [
                    question
                    for question in definition["questions"]
                    if question["phase"] == "pre_render"
                    and self._condition_ok(
                        question.get("condition"), answers, house_reference_available
                    )
                ]
                missing = [
                    question["id"] for question in active if question["id"] not in answers
                ]
                if missing:
                    raise self._invalid(
                        f"Answer every active question for {object_key}: {', '.join(missing)}."
                    )
            prompt = build_initial_concept_prompt(
                catalog,
                session,
                input_asset_present=session.source_asset_id is not None,
            )
            return (
                GenerationCreate(
                    project_id=project_id,
                    input_asset_id=session.source_asset_id,
                    type=GenerationType.MASTER_PLAN,
                    prompt=prompt,
                    composition_mode="replace",
                    edit_region=None,
                    protected_regions=[],
                ),
                session,
                "__initial__",
            )

        object_key = session.current_object
        if not object_key or object_key == "zayavka":
            raise self._invalid("Choose a questionnaire object before requesting a generation.")
        refinement = bool(
            session.initial_concept_mode
            and session.initial_concept_accepted
            and object_key in session.accepted_objects
        )
        if object_key in session.accepted_objects and not refinement:
            raise self._invalid("An accepted questionnaire object cannot be regenerated.")
        if object_key in session.generation_ids and not refinement:
            raise self._invalid("This questionnaire object already has a generation task.")

        definition = definitions.get(object_key)
        if definition is None:
            raise self._invalid("The current questionnaire object is not in the catalog.")
        answers = session.answers.get(object_key, {})
        house_accepted = "eskez-doma" in session.accepted_objects
        active_pre_render = [
            question
            for question in definition["questions"]
            if question["phase"] == "pre_render"
            and self._condition_ok(question.get("condition"), answers, house_accepted)
        ]
        missing = [
            question["id"] for question in active_pre_render if question["id"] not in answers
        ]
        if missing:
            raise self._invalid(
                f"Answer every active question before generation: {', '.join(missing)}."
            )

        input_asset_id = session.scene_asset_id or session.source_asset_id
        generation_type = (
            GenerationType.MASTER_PLAN
            if refinement
            else GenerationType.FACADE
            if object_key == "eskez-doma" and input_asset_id is not None
            else GenerationType.MASTER_PLAN
        )
        accepted_before = [
            key for key in session.accepted_objects if not refinement or key != object_key
        ]
        edit_region = session.edit_regions.get(object_key)
        masked = bool(input_asset_id is not None and (accepted_before or refinement))
        if masked and edit_region is None:
            raise self._invalid(
                "Choose the edit region before changing the accepted scene."
            )
        protected_regions = [
            session.lock_regions[key]
            for key in accepted_before
            if session.lock_regions.get(key) is not None
        ]
        if masked and not session.initial_concept_mode:
            missing_locks = [
                key for key in accepted_before if session.lock_regions.get(key) is None
            ]
            if missing_locks:
                raise self._invalid(
                    "Every previously accepted object must have a locked visual region."
                )

        prompt = build_questionnaire_generation_prompt(
            definition,
            session,
            accepted_before=accepted_before,
            input_asset_present=input_asset_id is not None,
        )
        return (
            GenerationCreate(
                project_id=project_id,
                input_asset_id=input_asset_id,
                type=generation_type,
                prompt=prompt,
                composition_mode="masked_edit" if masked else "replace",
                edit_region=edit_region if masked else None,
                protected_regions=protected_regions,
            ),
            session,
            object_key,
        )

    @classmethod
    def bind_generation_before_commit(
        cls,
        project: Project,
        *,
        expected_session: DesignSession,
        object_key: str,
        generation_id: UUID,
    ) -> None:
        current = cls._stored_session(project.context)
        if current is None or current != expected_session:
            raise AppError(
                type="questionnaire_generation_state_changed",
                title="Questionnaire state changed",
                status=409,
                detail=(
                    "The questionnaire changed while generation was being created. "
                    "Reload the project before retrying."
                ),
            )
        bound = current.model_copy(deep=True)
        if object_key == "__initial__":
            if current.initial_generation_id is not None:
                raise AppError(
                    type="questionnaire_generation_exists",
                    title="Initial concept already exists",
                    status=409,
                    detail="The initial concept already has a generation task.",
                )
            bound.initial_generation_id = generation_id
        else:
            refinement = bool(
                current.initial_concept_mode
                and current.initial_concept_accepted
                and object_key in current.accepted_objects
            )
            if object_key in current.generation_ids and not refinement:
                raise AppError(
                    type="questionnaire_generation_exists",
                    title="Questionnaire generation already exists",
                    status=409,
                    detail="This questionnaire object already has a generation task.",
                )
            bound.generation_ids[object_key] = generation_id
        project.context = {
            **(project.context or {}),
            "design_session": bound.model_dump(mode="json"),
        }

    async def accept_initial_concept(
        self, user: User, project_id: UUID
    ) -> DesignSession:
        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        current = self._stored_session(project.context)
        if (
            current is None
            or not current.initial_concept_mode
            or current.initial_concept_accepted
            or current.initial_generation_id is None
        ):
            raise self._invalid("There is no pending initial concept to accept.")
        generation = await self.generations.get_owned(current.initial_generation_id, user.id)
        if (
            generation is None
            or generation.project_id != project.id
            or generation.status != GenerationStatus.COMPLETED
            or generation.output_asset_id is None
        ):
            raise self._invalid("The initial concept generation is not completed.")
        if generation.type != GenerationType.MASTER_PLAN:
            raise self._invalid("The initial concept must use master_plan generation.")
        if generation.input_asset_id != current.source_asset_id:
            raise self._invalid("The initial concept source does not match the project source.")
        if generation.composition_mode != "replace":
            raise self._invalid("The initial concept must use replace composition.")
        if not generation.prompt.startswith("AUROOM_INITIAL_CONCEPT_V1"):
            raise self._invalid("The initial concept generation prompt is not canonical.")

        accepted = current.model_copy(deep=True)
        accepted.initial_concept_accepted = True
        accepted.accepted_objects = list(current.selected_objects)
        accepted.generation_ids = {
            key: generation.id for key in current.selected_objects
        }
        accepted.scene_asset_id = generation.output_asset_id
        accepted.scene_generation_id = generation.id
        accepted.current_object = None
        accepted.current_question_id = None
        accepted.region_mode = None
        accepted.region_object = None
        project.context = {
            **(project.context or {}),
            "design_session": accepted.model_dump(mode="json"),
        }
        await self.session.commit()
        await self.session.refresh(project)
        return accepted

    async def admin_catalog(self) -> QuestionnaireCatalogAdminResponse:
        row = await self.repository.get_catalog()
        if row is None:
            raise AppError(
                type="questionnaire_catalog_missing",
                title="Questionnaire catalog missing",
                status=503,
                detail="The questionnaire catalog has not been configured.",
            )
        return QuestionnaireCatalogAdminResponse(
            catalog=QuestionnaireCatalogResponse.model_validate(row.catalog),
            source_texts=row.source_texts,
            updated_at=row.updated_at,
        )

    async def update_admin_catalog(
        self, actor: User, payload: QuestionnaireCatalogAdminUpdate
    ) -> QuestionnaireCatalogAdminResponse:
        self._validate_catalog_sources(payload)
        row = await self.repository.get_catalog(for_update=True)
        historical = await self.repository.get_catalog_revision(payload.catalog.version)
        if historical is not None:
            raise AppError(
                type="questionnaire_catalog_version_conflict",
                title="Questionnaire catalog version already used",
                status=409,
                detail="Use a new catalog version; historical versions are immutable.",
            )
        if row is None:
            row = QuestionnaireCatalogConfig(
                id=1,
                version=payload.catalog.version,
                catalog=payload.catalog.model_dump(mode="json"),
                source_texts={key: value.model_dump(mode="json") for key, value in payload.source_texts.items()},
                updated_by_user_id=actor.id,
            )
            self.repository.add_catalog(row)
            old_version = None
        else:
            old_version = row.version
            if old_version == payload.catalog.version:
                raise AppError(
                    type="questionnaire_catalog_version_conflict",
                    title="Questionnaire catalog version unchanged",
                    status=409,
                    detail="Change the catalog version when questionnaire content changes.",
                )
            if await self.repository.get_catalog_revision(old_version) is None:
                self.repository.add_catalog_revision(
                    QuestionnaireCatalogRevision(
                        version=old_version,
                        catalog=row.catalog,
                        source_texts=row.source_texts,
                    )
                )
            row.version = payload.catalog.version
            row.catalog = payload.catalog.model_dump(mode="json")
            row.source_texts = {key: value.model_dump(mode="json") for key, value in payload.source_texts.items()}
            row.updated_by_user_id = actor.id
        self.repository.add_catalog_revision(
            QuestionnaireCatalogRevision(
                version=payload.catalog.version,
                catalog=payload.catalog.model_dump(mode="json"),
                source_texts={
                    key: value.model_dump(mode="json")
                    for key, value in payload.source_texts.items()
                },
            )
        )
        self.admin_repository.add_audit(
            actor_user_id=actor.id,
            action="questionnaires.catalog.update",
            entity_type="questionnaire_catalog",
            entity_id="1",
            details={"old_version": old_version, "new_version": payload.catalog.version},
        )
        await self.session.commit()
        await self.session.refresh(row)
        return await self.admin_catalog()

    async def list_applications(self, *, limit: int = 200) -> list[QuestionnaireApplicationResponse]:
        rows = await self.repository.list_applications_with_context(limit=limit)
        storage = LocalMediaStorage(get_settings())

        catalog_row = await self.repository.get_catalog()
        versions = {row[0].catalog_version for row in rows}
        missing_versions = {
            version
            for version in versions
            if catalog_row is None or version != catalog_row.version
        }
        revisions = await self.repository.get_catalog_revisions(missing_versions)
        catalogs: dict[str, dict | None] = {
            version: (
                catalog_row.catalog
                if catalog_row is not None and version == catalog_row.version
                else revisions.get(version).catalog
                if revisions.get(version) is not None
                else None
            )
            for version in versions
        }

        result: list[QuestionnaireApplicationResponse] = []
        for (
            item,
            project_name,
            user_name,
            scene_storage_path,
            final_generation_id,
            telegram_user_id,
            user_email,
        ) in rows:
            scene_asset_url = (
                storage.signed_url(scene_storage_path, ttl_seconds=3600)
                if scene_storage_path
                else None
            )
            response = QuestionnaireApplicationResponse.model_validate(item)
            application_contact = str(
                item.answers.get("zayavka", {}).get("24") or ""
            ).strip() or None
            result.append(
                QuestionnaireApplicationResponse.model_validate(
                    {
                        **response.model_dump(mode="python"),
                        "project_name": project_name,
                        "user_name": user_name,
                        "scene_asset_url": scene_asset_url,
                        "final_generation_id": final_generation_id,
                        "application_contact": application_contact,
                        "user_email": user_email,
                        "telegram_user_id": telegram_user_id,
                        "brief": build_application_brief(
                            selected_objects=item.selected_objects,
                            accepted_objects=item.accepted_objects,
                            answers=item.answers,
                            catalog=catalogs[item.catalog_version],
                        ),
                    }
                )
            )
        return result

    @staticmethod
    def _stored_session(context: dict | None) -> DesignSession | None:
        raw = (context or {}).get("design_session")
        return DesignSession.model_validate(raw) if raw else None

    @classmethod
    def _validate_accepted_object_locks(
        cls,
        previous: DesignSession | None,
        payload: DesignSession,
        catalog: dict | None = None,
    ) -> None:
        if previous is None:
            return
        if previous.session_id != payload.session_id:
            if cls._session_started(previous):
                raise cls._invalid("A started questionnaire session cannot change its session id.")
            return

        if cls._session_started(previous) and payload.selected_objects != previous.selected_objects:
            raise cls._invalid("Selected questionnaire objects are fixed after the session starts.")
        if (
            previous.initial_concept_accepted
            and payload.survey_completed_objects != previous.survey_completed_objects
        ):
            raise cls._invalid("The initial object snapshot is immutable after acceptance.")
        if (
            previous.initial_concept_accepted
            and payload.initial_generation_id != previous.initial_generation_id
        ):
            raise cls._invalid("The accepted initial generation cannot change.")
        if payload.initial_concept_mode != previous.initial_concept_mode:
            raise cls._invalid("The questionnaire flow mode cannot change after project creation.")
        if payload.removed_objects != previous.removed_objects:
            raise cls._invalid("Removed objects can change only through the removal acceptance endpoint.")
        if payload.pending_removal_object != previous.pending_removal_object:
            raise cls._invalid("Object removal must be started or cancelled through its dedicated endpoint.")
        if payload.initial_concept_accepted != previous.initial_concept_accepted:
            raise cls._invalid("Accept the initial concept through its dedicated endpoint.")

        if previous.source_step_completed:
            if not payload.source_step_completed or payload.source_asset_id != previous.source_asset_id:
                raise cls._invalid(
                    "The site-photo choice is fixed after the questionnaire starts."
                )

        locked = previous.accepted_objects
        if payload.accepted_objects[: len(locked)] != locked:
            raise cls._invalid("Accepted objects are immutable and must keep their order.")
        if len(payload.accepted_objects) > len(locked) + 1:
            raise cls._invalid("Accept objects one at a time.")

        for object_key in locked:
            refining_object = bool(
                previous.initial_concept_mode
                and previous.initial_concept_accepted
                and previous.current_object == object_key
            )
            if (
                payload.generation_ids.get(object_key)
                != previous.generation_ids.get(object_key)
                and not refining_object
            ):
                raise cls._invalid(f"Accepted object {object_key} cannot change generation.")
            previous_answers = previous.answers.get(object_key, {})
            payload_answers = payload.answers.get(object_key, {})
            if payload_answers != previous_answers:
                if not refining_object or catalog is None:
                    raise cls._invalid(f"Accepted object {object_key} cannot change answers.")
                definition = next(
                    (
                        item
                        for item in catalog["questionnaires"]
                        if item["key"] == object_key
                    ),
                    None,
                )
                review_ids = {
                    question["id"]
                    for question in (definition or {}).get("questions", [])
                    if question.get("phase") == "review"
                }
                changed_ids = {
                    key
                    for key in set(previous_answers) | set(payload_answers)
                    if previous_answers.get(key) != payload_answers.get(key)
                }
                if not changed_ids or not changed_ids.issubset(review_ids):
                    raise cls._invalid(
                        f"Accepted object {object_key} can change only review answers during refinement."
                    )
            if (
                payload.review_comments.get(object_key, "")
                != previous.review_comments.get(object_key, "")
                and not refining_object
            ):
                raise cls._invalid(f"Accepted object {object_key} cannot change review comments.")
            previous_lock = previous.lock_regions.get(object_key)
            payload_lock = payload.lock_regions.get(object_key)
            if previous_lock is not None and payload_lock != previous_lock:
                raise cls._invalid(f"Accepted object {object_key} cannot change its lock region.")
            previous_edit = previous.edit_regions.get(object_key)
            payload_edit = payload.edit_regions.get(object_key)
            if previous_edit is not None and payload_edit != previous_edit and not refining_object:
                raise cls._invalid(f"Accepted object {object_key} cannot change its edit region.")

        if len(payload.accepted_objects) == len(locked) + 1:
            new_key = payload.accepted_objects[-1]
            new_lock = payload.lock_regions.get(new_key)
            if new_lock is None:
                raise cls._invalid("A newly accepted object must have a visual lock region.")
            if (
                not previous.initial_concept_mode
                and any(payload.lock_regions.get(object_key) is None for object_key in locked)
            ):
                raise cls._invalid(
                    "Every previously accepted object must have a visual lock "
                    "before adding another object."
                )
            if locked:
                edit_region = payload.edit_regions.get(new_key)
                if edit_region is None or new_lock != edit_region:
                    raise cls._invalid(
                        "A later accepted object must lock exactly the region used for its masked edit."
                    )

        if locked == payload.accepted_objects and locked:
            if (
                payload.scene_asset_id != previous.scene_asset_id
                and not (
                    previous.initial_concept_mode
                    and previous.initial_concept_accepted
                    and previous.current_object in previous.accepted_objects
                )
            ):
                raise cls._invalid(
                    "The accepted scene can change only through an accepted refinement."
                )

    @staticmethod
    def _session_started(session: DesignSession) -> bool:
        return bool(
            session.source_step_completed
            or session.survey_completed_objects
            or session.initial_generation_id
            or session.initial_concept_accepted
            or session.current_question_id
            or session.answers
            or session.accepted_objects
            or session.removed_objects
            or session.pending_removal_object
            or session.generation_ids
            or session.edit_regions
            or session.lock_regions
            or session.review_comments
            or session.region_mode
            or session.application_submitted
        )

    @classmethod
    def _validate_acceptance_completion(
        cls,
        previous: DesignSession | None,
        payload: DesignSession,
        catalog: dict,
    ) -> None:
        if payload.initial_concept_mode:
            return
        previous_accepted: list[str] = []
        if previous is not None and previous.session_id == payload.session_id:
            previous_accepted = previous.accepted_objects
        if len(payload.accepted_objects) != len(previous_accepted) + 1:
            return

        object_key = payload.accepted_objects[-1]
        if previous is not None and previous.session_id == payload.session_id:
            if previous.current_object is not None and previous.current_object != object_key:
                raise cls._invalid("Only the current questionnaire object can be accepted.")

        definitions = {item["key"]: item for item in catalog["questionnaires"]}
        definition = definitions[object_key]
        answers = payload.answers.get(object_key, {})
        house_accepted_before = "eskez-doma" in previous_accepted

        for question in definition["questions"]:
            if question["phase"] != "pre_render":
                continue
            if not cls._condition_ok(question.get("condition"), answers, house_accepted_before):
                continue
            if question["id"] not in answers:
                raise cls._invalid(
                    f"Question {object_key}.{question['id']} must be answered or explicitly skipped before acceptance."
                )

        review_question = next(
            (
                question
                for question in definition["questions"]
                if question["phase"] == "review"
                and question.get("options")
                and str(question["options"][0]).startswith("Да")
            ),
            None,
        )
        review_answer = answers.get(review_question["id"]) if review_question else None
        if not isinstance(review_answer, str) or not review_answer.startswith("Да"):
            raise cls._invalid("An object can be accepted only after a positive sketch review.")

    async def _validate_assets(self, user: User, project_id: UUID, payload: DesignSession) -> None:
        for asset_id in (payload.source_asset_id, payload.scene_asset_id):
            if asset_id is None:
                continue
            asset = await self.assets.get_owned(asset_id, user.id)
            if asset is None or asset.project_id != project_id:
                raise AppError(
                    type="questionnaire_asset_not_found",
                    title="Questionnaire asset not found",
                    status=422,
                    detail="A questionnaire scene asset must belong to the current project.",
                )

    async def _validate_generations(
        self,
        user: User,
        project_id: UUID,
        payload: DesignSession,
        catalog: dict,
        *,
        previous: DesignSession | None = None,
    ) -> None:
        resolved = {}
        for object_key, generation_id in payload.generation_ids.items():
            generation = await self.generations.get_owned(generation_id, user.id)
            if generation is None or generation.project_id != project_id:
                raise self._invalid(
                    f"Generation for {object_key} must belong to the current project."
                )
            resolved[object_key] = generation

        for object_key in payload.accepted_objects:
            generation = resolved.get(object_key)
            if generation is None:
                raise self._invalid(
                    f"Accepted object {object_key} must reference a completed generation."
                )
            if (
                generation.status != GenerationStatus.COMPLETED
                or generation.output_asset_id is None
            ):
                raise self._invalid(
                    f"Accepted object {object_key} must reference a completed generation with output."
                )

        if payload.initial_concept_mode:
            if payload.initial_concept_accepted:
                initial_objects = set(payload.survey_completed_objects)
                if not initial_objects or not initial_objects.issubset(
                    set(payload.selected_objects)
                ):
                    raise self._invalid(
                        "The initial concept object snapshot is invalid."
                    )
                accounted_objects = set(payload.accepted_objects) | set(payload.removed_objects)
                if not initial_objects.issubset(accounted_objects):
                    raise self._invalid(
                        "Every initial concept object must remain accepted or be explicitly removed."
                    )
                if payload.initial_generation_id is None:
                    raise self._invalid("The accepted initial concept has no generation.")
                initial_generation = await self.generations.get_owned(
                    payload.initial_generation_id, user.id
                )
                if (
                    initial_generation is None
                    or initial_generation.project_id != project_id
                    or initial_generation.status != GenerationStatus.COMPLETED
                    or initial_generation.output_asset_id is None
                ):
                    raise self._invalid("The initial concept generation is unavailable.")
                if (
                    previous is not None
                    and previous.initial_concept_accepted
                    and payload.scene_asset_id != previous.scene_asset_id
                ):
                    refinement_key = previous.current_object
                    if not refinement_key or refinement_key not in payload.accepted_objects:
                        raise self._invalid(
                            "A changed accepted scene must identify the refined object."
                        )
                    definition = next(
                        item
                        for item in catalog["questionnaires"]
                        if item["key"] == refinement_key
                    )
                    review_question = next(
                        (
                            question
                            for question in definition["questions"]
                            if question["phase"] == "review"
                            and question.get("options")
                            and str(question["options"][0]).startswith("Да")
                        ),
                        None,
                    )
                    review_answer = (
                        payload.answers.get(refinement_key, {}).get(review_question["id"])
                        if review_question
                        else None
                    )
                    if (
                        not isinstance(review_answer, str)
                        or not review_answer.startswith("Да")
                    ):
                        raise self._invalid(
                            "A refinement can update the accepted scene only after a positive review."
                        )
                    generation = resolved.get(refinement_key)
                    if generation is None:
                        raise self._invalid("The refinement generation is unavailable.")
                    if generation.type != GenerationType.MASTER_PLAN:
                        raise self._invalid("Initial-concept refinements must use master_plan.")
                    if generation.input_asset_id != previous.scene_asset_id:
                        raise self._invalid(
                            "A refinement must use the previously accepted scene."
                        )
                    if generation.composition_mode != "masked_edit":
                        raise self._invalid(
                            "A refinement must use deterministic masked composition."
                        )
                    edit_region = payload.edit_regions.get(refinement_key)
                    if (
                        edit_region is None
                        or generation.edit_region != edit_region.model_dump(mode="json")
                    ):
                        raise self._invalid(
                            "The refinement generation must match the selected edit region."
                        )
                    if payload.scene_asset_id != generation.output_asset_id:
                        raise self._invalid(
                            "The accepted scene must be the refinement output."
                        )
                    if payload.scene_generation_id != generation.id:
                        raise self._invalid(
                            "The accepted scene generation must match the refinement output."
                        )
                elif previous is not None and previous.initial_concept_accepted:
                    if payload.scene_generation_id != previous.scene_generation_id:
                        raise self._invalid(
                            "The accepted scene generation cannot change without a new refinement."
                        )
                    if payload.scene_generation_id is None:
                        raise self._invalid("The accepted scene has no generation reference.")
                    current_scene_generation = await self.generations.get_owned(
                        payload.scene_generation_id, user.id
                    )
                    if (
                        current_scene_generation is None
                        or current_scene_generation.project_id != project_id
                        or current_scene_generation.status != GenerationStatus.COMPLETED
                        or current_scene_generation.output_asset_id != payload.scene_asset_id
                    ):
                        raise self._invalid(
                            "The accepted scene must match its completed generation output."
                        )
                elif payload.scene_asset_id != initial_generation.output_asset_id:
                    raise self._invalid(
                        "The accepted initial scene must be the initial generation output."
                    )
                elif payload.scene_generation_id not in (None, initial_generation.id):
                    raise self._invalid(
                        "The initial scene generation must reference the initial generation."
                    )
            return

        previous_accepted = (
            previous.accepted_objects
            if previous is not None and previous.session_id == payload.session_id
            else []
        )
        if len(payload.accepted_objects) == len(previous_accepted) + 1:
            new_key = payload.accepted_objects[-1]
            generation = resolved[new_key]
            expected_type = (
                GenerationType.FACADE
                if new_key == "eskez-doma" and generation.input_asset_id is not None
                else GenerationType.MASTER_PLAN
            )
            if generation.type != expected_type:
                raise self._invalid(
                    f"Questionnaire object {new_key} must use {expected_type.value} generation."
                )
            definition = next(
                item for item in catalog["questionnaires"] if item["key"] == new_key
            )
            expected_prompt = build_questionnaire_generation_prompt(
                definition,
                payload,
                accepted_before=previous_accepted,
                input_asset_present=generation.input_asset_id is not None,
            )
            if generation.prompt != expected_prompt:
                legacy_bound_unchanged = bool(
                    previous is not None
                    and previous.generation_ids.get(new_key) == generation.id
                    and payload.answers.get(new_key, {}) == previous.answers.get(new_key, {})
                    and not generation.prompt.startswith("AUROOM_RENDER_SPEC_V1")
                )
                if not legacy_bound_unchanged:
                    raise self._invalid(
                        "The accepted generation prompt must match the current questionnaire answers."
                    )

        if payload.accepted_objects:
            latest_key = payload.accepted_objects[-1]
            latest_generation = resolved[latest_key]
            if payload.scene_asset_id != latest_generation.output_asset_id:
                raise self._invalid(
                    "The current scene must be the output of the latest accepted object."
                )

        if payload.accepted_objects:
            if len(payload.accepted_objects) == len(previous_accepted) + 1 and not previous_accepted:
                new_key = payload.accepted_objects[-1]
                generation = resolved[new_key]
                if generation.input_asset_id != payload.source_asset_id:
                    raise self._invalid(
                        "The first accepted object must be generated from the questionnaire site source."
                    )
                if generation.composition_mode != "replace":
                    raise self._invalid(
                        "The first accepted object must use the normal replace composition mode."
                    )

        if (
            previous is not None
            and previous.session_id == payload.session_id
            and len(payload.accepted_objects) == len(previous.accepted_objects) + 1
            and previous.accepted_objects
        ):
            new_key = payload.accepted_objects[-1]
            generation = resolved[new_key]
            if generation.input_asset_id != previous.scene_asset_id:
                raise self._invalid(
                    "A new object must be generated from the last accepted scene."
                )
            if generation.composition_mode != "masked_edit":
                raise self._invalid(
                    "A new object after an accepted scene must use deterministic "
                    "masked composition."
                )
            edit_region = payload.edit_regions.get(new_key)
            if edit_region is None or generation.edit_region != edit_region.model_dump(mode="json"):
                raise self._invalid(
                    "The generation edit region must match the questionnaire edit region."
                )
            expected_protected = [
                payload.lock_regions[key].model_dump(mode="json")
                for key in previous.accepted_objects
                if payload.lock_regions.get(key) is not None
            ]
            if list(generation.protected_regions or []) != expected_protected:
                raise self._invalid(
                    "The generation must protect every previously accepted object region."
                )

    def _validate(
        self,
        payload: DesignSession,
        catalog: dict,
        *,
        allow_submitted: bool,
        previous: DesignSession | None = None,
    ) -> None:
        if payload.catalog_version != catalog["version"]:
            raise AppError(
                type="questionnaire_catalog_version_mismatch",
                title="Questionnaire catalog changed",
                status=409,
                detail="Reload the questionnaire before continuing.",
            )

        definitions = {item["key"]: item for item in catalog["questionnaires"]}
        object_keys = {item for section in catalog["sections"] for item in section["object_keys"]}
        progress_started = bool(
            payload.survey_completed_objects
            or payload.initial_generation_id
            or payload.initial_concept_accepted
            or payload.current_question_id
            or payload.answers
            or payload.accepted_objects
            or payload.removed_objects
            or payload.pending_removal_object
            or payload.generation_ids
            or payload.edit_regions
            or payload.lock_regions
            or payload.review_comments
            or payload.region_mode
            or payload.application_submitted
        )
        if progress_started and not payload.source_step_completed:
            raise self._invalid(
                "Choose a site photo or continue without one before starting the questionnaire."
            )
        if payload.source_step_completed and not payload.selected_objects:
            raise self._invalid("Select at least one questionnaire object before starting.")
        if (
            payload.source_step_completed
            and not payload.accepted_objects
            and payload.scene_asset_id != payload.source_asset_id
        ):
            raise self._invalid(
                "Before the first accepted object, the current scene must equal the one-time site source."
            )
        if payload.current_object == "zayavka" and not payload.accepted_objects:
            raise self._invalid("The application opens only after an accepted sketch.")
        if payload.answers.get("zayavka") and not payload.accepted_objects:
            raise self._invalid("Application answers require an accepted sketch.")

        if len(payload.selected_objects) != len(set(payload.selected_objects)):
            raise self._invalid("Selected objects must not contain duplicates.")
        if any(key not in object_keys for key in payload.selected_objects):
            raise self._invalid("The session contains an unknown questionnaire object.")
        if payload.current_object is not None and payload.current_object not in (
            set(payload.selected_objects) | {"zayavka"}
        ):
            raise self._invalid("The current questionnaire is not part of this session.")
        if (
            payload.current_object in set(payload.accepted_objects)
            and not (payload.initial_concept_mode and payload.initial_concept_accepted)
        ):
            raise self._invalid("An accepted object cannot be reopened for editing.")
        if any(key not in payload.selected_objects for key in payload.accepted_objects):
            raise self._invalid("Only selected objects can be accepted.")
        if any(key not in payload.selected_objects for key in payload.removed_objects):
            raise self._invalid("Only selected objects can be marked removed.")
        if set(payload.accepted_objects) & set(payload.removed_objects):
            raise self._invalid("Accepted and removed objects must not overlap.")
        if (
            payload.pending_removal_object is not None
            and payload.pending_removal_object not in payload.accepted_objects
        ):
            raise self._invalid("Pending removal must target an accepted object.")
        if any(key not in payload.selected_objects for key in payload.generation_ids):
            raise self._invalid("Generation ids may only reference selected objects.")
        if any(key not in payload.selected_objects for key in payload.edit_regions):
            raise self._invalid("Edit regions may only reference selected objects.")
        if any(key not in payload.selected_objects for key in payload.lock_regions):
            raise self._invalid("Lock regions may only reference selected objects.")
        if payload.region_mode == "edit":
            if payload.region_object != payload.current_object:
                raise self._invalid("Edit-region selection must target the current object.")
            if (
                payload.region_object in payload.accepted_objects
                and not (payload.initial_concept_mode and payload.initial_concept_accepted)
            ):
                raise self._invalid("An accepted object cannot request a new edit region.")
        if payload.region_mode == "lock":
            targets_current = payload.region_object == payload.current_object
            targets_accepted = payload.region_object in payload.accepted_objects
            if not targets_current and not targets_accepted:
                raise self._invalid(
                    "Lock-region selection must target the current or accepted object."
                )

        house_accepted = "eskez-doma" in payload.accepted_objects
        allowed_answer_keys = set(payload.selected_objects) | {"zayavka"}
        previous_accepted = (
            set(previous.accepted_objects)
            if previous is not None and previous.session_id == payload.session_id
            else set()
        )
        for object_key, answers in payload.answers.items():
            if object_key not in allowed_answer_keys:
                raise self._invalid(f"Answers contain an unknown object: {object_key}.")
            if object_key in previous_accepted:
                previous_answers = previous.answers.get(object_key, {})
                if answers != previous_answers:
                    refining_object = bool(
                        previous.initial_concept_mode
                        and previous.initial_concept_accepted
                        and previous.current_object == object_key
                    )
                    review_ids = {
                        question["id"]
                        for question in definitions[object_key]["questions"]
                        if question.get("phase") == "review"
                    }
                    changed_ids = {
                        key
                        for key in set(previous_answers) | set(answers)
                        if previous_answers.get(key) != answers.get(key)
                    }
                    if (
                        not refining_object
                        or not changed_ids
                        or not changed_ids.issubset(review_ids)
                    ):
                        raise self._invalid(
                            f"Accepted object {object_key} can change only review answers during refinement."
                        )
                # Accepted answers are immutable snapshots of the catalog version under
                # which they were approved. Do not invalidate them after a catalog bump.
                continue
            definition = definitions[object_key]
            questions = {question["id"]: question for question in definition["questions"]}
            for question_id, answer in answers.items():
                question = questions.get(question_id)
                if question is None:
                    raise self._invalid(
                        f"Unknown question {object_key}.{question_id} in the saved session."
                    )
                allow_empty_multi = (
                    object_key == "eskez-doma"
                    and question_id == "15б"
                    and bool(payload.review_comments.get(object_key, "").strip())
                )
                self._validate_answer(
                    question,
                    answer,
                    answers,
                    house_accepted,
                    allow_empty_multi=allow_empty_multi,
                )

        if payload.current_object and payload.current_question_id:
            definition = definitions[payload.current_object]
            question = next(
                (item for item in definition["questions"] if item["id"] == payload.current_question_id),
                None,
            )
            if question is None:
                raise self._invalid("The current question does not exist in the current questionnaire.")
            answers = payload.answers.get(payload.current_object, {})
            if not self._condition_ok(question.get("condition"), answers, house_accepted):
                raise self._invalid("The current question is inactive for the saved answers.")

        if payload.edit_question_ids:
            if payload.current_object is None or payload.current_object == "zayavka":
                raise self._invalid("Edit targets require a current design questionnaire.")
            valid_ids = {item["id"] for item in definitions[payload.current_object]["questions"]}
            if any(question_id not in valid_ids for question_id in payload.edit_question_ids):
                raise self._invalid("Edit targets contain an unknown question.")

        if payload.application_submitted:
            if not allow_submitted:
                raise self._invalid("Application submission is not allowed on this endpoint.")
            if not payload.accepted_objects:
                raise self._invalid("The application can be submitted only after an accepted sketch.")
            application = payload.answers.get("zayavka", {})
            for qid in ("20", "21", "22", "23", "24"):
                if application.get(qid) in (None, "", []):
                    raise self._invalid("The application is incomplete.")
            if application.get("25") is not True:
                raise self._invalid("Personal-data consent is required.")

    def _validate_answer(
        self,
        question: dict,
        answer: object,
        answers: dict[str, object],
        house_accepted: bool,
        *,
        allow_empty_multi: bool = False,
    ) -> None:
        skip_default = question.get("skip_default")
        if skip_default is not None and answer == skip_default:
            if not self._condition_ok(question.get("skip_condition"), answers, house_accepted):
                raise self._invalid("This question cannot be skipped for the current answers.")
            return
        kind = question["kind"]
        options = set(question["options"])
        if kind == "multi":
            if not isinstance(answer, list) or not all(isinstance(item, str) for item in answer):
                raise self._invalid("A multi-select answer must be a list of strings.")
            if not answer and not allow_empty_multi:
                raise self._invalid("Select at least one option or use the explicit skip action.")
            if len(answer) != len(set(answer)):
                raise self._invalid("A multi-select answer must not contain duplicate options.")
            if question.get("max_selections") and len(answer) > question["max_selections"]:
                raise self._invalid("Too many options were selected.")
            if options and any(item not in options for item in answer):
                raise self._invalid("The answer contains an option absent from the questionnaire.")
            for item in answer:
                rule = question.get("option_rules", {}).get(item)
                if rule and not self._condition_ok(rule, answers, house_accepted):
                    raise self._invalid("The selected option is inactive for the current answers.")
            return
        if kind == "number":
            if isinstance(answer, bool) or not isinstance(answer, (int, float)):
                raise self._invalid("A numeric questionnaire answer must be a number.")
            minimum = question.get("min_value")
            maximum = question.get("max_value")
            if minimum is not None and answer < minimum:
                raise self._invalid("The numeric answer is below the questionnaire minimum.")
            if maximum is not None and answer > maximum:
                raise self._invalid("The numeric answer exceeds the questionnaire maximum.")
            return
        if kind == "consent":
            if not isinstance(answer, bool):
                raise self._invalid("Consent must be a boolean value.")
            return
        if not isinstance(answer, str):
            raise self._invalid("A questionnaire answer must be text.")
        if not answer.strip():
            raise self._invalid("A questionnaire answer must not be blank; use skip when available.")
        if kind == "single" and options and answer == "Свой вариант" and "Свой вариант" in options:
            raise self._invalid("Enter the custom questionnaire value instead of the placeholder option.")
        if kind == "single" and options and answer not in options:
            custom_prefix = "Свой вариант:"
            custom_allowed = "Свой вариант" in options and answer.startswith(custom_prefix)
            if not custom_allowed:
                raise self._invalid("The answer is not one of the questionnaire options.")
            custom_value = answer[len(custom_prefix) :].strip()
            if not custom_value:
                raise self._invalid("A custom questionnaire answer must not be blank.")
            minimum = question.get("min_value")
            maximum = question.get("max_value")
            if minimum is not None or maximum is not None:
                match = re.search(r"-?\d+(?:[.,]\d+)?", custom_value)
                if match is None:
                    raise self._invalid("The custom questionnaire answer must contain a number.")
                numeric = float(match.group(0).replace(",", "."))
                if minimum is not None and numeric < minimum:
                    raise self._invalid("The numeric answer is below the questionnaire minimum.")
                if maximum is not None and numeric > maximum:
                    raise self._invalid("The numeric answer exceeds the questionnaire maximum.")
            return
        if kind == "single":
            rule = question.get("option_rules", {}).get(answer)
            if rule and not self._condition_ok(rule, answers, house_accepted):
                raise self._invalid("The selected option is inactive for the current answers.")

    @classmethod
    def _condition_ok(
        cls, condition: dict | None, answers: dict[str, object], house_accepted: bool
    ) -> bool:
        return questionnaire_condition_ok(condition, answers, house_accepted)

    @staticmethod
    def _validate_catalog_sources(payload: QuestionnaireCatalogAdminUpdate) -> None:
        definitions = {item.key: item for item in payload.catalog.questionnaires}
        if set(payload.source_texts) != set(definitions):
            raise AppError(
                type="questionnaire_sources_invalid",
                title="Questionnaire sources invalid",
                status=422,
                detail="Source texts must contain exactly one entry for every questionnaire.",
            )
        for key, definition in definitions.items():
            source = payload.source_texts[key]
            if source.filename != definition.source_file or not source.text.strip():
                raise AppError(
                    type="questionnaire_sources_invalid",
                    title="Questionnaire sources invalid",
                    status=422,
                    detail=f"Source text for {key} does not match its questionnaire source file.",
                )

    @staticmethod
    def _invalid(detail: str) -> AppError:
        return AppError(
            type="questionnaire_session_invalid",
            title="Invalid questionnaire session",
            status=422,
            detail=detail,
        )
