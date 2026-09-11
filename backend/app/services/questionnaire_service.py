from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
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
    build_questionnaire_generation_prompt,
)
from app.questionnaires.generation_prompt import (
    condition_ok as questionnaire_condition_ok,
)
from app.repositories.admin import AdminRepository
from app.repositories.assets import AssetRepository
from app.repositories.generations import GenerationRepository
from app.repositories.projects import ProjectRepository
from app.repositories.questionnaires import QuestionnaireRepository
from app.schemas.generations import GenerationCreate
from app.schemas.questionnaires import (
    DesignSession,
    QuestionnaireApplicationAdminResponse,
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
        self._validate_accepted_object_locks(previous, payload)
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
        self._validate_accepted_object_locks(previous, payload)
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

    async def build_generation_request(
        self, user: User, project_id: UUID
    ) -> tuple[GenerationCreate, DesignSession, str]:
        """Build the internal generation request from the persisted questionnaire state.

        The client never supplies or receives the questionnaire prompt. The server owns
        questionnaire-to-prompt translation so generation provenance cannot drift from
        saved answers or be altered in the browser.
        """
        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        session = self._stored_session(project.context)
        if session is None or not session.source_step_completed:
            raise self._invalid("Start the questionnaire before requesting a generation.")
        if session.application_submitted:
            raise self._invalid("A submitted questionnaire cannot create another sketch.")
        object_key = session.current_object
        if not object_key or object_key == "zayavka":
            raise self._invalid("Choose a questionnaire object before requesting a generation.")
        if object_key in session.accepted_objects:
            raise self._invalid("An accepted questionnaire object cannot be regenerated.")
        if object_key in session.generation_ids:
            raise self._invalid("This questionnaire object already has a generation task.")

        catalog = await self.catalog_for_version(session.catalog_version)
        if catalog is None:
            raise AppError(
                type="questionnaire_catalog_version_unavailable",
                title="Questionnaire version unavailable",
                status=409,
                detail="The questionnaire revision for this project is unavailable.",
            )
        definitions = {item["key"]: item for item in catalog["questionnaires"]}
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
        missing = [question["id"] for question in active_pre_render if question["id"] not in answers]
        if missing:
            raise self._invalid(
                f"Answer every active question before generation: {', '.join(missing)}."
            )

        input_asset_id = session.scene_asset_id or session.source_asset_id
        generation_type = (
            GenerationType.FACADE
            if object_key == "eskez-doma" and input_asset_id is not None
            else GenerationType.MASTER_PLAN
        )
        accepted_before = list(session.accepted_objects)
        edit_region = session.edit_regions.get(object_key)
        masked = bool(accepted_before and input_asset_id is not None)
        if masked and edit_region is None:
            raise self._invalid("Choose the edit region before adding an object to the accepted scene.")
        protected_regions = []
        if masked:
            for accepted_key in accepted_before:
                lock = session.lock_regions.get(accepted_key)
                if lock is None:
                    raise self._invalid(
                        f"Accepted object {accepted_key} must have a locked visual region."
                    )
                protected_regions.append(lock)

        prompt = build_questionnaire_generation_prompt(
            definition,
            session,
            accepted_before=accepted_before,
            input_asset_present=input_asset_id is not None,
        )
        payload = GenerationCreate(
            project_id=project_id,
            input_asset_id=input_asset_id,
            type=generation_type,
            prompt=prompt,
            composition_mode="masked_edit" if masked else "replace",
            edit_region=edit_region if masked else None,
            protected_regions=protected_regions,
        )
        return payload, session, object_key

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
        if object_key in current.generation_ids:
            raise AppError(
                type="questionnaire_generation_exists",
                title="Questionnaire generation already exists",
                status=409,
                detail="This questionnaire object already has a generation task.",
            )
        bound = current.model_copy(deep=True)
        bound.generation_ids[object_key] = generation_id
        project.context = {
            **(project.context or {}),
            "design_session": bound.model_dump(mode="json"),
        }

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

    async def list_applications(
        self, *, settings: Settings, limit: int = 200
    ) -> list[QuestionnaireApplicationAdminResponse]:
        storage = LocalMediaStorage(settings)
        catalogs: dict[str, dict | None] = {}
        result: list[QuestionnaireApplicationAdminResponse] = []

        for item in await self.repository.list_applications(limit=limit):
            if item.catalog_version not in catalogs:
                catalogs[item.catalog_version] = await self.catalog_for_version(item.catalog_version)
            catalog = catalogs[item.catalog_version]
            project = await self.session.get(Project, item.project_id)
            owner = await self.session.get(User, item.user_id)
            scene_image_url: str | None = None
            if item.scene_asset_id is not None:
                asset = await self.session.get(Asset, item.scene_asset_id)
                if asset is not None and asset.deleted_at is None:
                    scene_image_url = storage.signed_url(asset.storage_path)

            brief = (
                build_application_brief(
                    catalog,
                    accepted_objects=list(item.accepted_objects),
                    answers=dict(item.answers or {}),
                )
                if catalog is not None
                else []
            )
            base = QuestionnaireApplicationResponse.model_validate(item).model_dump()
            result.append(
                QuestionnaireApplicationAdminResponse(
                    **base,
                    project_name=project.name if project is not None else str(item.project_id),
                    user_name=owner.display_name if owner is not None else str(item.user_id),
                    scene_image_url=scene_image_url,
                    brief=brief,
                )
            )
        return result

    @staticmethod
    def _stored_session(context: dict | None) -> DesignSession | None:
        raw = (context or {}).get("design_session")
        return DesignSession.model_validate(raw) if raw else None

    @classmethod
    def _validate_accepted_object_locks(
        cls, previous: DesignSession | None, payload: DesignSession
    ) -> None:
        if previous is None:
            return
        if previous.session_id != payload.session_id:
            if cls._session_started(previous):
                raise cls._invalid("A started questionnaire session cannot change its session id.")
            return

        if cls._session_started(previous) and payload.selected_objects != previous.selected_objects:
            raise cls._invalid("Selected questionnaire objects are fixed after the session starts.")

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
            if payload.generation_ids.get(object_key) != previous.generation_ids.get(object_key):
                raise cls._invalid(f"Accepted object {object_key} cannot change generation.")
            if payload.answers.get(object_key, {}) != previous.answers.get(object_key, {}):
                raise cls._invalid(f"Accepted object {object_key} cannot change answers.")
            if payload.review_comments.get(object_key, "") != previous.review_comments.get(
                object_key, ""
            ):
                raise cls._invalid(f"Accepted object {object_key} cannot change review comments.")
            previous_lock = previous.lock_regions.get(object_key)
            payload_lock = payload.lock_regions.get(object_key)
            if previous_lock is not None and payload_lock != previous_lock:
                raise cls._invalid(f"Accepted object {object_key} cannot change its lock region.")
            previous_edit = previous.edit_regions.get(object_key)
            payload_edit = payload.edit_regions.get(object_key)
            if previous_edit is not None and payload_edit != previous_edit:
                raise cls._invalid(f"Accepted object {object_key} cannot change its edit region.")

        if len(payload.accepted_objects) == len(locked) + 1:
            new_key = payload.accepted_objects[-1]
            new_lock = payload.lock_regions.get(new_key)
            if new_lock is None:
                raise cls._invalid("A newly accepted object must have a visual lock region.")
            if any(payload.lock_regions.get(object_key) is None for object_key in locked):
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
            if payload.scene_asset_id != previous.scene_asset_id:
                raise cls._invalid(
                    "The accepted scene can change only when a new object is accepted."
                )

    @staticmethod
    def _session_started(session: DesignSession) -> bool:
        return bool(
            session.source_step_completed
            or session.current_question_id
            or session.answers
            or session.accepted_objects
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
            payload.current_question_id
            or payload.answers
            or payload.accepted_objects
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
        if payload.current_object in set(payload.accepted_objects):
            raise self._invalid("An accepted object cannot be reopened for editing.")
        if any(key not in payload.selected_objects for key in payload.accepted_objects):
            raise self._invalid("Only selected objects can be accepted.")
        if any(key not in payload.selected_objects for key in payload.generation_ids):
            raise self._invalid("Generation ids may only reference selected objects.")
        if any(key not in payload.selected_objects for key in payload.edit_regions):
            raise self._invalid("Edit regions may only reference selected objects.")
        if any(key not in payload.selected_objects for key in payload.lock_regions):
            raise self._invalid("Lock regions may only reference selected objects.")
        if payload.region_mode == "edit":
            if payload.region_object != payload.current_object:
                raise self._invalid("Edit-region selection must target the current object.")
            if payload.region_object in payload.accepted_objects:
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
                if answers != previous.answers.get(object_key, {}):
                    raise self._invalid(f"Accepted object {object_key} cannot change answers.")
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
