from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorItem(BaseModel):
    field: str | None = None
    code: str
    message: str


class ProblemDetails(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "examples": [
            {
                "type": "validation_error",
                "title": "Request validation failed",
                "status": 422,
                "detail": "One or more request fields are invalid.",
                "errors": [
                    {
                        "field": "building.width_m",
                        "code": "too_small",
                        "message": "Minimum value is 3.",
                    }
                ],
                "request_id": "d7b8c958-32cb-4d9c-af43-0ce90589a219",
            }
        ]
    })

    type: str
    title: str
    status: int
    detail: str | None = None
    errors: list[ErrorItem] = Field(default_factory=list)
    request_id: str | None = None
    meta: dict[str, Any] | None = None
