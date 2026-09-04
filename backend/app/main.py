from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.middleware.access_log import AccessLogMiddleware
from app.api.middleware.request_id import RequestIdMiddleware
from app.api.v1.router import router as api_v1_router
from app.core.config import get_settings
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging
from app.core.redis import redis_client
from app.db.session import dispose_engine

settings = get_settings()
configure_logging(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await redis_client.aclose()
    await dispose_engine()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Official backend contract for web, Telegram, admin, mobile, and future clients. "
        "Business logic lives behind application services rather than client-specific handlers."
    ),
    openapi_url="/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestIdMiddleware)

install_exception_handlers(app)
app.include_router(health_router)
app.include_router(api_v1_router, prefix=settings.api_v1_prefix)
