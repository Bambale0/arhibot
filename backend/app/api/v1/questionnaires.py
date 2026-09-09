from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies.auth import CurrentUser, DbSession
from app.schemas.questionnaires import DesignSession, DesignSessionResponse, QuestionnaireCatalogResponse
from app.services.questionnaire_service import QuestionnaireService

router = APIRouter(tags=["Questionnaires"])


@router.get("/questionnaires", operation_id="getQuestionnaireCatalog", response_model=QuestionnaireCatalogResponse)
async def get_questionnaire_catalog() -> QuestionnaireCatalogResponse:
    return QuestionnaireCatalogResponse.model_validate(QuestionnaireService.catalog())


@router.get("/projects/{project_id}/questionnaire-session", operation_id="getProjectQuestionnaireSession", response_model=DesignSessionResponse)
async def get_questionnaire_session(project_id: UUID, user: CurrentUser, session: DbSession) -> DesignSessionResponse:
    return DesignSessionResponse(session=await QuestionnaireService(session).get_session(user, project_id))


@router.put("/projects/{project_id}/questionnaire-session", operation_id="saveProjectQuestionnaireSession", response_model=DesignSessionResponse)
async def save_questionnaire_session(project_id: UUID, payload: DesignSession, user: CurrentUser, session: DbSession) -> DesignSessionResponse:
    return DesignSessionResponse(session=await QuestionnaireService(session).save_session(user, project_id, payload))
