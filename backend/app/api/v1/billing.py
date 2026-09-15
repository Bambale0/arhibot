from json import JSONDecodeError, loads
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.api.client import request_identity
from app.api.dependencies.auth import CurrentUser, DbSession
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.providers.yookassa import YooKassaError
from app.schemas.billing import BillingPaymentCreate, BillingPaymentResponse, BillingSummaryResponse
from app.schemas.errors import ProblemDetails
from app.services.billing_service import build_billing_service
from app.services.rate_limit_service import RateLimitService

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
        422: {"model": ProblemDetails, "description": "Receipt email is required."},
        429: {"model": ProblemDetails, "description": "Rate limit exceeded."},
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
    await RateLimitService(session).enforce("payment", str(user.id))
    return await build_billing_service(session, settings).create_payment(
        user,
        payload.package_code,
        receipt_email=str(payload.receipt_email) if payload.receipt_email else None,
    )


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
    source = request_identity(request)
    await RateLimitService(session).enforce_window(
        "yookassa-webhook",
        source,
        limit=settings.yookassa_webhook_rate_limit_per_minute,
        window_seconds=60,
    )
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise AppError(
            type="invalid_webhook_content_type",
            title="Invalid webhook content type",
            status=415,
            detail="YooKassa webhook must use application/json.",
        )
    raw = await request.body()
    if len(raw) > settings.yookassa_webhook_max_body_bytes:
        raise AppError(
            type="webhook_payload_too_large",
            title="Webhook payload too large",
            status=413,
            detail="YooKassa webhook payload exceeds the configured size limit.",
        )
    try:
        payload = loads(raw)
    except (JSONDecodeError, UnicodeDecodeError) as exc:
        raise AppError(
            type="invalid_webhook_payload",
            title="Invalid webhook payload",
            status=400,
            detail="YooKassa webhook payload must be valid JSON.",
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            type="invalid_webhook_payload",
            title="Invalid webhook payload",
            status=400,
            detail="YooKassa webhook payload must be a JSON object.",
        )
    try:
        await build_billing_service(session, settings).handle_webhook(payload)
    except YooKassaError:
        # Non-200 makes YooKassa retry the notification. Do not expose provider details.
        raise
    return {"ok": True}
