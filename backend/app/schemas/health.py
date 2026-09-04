from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"


class DependencyStatus(StrEnum):
    OK = "ok"
    ERROR = "error"


class LiveHealthResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"status": "ok"}]})
    status: HealthStatus


class ReadyHealthResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "ok",
                    "dependencies": {"database": "ok", "redis": "ok"},
                }
            ]
        }
    )
    status: HealthStatus
    dependencies: dict[str, DependencyStatus]
