from uuid import UUID

from fastapi import APIRouter, Response, status

from app.api.dependencies.auth import CurrentUser, DbSession
from app.schemas.projects import ProjectResponse
from app.schemas.questionnaires import (
    DesignSession,
    DesignSessionResponse,
    QuestionnaireApplicationSubmitResponse,
    QuestionnaireCatalogResponse,
    QuestionnaireProjectStartRequest,
)
from app.services.questionnaire_project_service import QuestionnaireProjectService
from app.services.questionnaire_service import QuestionnaireService

router = APIRouter(tags=["Questionnaires"])


@router.get(
    "/questionnaires",
    operation_id="getQuestionnaireCatalog",
    response_model=QuestionnaireCatalogResponse,
)
async def get_questionnaire_catalog(session: DbSession) -> QuestionnaireCatalogResponse:
    return QuestionnaireCatalogResponse.model_validate(await QuestionnaireService(session).catalog())


@router.post(
    "/questionnaire-projects",
    operation_id="startQuestionnaireProject",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_questionnaire_project(
    payload: QuestionnaireProjectStartRequest,
    user: CurrentUser,
    session: DbSession,
) -> ProjectResponse:
    return await QuestionnaireProjectService(session).start(user, payload)


@router.delete(
    "/questionnaire-projects/{project_id}/draft",
    operation_id="discardQuestionnaireProjectDraft",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def discard_questionnaire_project_draft(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> Response:
    await QuestionnaireProjectService(session).discard_draft(user, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    lifecycle = QuestionnaireProjectService(session)
    saved = await lifecycle.save_source_if_draft(user, project_id, payload)
    if saved is None:
        saved = await QuestionnaireService(session).save_session(user, project_id, payload)
    return DesignSessionResponse(session=saved)


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
