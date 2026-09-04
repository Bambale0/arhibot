from dataclasses import dataclass, field
from typing import Any

import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import get_request_id
from app.schemas.errors import ErrorItem, ProblemDetails

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppError(Exception):
    type: str
    title: str
    status: int
    detail: str | None = None
    errors: list[ErrorItem] = field(default_factory=list)
    meta: dict[str, Any] | None = None


def problem_response(problem: ProblemDetails) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if problem.status == 401 else None
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json"),
        media_type="application/problem+json",
        headers=headers,
    )


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return problem_response(
            ProblemDetails(
                type=exc.type,
                title=exc.title,
                status=exc.status,
                detail=exc.detail,
                errors=exc.errors,
                request_id=get_request_id(),
                meta=exc.meta,
            )
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors: list[ErrorItem] = []
        for error in exc.errors():
            location = [
                str(part) for part in error.get("loc", ()) if part not in {"body", "query", "path"}
            ]
            errors.append(
                ErrorItem(
                    field=".".join(location) or None,
                    code=str(error.get("type", "invalid")),
                    message=str(error.get("msg", "Invalid value")),
                )
            )
        return problem_response(
            ProblemDetails(
                type="validation_error",
                title="Request validation failed",
                status=422,
                detail="One or more request fields are invalid.",
                errors=errors,
                request_id=get_request_id(),
            )
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem_response(
            ProblemDetails(
                type="http_error",
                title="HTTP error",
                status=exc.status_code,
                detail=str(exc.detail),
                request_id=get_request_id(),
            )
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", extra={"error": str(exc)})
        return problem_response(
            ProblemDetails(
                type="internal_error",
                title="Internal server error",
                status=500,
                detail="An unexpected error occurred.",
                request_id=get_request_id(),
            )
        )
