from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.config import Settings, get_settings
from app.providers.yookassa import YooKassaError
from app.schemas.billing import BillingPaymentCreate, BillingPaymentResponse, BillingSummaryResponse
from app.schemas.errors import ProblemDetails
from app.services.billing_service import build_billing_service

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get(
    "",
    response_model=BillingSummaryResponse,
    operation_id="getBillingSummary",
    summary="Get billing summary",
)
async def billing_summary(
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> BillingSummaryResponse:
    return await build_billing_service(session, settings).summary(user)


@router.post(
    "/payments",
    response_model=BillingPaymentResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createBillingPayment",
    summary="Create YooKassa payment",
    responses={
        404: {"model": ProblemDetails, "description": "Billing package not found."},
        502: {"model": ProblemDetails, "description": "YooKassa unavailable."},
        503: {"model": ProblemDetails, "description": "Billing not configured."},
    },
)
async def create_billing_payment(
    payload: BillingPaymentCreate,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> BillingPaymentResponse:
    return await build_billing_service(session, settings).create_payment(user, payload.package_code)


@router.get(
    "/payments/{payment_id}",
    response_model=BillingPaymentResponse,
    operation_id="getBillingPayment",
    summary="Get and reconcile payment",
)
async def get_billing_payment(
    payment_id: UUID,
    user: CurrentUser,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> BillingPaymentResponse:
    return await build_billing_service(session, settings).get_owned_and_sync(user, payment_id)


@router.post(
    "/webhooks/yookassa",
    status_code=status.HTTP_200_OK,
    operation_id="receiveYooKassaWebhook",
    summary="Receive YooKassa webhook",
    include_in_schema=True,
)
async def yookassa_webhook(
    request: Request,
    session: DbSession,
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    payload = await request.json()
    try:
        await build_billing_service(session, settings).handle_webhook(payload)
    except YooKassaError:
        # Non-200 makes YooKassa retry the notification. Do not expose provider details.
        raise
    return {"ok": True}
