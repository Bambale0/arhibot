from fastapi import APIRouter

from app.api.dependencies.auth import DbSession
from app.schemas.telegram import TelegramContentResponse
from app.services.telegram_content_service import TelegramContentService

router = APIRouter(prefix="/telegram", tags=["Telegram"])


@router.get(
    "/content",
    response_model=TelegramContentResponse,
    operation_id="getTelegramContent",
    summary="Public Telegram bot content",
)
async def telegram_content(session: DbSession) -> TelegramContentResponse:
    return await TelegramContentService(session).get()
