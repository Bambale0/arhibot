from uuid import UUID

from fastapi import APIRouter

from app.api.dependencies.auth import CurrentUser, DbSession
from app.schemas.questionnaires import (
    DesignSession,
    DesignSessionResponse,
    QuestionnaireApplicationSubmitResponse,
    QuestionnaireCatalogResponse,
)
from app.services.questionnaire_service import QuestionnaireService

router = APIRouter(tags=["Questionnaires"])


@router.get(
    "/questionnaires",
    operation_id="getQuestionnaireCatalog",
    response_model=QuestionnaireCatalogResponse,
)
async def get_questionnaire_catalog(session: DbSession) -> QuestionnaireCatalogResponse:
    return QuestionnaireCatalogResponse.model_validate(await QuestionnaireService(session).catalog())


@router.get(
    "/projects/{project_id}/questionnaire-session",
    operation_id="getProjectQuestionnaireSession",
    response_model=DesignSessionResponse,
)
async def get_questionnaire_session(
    project_id: UUID, user: CurrentUser, session: DbSession
) -> DesignSessionResponse:
    return DesignSessionResponse(
        session=await QuestionnaireService(session).get_session(user, project_id)
    )


@router.put(
    "/projects/{project_id}/questionnaire-session",
    operation_id="saveProjectQuestionnaireSession",
    response_model=DesignSessionResponse,
)
async def save_questionnaire_session(
    project_id: UUID, payload: DesignSession, user: CurrentUser, session: DbSession
) -> DesignSessionResponse:
    return DesignSessionResponse(
        session=await QuestionnaireService(session).save_session(user, project_id, payload)
    )


@router.post(
    "/projects/{project_id}/questionnaire-application",
    operation_id="submitProjectQuestionnaireApplication",
    response_model=QuestionnaireApplicationSubmitResponse,
)
async def submit_questionnaire_application(
    project_id: UUID, payload: DesignSession, user: CurrentUser, session: DbSession
) -> QuestionnaireApplicationSubmitResponse:
    saved_session, application = await QuestionnaireService(session).submit_application(
        user, project_id, payload
    )
    return QuestionnaireApplicationSubmitResponse(
        session=saved_session,
        application=application,
    )
