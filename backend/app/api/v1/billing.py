from ipaddress import ip_address, ip_network
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from pydantic import ValidationError

from app.api.dependencies.auth import CurrentUser, DbSession
from app.api.request_identity import request_ip
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.providers.yookassa import YooKassaError
from app.schemas.billing import (
    BillingPaymentCreate,
    BillingPaymentResponse,
    BillingSummaryResponse,
    YooKassaWebhookNotification,
)
from app.schemas.errors import ProblemDetails
from app.services.billing_service import build_billing_service
from app.services.rate_limit_service import RateLimitService

router = APIRouter(prefix="/billing", tags=["Billing"])

# Current official YooKassa webhook source ranges:
# https://yookassa.ru/developers/using-api/webhooks
YOOKASSA_WEBHOOK_NETWORKS = tuple(
    ip_network(value)
    for value in (
        "185.71.76.0/27",
        "185.71.77.0/27",
        "77.75.153.0/25",
        "77.75.156.11/32",
        "77.75.156.35/32",
        "77.75.154.128/25",
        "2a02:5180::/32",
    )
)
YOOKASSA_WEBHOOK_MAX_BODY_BYTES = 64 * 1024


def _is_yookassa_webhook_ip(value: str) -> bool:
    try:
        address = ip_address(value)
    except ValueError:
        return False
    if getattr(address, "ipv4_mapped", None) is not None:
        address = address.ipv4_mapped
    return any(address in network for network in YOOKASSA_WEBHOOK_NETWORKS)




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
    source_ip = request_ip(request)
    if not _is_yookassa_webhook_ip(source_ip):
        raise AppError(
            type="yookassa_webhook_source_rejected",
            title="Webhook source rejected",
            status=403,
            detail="The webhook source is not trusted.",
        )

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = YOOKASSA_WEBHOOK_MAX_BODY_BYTES + 1
        if declared_size > YOOKASSA_WEBHOOK_MAX_BODY_BYTES:
            raise AppError(
                type="webhook_payload_too_large",
                title="Webhook payload too large",
                status=413,
                detail="The webhook payload exceeds the allowed size.",
            )

    await RateLimitService.enforce_fixed(
        "yookassa-webhook-ip",
        source_ip,
        limit=120,
    )
    await RateLimitService.enforce_fixed(
        "yookassa-webhook-global",
        "global",
        limit=600,
    )

    raw = await request.body()
    if len(raw) > YOOKASSA_WEBHOOK_MAX_BODY_BYTES:
        raise AppError(
            type="webhook_payload_too_large",
            title="Webhook payload too large",
            status=413,
            detail="The webhook payload exceeds the allowed size.",
        )
    try:
        payload = YooKassaWebhookNotification.model_validate_json(raw)
    except ValidationError as exc:
        raise AppError(
            type="invalid_yookassa_webhook",
            title="Invalid YooKassa webhook",
            status=422,
            detail="The webhook payload is malformed.",
        ) from exc

    try:
        await build_billing_service(session, settings).handle_webhook(payload)
    except YooKassaError:
        # Non-200 makes YooKassa retry the notification. Do not expose provider details.
        raise
    return {"ok": True}
