from secrets import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.dependencies.auth import DbSession
from app.core.config import Settings, get_settings
from app.schemas.telegram import TelegramContentResponse, TelegramUserSummaryResponse
from app.services.telegram_content_service import TelegramContentService
from app.services.telegram_user_summary_service import TelegramUserSummaryService

router = APIRouter(prefix="/telegram", tags=["Telegram"])


@router.get(
    "/content",
    response_model=TelegramContentResponse,
    operation_id="getTelegramContent",
    summary="Public Telegram bot content",
)
async def telegram_content(session: DbSession) -> TelegramContentResponse:
    return await TelegramContentService(session).get()


@router.get(
    "/summary/{telegram_user_id}",
    response_model=TelegramUserSummaryResponse,
    include_in_schema=False,
)
async def telegram_user_summary(
    telegram_user_id: str,
    session: DbSession,
    x_telegram_bot_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> TelegramUserSummaryResponse:
    configured = (settings.telegram_bot_token or "").strip()
    supplied = (x_telegram_bot_token or "").strip()
    if not configured or not supplied or not compare_digest(configured, supplied):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    summary = await TelegramUserSummaryService(session).get(telegram_user_id)
    if summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return summary
