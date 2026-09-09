from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.projects.enums import ProjectStatus
from app.schemas.projects import ProjectContext, ProjectContextResponse, ProjectResponse


def legacy_context() -> dict:
    return {
        "house_area_m2": 180,
        "floors": 2,
        "garage_cars": 2,
        "pool": True,
        "attic": False,
        "glazed_veranda": True,
        "smoke_test": "historical-internal-key",
    }


def test_project_context_response_preserves_known_legacy_fields_and_ignores_internal_keys() -> None:
    context = ProjectContextResponse.model_validate(legacy_context())
    payload = context.model_dump(exclude_none=True)

    assert payload["garage_cars"] == 2
    assert payload["pool"] is True
    assert payload["attic"] is False
    assert payload["glazed_veranda"] is True
    assert "smoke_test" not in payload


def test_project_context_write_contract_remains_strict() -> None:
    with pytest.raises(ValidationError):
        ProjectContext.model_validate({"smoke_test": True})

    context = ProjectContext.model_validate(
        {"garage_cars": 1, "pool": False, "attic": True, "glazed_veranda": False}
    )
    assert context.garage_cars == 1


def test_project_response_does_not_fail_on_historical_extra_context_keys() -> None:
    now = datetime.now(UTC)
    response = ProjectResponse.model_validate(
        {
            "id": uuid4(),
            "name": "Legacy project",
            "description": None,
            "status": ProjectStatus.ACTIVE,
            "context": legacy_context(),
            "created_at": now,
            "updated_at": now,
        }
    )

    assert response.context.pool is True
    assert response.context.garage_cars == 2
    assert "smoke_test" not in response.context.model_dump()
