from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.generations import QuestionnaireGenerationResponse
from app.schemas.projects import ProjectResponse
from app.schemas.questionnaires import (
    DesignSession,
    DesignSessionResponse,
    QuestionnaireApplicationSubmitResponse,
    QuestionnaireCatalogResponse,
    QuestionnaireGenerationCostResponse,
    QuestionnaireObjectAddRequest,
    QuestionnaireProjectStartRequest,
)
from app.services.generation_service import build_generation_service
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


@router.get(
    "/questionnaire-generation-cost",
    operation_id="getQuestionnaireGenerationCost",
    response_model=QuestionnaireGenerationCostResponse,
)
async def get_questionnaire_generation_cost(
    user: CurrentUser,
    session: DbSession,
) -> QuestionnaireGenerationCostResponse:
    cost = await QuestionnaireService(session).generation_cost(user)
    if not cost.is_available:
        return cost
    # The questionnaire offer includes exactly one free whole-site initial concept.
    # Paid master-plan pricing still applies to post-accept add/change/remove iterations.
    return cost.model_copy(update={"credits": 0})


@router.post(
    "/projects/{project_id}/questionnaire-objects",
    operation_id="addProjectQuestionnaireObject",
    response_model=DesignSessionResponse,
)
async def add_questionnaire_object(
    project_id: UUID,
    payload: QuestionnaireObjectAddRequest,
    user: CurrentUser,
    session: DbSession,
) -> DesignSessionResponse:
    return DesignSessionResponse(
        session=await QuestionnaireService(session).add_refinement_object(
            user, project_id, payload.object_key
        )
    )


@router.post(
    "/projects/{project_id}/questionnaire-object-removal",
    operation_id="startProjectQuestionnaireObjectRemoval",
    response_model=DesignSessionResponse,
)
async def start_questionnaire_object_removal(
    project_id: UUID,
    payload: QuestionnaireObjectAddRequest,
    user: CurrentUser,
    session: DbSession,
) -> DesignSessionResponse:
    return DesignSessionResponse(
        session=await QuestionnaireService(session).start_object_removal(
            user, project_id, payload.object_key
        )
    )


@router.delete(
    "/projects/{project_id}/questionnaire-object-removal",
    operation_id="cancelProjectQuestionnaireObjectRemoval",
    response_model=DesignSessionResponse,
)
async def cancel_questionnaire_object_removal(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> DesignSessionResponse:
    return DesignSessionResponse(
        session=await QuestionnaireService(session).cancel_object_removal(
            user, project_id
        )
    )


@router.post(
    "/projects/{project_id}/questionnaire-object-removal/accept",
    operation_id="acceptProjectQuestionnaireObjectRemoval",
    response_model=DesignSessionResponse,
)
async def accept_questionnaire_object_removal(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> DesignSessionResponse:
    return DesignSessionResponse(
        session=await QuestionnaireService(session).accept_object_removal(
            user, project_id
        )
    )


@router.post(
    "/projects/{project_id}/questionnaire-generation",
    operation_id="createProjectQuestionnaireGeneration",
    response_model=QuestionnaireGenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_questionnaire_generation(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> QuestionnaireGenerationResponse:
    questionnaire = QuestionnaireService(session)
    payload, expected_session, object_key = await questionnaire.build_generation_request(
        user, project_id
    )

    def bind_generation(generation, project) -> None:
        questionnaire.bind_generation_before_commit(
            project,
            expected_session=expected_session,
            object_key=object_key,
            generation_id=generation.id,
        )

    created = await build_generation_service(session, settings).create(
        user, payload, before_commit=bind_generation
    )
    return QuestionnaireGenerationResponse.model_validate(created)


@router.post(
    "/projects/{project_id}/questionnaire-initial-accept",
    operation_id="acceptProjectQuestionnaireInitialConcept",
    response_model=DesignSessionResponse,
)
async def accept_questionnaire_initial_concept(
    project_id: UUID,
    user: CurrentUser,
    session: DbSession,
) -> DesignSessionResponse:
    return DesignSessionResponse(
        session=await QuestionnaireService(session).accept_initial_concept(user, project_id)
    )


@router.get(
    "/projects/{project_id}/questionnaire-generation/{generation_id}",
    operation_id="getProjectQuestionnaireGeneration",
    response_model=QuestionnaireGenerationResponse,
)
async def get_questionnaire_generation(
    project_id: UUID,
    generation_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> QuestionnaireGenerationResponse:
    generation = await build_generation_service(session, settings).get(user, generation_id)
    if generation.project_id != project_id:
        raise AppError(
            type="generation_not_found",
            title="Generation not found",
            status=404,
            detail="The questionnaire generation does not belong to this project.",
        )
    return QuestionnaireGenerationResponse.model_validate(generation)


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
