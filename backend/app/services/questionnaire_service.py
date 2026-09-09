from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models.users import User
from app.questionnaires.catalog import CATALOG_VERSION, build_catalog
from app.repositories.assets import AssetRepository
from app.repositories.projects import ProjectRepository
from app.schemas.questionnaires import DesignSession
from app.services.project_service import ProjectService


class QuestionnaireService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectRepository(session)
        self.assets = AssetRepository(session)

    @staticmethod
    def catalog() -> dict:
        return build_catalog()

    @staticmethod
    def _definitions() -> dict[str, dict]:
        return {item["key"]: item for item in build_catalog()["questionnaires"]}

    async def get_session(self, user: User, project_id: UUID) -> DesignSession | None:
        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        raw = (project.context or {}).get("design_session")
        return DesignSession.model_validate(raw) if raw else None

    async def save_session(
        self, user: User, project_id: UUID, payload: DesignSession
    ) -> DesignSession:
        project = await ProjectService(self.projects).get_owned_model(user, project_id)
        self._validate(payload)

        for asset_id in (payload.source_asset_id, payload.scene_asset_id):
            if asset_id is None:
                continue
            asset = await self.assets.get_owned(asset_id, user.id)
            if asset is None or asset.project_id != project.id:
                raise AppError(
                    type="questionnaire_asset_not_found",
                    title="Questionnaire asset not found",
                    status=422,
                    detail="A questionnaire scene asset must belong to the current project.",
                )

        project.context = {
            **(project.context or {}),
            "design_session": payload.model_dump(mode="json"),
        }
        await self.session.commit()
        await self.session.refresh(project)
        return payload

    def _validate(self, payload: DesignSession) -> None:
        if payload.catalog_version != CATALOG_VERSION:
            raise AppError(
                type="questionnaire_catalog_version_mismatch",
                title="Questionnaire catalog changed",
                status=409,
                detail="Reload the questionnaire before continuing.",
            )

        definitions = self._definitions()
        object_keys = {
            item for section in build_catalog()["sections"] for item in section["object_keys"]
        }
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
                self._validate_answer(question, answer)

        if payload.application_submitted:
            if not payload.accepted_objects:
                raise self._invalid("The application can be submitted only after an accepted sketch.")
            application = payload.answers.get("zayavka", {})
            for qid in ("20", "21", "22", "23", "24"):
                if application.get(qid) in (None, "", []):
                    raise self._invalid("The application is incomplete.")
            if application.get("25") is not True:
                raise self._invalid("Personal-data consent is required.")

    def _validate_answer(self, question: dict, answer: object) -> None:
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

    @staticmethod
    def _invalid(detail: str) -> AppError:
        return AppError(
            type="questionnaire_session_invalid",
            title="Invalid questionnaire session",
            status=422,
            detail=detail,
        )
