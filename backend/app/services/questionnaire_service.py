from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.questionnaires import QuestionnaireApplication, QuestionnaireCatalogConfig
from app.db.models.users import User
from app.repositories.admin import AdminRepository
from app.repositories.assets import AssetRepository
from app.repositories.projects import ProjectRepository
from app.repositories.questionnaires import QuestionnaireRepository
from app.schemas.questionnaires import (
    DesignSession,
    QuestionnaireApplicationResponse,
    QuestionnaireCatalogAdminResponse,
    QuestionnaireCatalogAdminUpdate,
    QuestionnaireCatalogResponse,
)
from app.services.project_service import ProjectService


class QuestionnaireService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.assets = AssetRepository(session)
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
        catalog = await self.catalog()
        self._validate(payload, catalog, allow_submitted=False)
        await self._validate_assets(user, project.id, payload)
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
        catalog = await self.catalog()
        self._validate(payload, catalog, allow_submitted=True)
        if not payload.application_submitted:
            raise self._invalid("The application must be marked submitted.")
        await self._validate_assets(user, project.id, payload)

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
            row.version = payload.catalog.version
            row.catalog = payload.catalog.model_dump(mode="json")
            row.source_texts = {key: value.model_dump(mode="json") for key, value in payload.source_texts.items()}
            row.updated_by_user_id = actor.id
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
        return [
            QuestionnaireApplicationResponse.model_validate(item)
            for item in await self.repository.list_applications(limit=limit)
        ]

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

    def _validate(self, payload: DesignSession, catalog: dict, *, allow_submitted: bool) -> None:
        if payload.catalog_version != catalog["version"]:
            raise AppError(
                type="questionnaire_catalog_version_mismatch",
                title="Questionnaire catalog changed",
                status=409,
                detail="Reload the questionnaire before continuing.",
            )

        definitions = {item["key"]: item for item in catalog["questionnaires"]}
        object_keys = {item for section in catalog["sections"] for item in section["object_keys"]}
        if len(payload.selected_objects) != len(set(payload.selected_objects)):
            raise self._invalid("Selected objects must not contain duplicates.")
        if any(key not in object_keys for key in payload.selected_objects):
            raise self._invalid("The session contains an unknown questionnaire object.")
        if payload.current_object is not None and payload.current_object not in (
            set(payload.selected_objects) | {"zayavka"}
        ):
            raise self._invalid("The current questionnaire is not part of this session.")
        if any(key not in payload.selected_objects for key in payload.accepted_objects):
            raise self._invalid("Only selected objects can be accepted.")
        if any(key not in payload.selected_objects for key in payload.generation_ids):
            raise self._invalid("Generation ids may only reference selected objects.")

        house_accepted = "eskez-doma" in payload.accepted_objects
        allowed_answer_keys = set(payload.selected_objects) | {"zayavka"}
        for object_key, answers in payload.answers.items():
            if object_key not in allowed_answer_keys:
                raise self._invalid(f"Answers contain an unknown object: {object_key}.")
            definition = definitions[object_key]
            questions = {question["id"]: question for question in definition["questions"]}
            for question_id, answer in answers.items():
                question = questions.get(question_id)
                if question is None:
                    raise self._invalid(
                        f"Unknown question {object_key}.{question_id} in the saved session."
                    )
                self._validate_answer(question, answer, answers, house_accepted)

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
    ) -> None:
        skip_default = question.get("skip_default")
        if skip_default is not None and answer == skip_default:
            if not self._condition_ok(question.get("skip_condition"), answers, house_accepted):
                raise self._invalid("This question cannot be skipped for the current answers.")
            return
        if not question.get("required") and answer in ("", []):
            return

        kind = question["kind"]
        options = set(question["options"])
        if kind == "multi":
            if not isinstance(answer, list) or not all(isinstance(item, str) for item in answer):
                raise self._invalid("A multi-select answer must be a list of strings.")
            if question.get("max_selections") and len(answer) > question["max_selections"]:
                raise self._invalid("Too many options were selected.")
            if options and any(item not in options for item in answer):
                raise self._invalid("The answer contains an option absent from the questionnaire.")
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
        if kind == "single" and options and answer not in options:
            raise self._invalid("The answer is not one of the questionnaire options.")

    @classmethod
    def _condition_ok(
        cls, condition: dict | None, answers: dict[str, object], house_accepted: bool
    ) -> bool:
        if not condition:
            return True
        operator = condition.get("operator")
        if operator == "house_accepted":
            return house_accepted
        if operator == "all":
            return all(cls._condition_ok(item, answers, house_accepted) for item in condition.get("conditions", []))
        if operator == "any":
            return any(cls._condition_ok(item, answers, house_accepted) for item in condition.get("conditions", []))
        answer = answers.get(condition.get("question_id"))
        value = condition.get("value")
        if operator == "eq":
            return answer == value
        if operator == "neq":
            return answer != value
        if operator == "in":
            return isinstance(answer, str) and isinstance(value, list) and answer in value
        if operator == "contains":
            return isinstance(answer, list) and isinstance(value, str) and value in answer
        if operator == "starts_with":
            return isinstance(answer, str) and isinstance(value, str) and answer.startswith(value)
        if operator == "not_contains_any":
            return not isinstance(answer, list) or not isinstance(value, list) or not any(item in answer for item in value)
        return True

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
