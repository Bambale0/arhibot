from fastapi import APIRouter, Response
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.metrics import metrics_payload, refresh_runtime_metrics
from app.core.redis import redis_client
from app.db.session import get_engine
from app.schemas.errors import ProblemDetails
from app.schemas.health import (
    DependencyStatus,
    HealthStatus,
    LiveHealthResponse,
    ReadyHealthResponse,
    VersionHealthResponse,
)

router = APIRouter(tags=["Health"])


@router.get(
    "/health/live",
    operation_id="getLiveness",
    summary="Liveness probe",
    description="Returns success when the API process is alive. Does not call external dependencies.",
    response_model=LiveHealthResponse,
)
async def liveness() -> LiveHealthResponse:
    return LiveHealthResponse(status=HealthStatus.OK)


@router.get(
    "/health/ready",
    operation_id="getReadiness",
    summary="Readiness probe",
    description="Checks critical infrastructure dependencies: PostgreSQL and Redis.",
    response_model=ReadyHealthResponse,
    responses={503: {"model": ProblemDetails, "description": "A critical dependency is unavailable."}},
)
async def readiness() -> ReadyHealthResponse:
    dependencies: dict[str, DependencyStatus] = {
        "database": DependencyStatus.OK,
        "redis": DependencyStatus.OK,
    }

    try:
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        dependencies["database"] = DependencyStatus.ERROR

    try:
        await redis_client.ping()
    except Exception:
        dependencies["redis"] = DependencyStatus.ERROR

    if DependencyStatus.ERROR in dependencies.values():
        raise AppError(
            type="service_not_ready",
            title="Service is not ready",
            status=503,
            detail="One or more critical dependencies are unavailable.",
            meta={"dependencies": {key: value.value for key, value in dependencies.items()}},
        )

    return ReadyHealthResponse(status=HealthStatus.OK, dependencies=dependencies)


@router.get(
    "/health/version",
    operation_id="getVersionHealth",
    summary="Release identity",
    response_model=VersionHealthResponse,
)
async def version_health() -> VersionHealthResponse:
    settings = get_settings()
    return VersionHealthResponse(
        app_version=settings.app_version,
        release_sha=settings.release_sha,
        environment=settings.app_env,
    )


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    settings = get_settings()
    await refresh_runtime_metrics(release_sha=settings.release_sha)
    payload, media_type = metrics_payload()
    return Response(content=payload, media_type=media_type)
