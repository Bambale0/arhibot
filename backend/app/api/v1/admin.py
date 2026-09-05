from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.dependencies.auth import AdminUser, DbSession
from app.core.config import Settings, get_settings
from app.domain.generations.enums import GenerationType
from app.schemas.admin import (
    AdminOverviewResponse,
    AdminPaymentResponse,
    AdminUserResponse,
    AuditLogResponse,
    BillingPlanCreate,
    BillingPlanResponse,
    BillingPlanUpdate,
    BroadcastCreate,
    BroadcastResponse,
    CreditAdjustmentRequest,
    GenerationRuntimeResponse,
    GenerationRuntimeUpdate,
    IdeaCreate,
    IdeaResponse,
    IdeaUpdate,
    PromptTemplateResponse,
    PromptTemplateUpdate,
    UserStateUpdate,
)
from app.services.admin_service import AdminService

router = APIRouter(prefix="/admin", tags=["Admin"])


def service(session: DbSession, settings: Settings) -> AdminService:
    return AdminService(session, settings)


@router.get("/overview", response_model=AdminOverviewResponse)
async def overview(
    _admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> AdminOverviewResponse:
    return service(session, settings).overview()


@router.get("/tariffs", response_model=list[BillingPlanResponse])
async def list_tariffs(
    _admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> list[BillingPlanResponse]:
    return await service(session, settings).list_plans()


@router.post("/tariffs", response_model=BillingPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_tariff(
    payload: BillingPlanCreate,
    admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> BillingPlanResponse:
    return await service(session, settings).create_plan(admin, payload)


@router.patch("/tariffs/{plan_id}", response_model=BillingPlanResponse)
async def update_tariff(
    plan_id: UUID,
    payload: BillingPlanUpdate,
    admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> BillingPlanResponse:
    return await service(session, settings).update_plan(admin, plan_id, payload)


@router.delete("/tariffs/{plan_id}", response_model=BillingPlanResponse)
async def archive_tariff(
    plan_id: UUID,
    admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> BillingPlanResponse:
    return await service(session, settings).archive_plan(admin, plan_id)


@router.get("/ideas", response_model=list[IdeaResponse])
async def list_ideas(
    _admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> list[IdeaResponse]:
    return await service(session, settings).list_ideas()


@router.post("/ideas", response_model=IdeaResponse, status_code=status.HTTP_201_CREATED)
async def create_idea(
    payload: IdeaCreate,
    admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> IdeaResponse:
    return await service(session, settings).create_idea(admin, payload)


@router.patch("/ideas/{idea_id}", response_model=IdeaResponse)
async def update_idea(
    idea_id: UUID,
    payload: IdeaUpdate,
    admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> IdeaResponse:
    return await service(session, settings).update_idea(admin, idea_id, payload)


@router.delete("/ideas/{idea_id}", response_model=IdeaResponse)
async def archive_idea(
    idea_id: UUID,
    admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> IdeaResponse:
    return await service(session, settings).archive_idea(admin, idea_id)


@router.get("/generation", response_model=GenerationRuntimeResponse)
async def get_generation_settings(
    _admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> GenerationRuntimeResponse:
    return await service(session, settings).get_generation_settings()


@router.put("/generation", response_model=GenerationRuntimeResponse)
async def update_generation_settings(
    payload: GenerationRuntimeUpdate,
    admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> GenerationRuntimeResponse:
    return await service(session, settings).update_generation_settings(admin, payload)


@router.get("/prompts", response_model=list[PromptTemplateResponse])
async def list_prompts(
    _admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> list[PromptTemplateResponse]:
    return await service(session, settings).list_prompts()


@router.put("/prompts/{generation_type}", response_model=PromptTemplateResponse)
async def update_prompt(
    generation_type: GenerationType,
    payload: PromptTemplateUpdate,
    admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> PromptTemplateResponse:
    return await service(session, settings).update_prompt(admin, generation_type, payload)


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    _admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> list[AdminUserResponse]:
    return await service(session, settings).list_users()


@router.post("/users/{user_id}/credits", response_model=AdminUserResponse)
async def adjust_user_credits(
    user_id: UUID,
    payload: CreditAdjustmentRequest,
    admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> AdminUserResponse:
    return await service(session, settings).adjust_credits(admin, user_id, payload)


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def update_user_state(
    user_id: UUID,
    payload: UserStateUpdate,
    admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> AdminUserResponse:
    return await service(session, settings).update_user_state(admin, user_id, payload)


@router.get("/payments", response_model=list[AdminPaymentResponse])
async def list_payments(
    _admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> list[AdminPaymentResponse]:
    return await service(session, settings).list_payments()


@router.post("/payments/{payment_id}/reconcile", response_model=AdminPaymentResponse)
async def reconcile_payment(
    payment_id: UUID,
    admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> AdminPaymentResponse:
    return await service(session, settings).reconcile_payment(admin, payment_id)


@router.get("/broadcasts", response_model=list[BroadcastResponse])
async def list_broadcasts(
    _admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> list[BroadcastResponse]:
    return await service(session, settings).list_broadcasts()


@router.post("/broadcasts", response_model=BroadcastResponse, status_code=status.HTTP_201_CREATED)
async def create_broadcast(
    payload: BroadcastCreate,
    admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> BroadcastResponse:
    return await service(session, settings).create_broadcast(admin, payload)


@router.post("/broadcasts/{campaign_id}/send", response_model=BroadcastResponse)
async def send_broadcast(
    campaign_id: UUID,
    admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> BroadcastResponse:
    return await service(session, settings).send_broadcast(admin, campaign_id)


@router.get("/audit", response_model=list[AuditLogResponse])
async def list_audit(
    _admin: AdminUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> list[AuditLogResponse]:
    return await service(session, settings).list_audit()
