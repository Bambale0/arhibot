from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies.auth import AdminUser, DbSession
from app.schemas.questionnaires import (
    QuestionnaireApplicationResponse,
    QuestionnaireCatalogAdminResponse,
    QuestionnaireCatalogAdminUpdate,
)
from app.services.questionnaire_service import QuestionnaireService

router = APIRouter(prefix="/admin", tags=["Admin", "Questionnaires"])


@router.get(
    "/questionnaires",
    operation_id="adminGetQuestionnaireCatalog",
    response_model=QuestionnaireCatalogAdminResponse,
)
async def admin_get_questionnaire_catalog(
    _admin: AdminUser, session: DbSession
) -> QuestionnaireCatalogAdminResponse:
    return await QuestionnaireService(session).admin_catalog()


@router.put(
    "/questionnaires",
    operation_id="adminUpdateQuestionnaireCatalog",
    response_model=QuestionnaireCatalogAdminResponse,
)
async def admin_update_questionnaire_catalog(
    payload: QuestionnaireCatalogAdminUpdate,
    admin: AdminUser,
    session: DbSession,
) -> QuestionnaireCatalogAdminResponse:
    return await QuestionnaireService(session).update_admin_catalog(admin, payload)


@router.get(
    "/questionnaire-applications",
    operation_id="adminListQuestionnaireApplications",
    response_model=list[QuestionnaireApplicationResponse],
)
async def admin_list_questionnaire_applications(
    _admin: AdminUser,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[QuestionnaireApplicationResponse]:
    return await QuestionnaireService(session).list_applications(limit=limit)
