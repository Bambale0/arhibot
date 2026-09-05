from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.repositories.users import UserRepository
from app.schemas.auth import (
    LoginRequest,
    LogoutResponse,
    RefreshTokenRequest,
    RegisterRequest,
    TelegramAuthRequest,
    TokenPairResponse,
)
from app.schemas.errors import ProblemDetails
from app.services.auth_service import AuthService
from app.services.rate_limit_service import RateLimitService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _service(session: AsyncSession, settings: Settings) -> AuthService:
    return AuthService(UserRepository(session), settings)


def _disable_auth_response_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _request_identity(request: Request) -> str:
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",", maxsplit=1)[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


@router.post(
    "/register",
    operation_id="registerUser",
    summary="Register with email",
    description="Creates a platform user and an email auth identity, then issues platform tokens.",
    response_model=TokenPairResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ProblemDetails, "description": "Email is already registered."}, 429: {"model": ProblemDetails, "description": "Rate limit exceeded."}},
)
async def register_user(
    payload: RegisterRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPairResponse:
    await RateLimitService(session).enforce("auth", f"register:{payload.email.strip().lower()}")
    _disable_auth_response_caching(response)
    return await _service(session, settings).register(
        payload.email, payload.password, payload.display_name
    )


@router.post(
    "/login",
    operation_id="loginUser",
    summary="Login with email",
    description="Authenticates an email identity and issues a new access/refresh token pair.",
    response_model=TokenPairResponse,
    responses={401: {"model": ProblemDetails, "description": "Invalid credentials."}, 429: {"model": ProblemDetails, "description": "Rate limit exceeded."}},
)
async def login_user(
    payload: LoginRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPairResponse:
    await RateLimitService(session).enforce("auth", f"login:{payload.email.strip().lower()}")
    _disable_auth_response_caching(response)
    return await _service(session, settings).login(payload.email, payload.password)


@router.post(
    "/telegram",
    operation_id="authenticateWithTelegram",
    summary="Authenticate with Telegram Mini App",
    description=(
        "Validates Telegram WebApp initData, finds or creates the Telegram auth identity, "
        "and issues platform access/refresh tokens. Telegram is not used to authorize later API calls."
    ),
    response_model=TokenPairResponse,
    responses={
        401: {"model": ProblemDetails, "description": "Invalid or expired Telegram initData."},
        429: {"model": ProblemDetails, "description": "Rate limit exceeded."},
        503: {"model": ProblemDetails, "description": "Telegram authentication is not configured."},
    },
)
async def authenticate_with_telegram(
    payload: TelegramAuthRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPairResponse:
    await RateLimitService(session).enforce("auth", f"telegram:{_request_identity(request)}")
    _disable_auth_response_caching(response)
    return await _service(session, settings).authenticate_telegram(payload.init_data)


@router.post(
    "/refresh",
    operation_id="refreshAccessToken",
    summary="Rotate refresh token",
    description=(
        "Consumes a refresh token exactly once, rotates it, and returns a fresh access/refresh pair. "
        "Detected token reuse revokes the entire refresh-token family."
    ),
    response_model=TokenPairResponse,
    responses={401: {"model": ProblemDetails, "description": "Invalid, expired, or reused token."}, 429: {"model": ProblemDetails, "description": "Rate limit exceeded."}},
)
async def refresh_access_token(
    payload: RefreshTokenRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPairResponse:
    await RateLimitService(session).enforce("auth", f"refresh:{payload.refresh_token[:64]}")
    _disable_auth_response_caching(response)
    return await _service(session, settings).refresh(payload.refresh_token)


@router.post(
    "/logout",
    operation_id="logoutUser",
    summary="Logout a token family",
    description="Revokes the refresh-token family associated with the supplied refresh token.",
    response_model=LogoutResponse,
)
async def logout_user(
    payload: RefreshTokenRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LogoutResponse:
    _disable_auth_response_caching(response)
    await _service(session, settings).logout(payload.refresh_token)
    return LogoutResponse()
