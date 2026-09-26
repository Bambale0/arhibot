from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.client import request_identity
from app.core.config import Settings, get_settings
from app.core.errors import AppError
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
REFRESH_COOKIE_NAME = "auroom_refresh_token"


def _service(session: AsyncSession, settings: Settings) -> AuthService:
    return AuthService(UserRepository(session), settings)


def _disable_auth_response_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _refresh_cookie_path(settings: Settings) -> str:
    return f"{settings.api_v1_prefix.rstrip('/')}/auth"


def _set_refresh_cookie(
    response: Response,
    token_pair: TokenPairResponse,
    settings: Settings,
) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token_pair.refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path=_refresh_cookie_path(settings),
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        path=_refresh_cookie_path(settings),
    )


def _refresh_token_from_request(
    request: Request,
    payload: RefreshTokenRequest | None,
) -> str:
    if payload is not None:
        return payload.refresh_token
    token = (request.cookies.get(REFRESH_COOKIE_NAME) or "").strip()
    if token:
        return token
    raise AppError(
        type="invalid_refresh_token",
        title="Invalid refresh token",
        status=401,
        detail="The refresh token is invalid or expired.",
    )


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
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPairResponse:
    limiter = RateLimitService(session)
    source = request_identity(request)
    await limiter.enforce("auth", f"register-ip:{source}")
    await limiter.enforce("auth", f"register-email:{payload.email.strip().lower()}")
    await limiter.enforce_registration_daily(source)
    _disable_auth_response_caching(response)
    pair = await _service(session, settings).register(
        payload.email, payload.password, payload.display_name
    )
    _set_refresh_cookie(response, pair, settings)
    return pair


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
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenPairResponse:
    limiter = RateLimitService(session)
    source = request_identity(request)
    await limiter.enforce("auth", f"login-ip:{source}")
    await limiter.enforce("auth", f"login-email:{payload.email.strip().lower()}")
    _disable_auth_response_caching(response)
    pair = await _service(session, settings).login(payload.email, payload.password)
    _set_refresh_cookie(response, pair, settings)
    return pair


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
    await RateLimitService(session).enforce("auth", f"telegram:{request_identity(request)}")
    _disable_auth_response_caching(response)
    pair = await _service(session, settings).authenticate_telegram(payload.init_data)
    _set_refresh_cookie(response, pair, settings)
    return pair


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
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    payload: RefreshTokenRequest | None = None,
) -> TokenPairResponse:
    raw_refresh_token = _refresh_token_from_request(request, payload)
    await RateLimitService(session).enforce("auth", f"refresh:{raw_refresh_token[:64]}")
    _disable_auth_response_caching(response)
    pair = await _service(session, settings).refresh(raw_refresh_token)
    _set_refresh_cookie(response, pair, settings)
    return pair


@router.post(
    "/logout",
    operation_id="logoutUser",
    summary="Logout a token family",
    description="Revokes the refresh-token family associated with the supplied refresh token.",
    response_model=LogoutResponse,
)
async def logout_user(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    payload: RefreshTokenRequest | None = None,
) -> LogoutResponse:
    _disable_auth_response_caching(response)
    raw_refresh_token = (
        payload.refresh_token
        if payload is not None
        else (request.cookies.get(REFRESH_COOKIE_NAME) or "").strip()
    )
    if raw_refresh_token:
        await _service(session, settings).logout(raw_refresh_token)
    _clear_refresh_cookie(response, settings)
    return LogoutResponse()
