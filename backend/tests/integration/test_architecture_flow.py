import os
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.integration

if os.getenv("RUN_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "set RUN_INTEGRATION_TESTS=1 with a migrated test database", allow_module_level=True
    )

from app.main import app  # noqa: E402


def _architecture_payload() -> dict:
    return {
        "schema_version": "1.0",
        "program": {"living_area_sqm": 120, "storeys": 1, "bedrooms": 2, "bathrooms": 1},
        "appearance": {"architecture_style": "fachwerk", "primary_material": "brick"},
        "geometry": {
            "levels": [
                {
                    "id": "ground",
                    "label": "GROUND FLOOR",
                    "z": 0,
                    "height": 3.2,
                    "footprint": {
                        "points": [
                            {"x": 0, "y": 0},
                            {"x": 12, "y": 0},
                            {"x": 12, "y": 10},
                            {"x": 0, "y": 10},
                        ]
                    },
                    "rooms": [
                        {
                            "id": "living",
                            "name": "Living room",
                            "kind": "living",
                            "polygon": {
                                "points": [
                                    {"x": 0, "y": 0},
                                    {"x": 6, "y": 0},
                                    {"x": 6, "y": 5},
                                    {"x": 0, "y": 5},
                                ]
                            },
                        }
                    ],
                }
            ],
            "external_objects": [
                {
                    "id": "pool",
                    "label": "Outdoor pool",
                    "type": "pool",
                    "z": 0,
                    "height": 0.05,
                    "polygon": {
                        "points": [
                            {"x": 14, "y": 1},
                            {"x": 20, "y": 1},
                            {"x": 20, "y": 5},
                            {"x": 14, "y": 5},
                        ]
                    },
                }
            ],
            "roof": {
                "type": "gable",
                "eave_z": 3.2,
                "ridge_z": 6.0,
                "ridge_start": {"x": 6, "y": 0},
                "ridge_end": {"x": 6, "y": 10},
            },
        },
    }


@pytest.mark.asyncio
async def test_architecture_package_survives_project_context_updates() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        register = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"architecture-{uuid4()}@example.com",
                "password": "integration-test-password-123",
                "display_name": "Architecture Test",
            },
        )
        assert register.status_code == 201, register.text
        headers = {"Authorization": f"Bearer {register.json()['access_token']}"}

        project = await client.post(
            "/api/v1/projects",
            headers=headers,
            json={"name": "Canonical house", "context": {"house_area_m2": 120, "floors": 1}},
        )
        assert project.status_code == 201, project.text
        project_id = project.json()["id"]

        saved = await client.put(
            f"/api/v1/projects/{project_id}/architecture",
            headers=headers,
            json=_architecture_payload(),
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["validation"]["valid"] is True

        plan = await client.get(
            f"/api/v1/projects/{project_id}/architecture/plan.svg", headers=headers
        )
        assert plan.status_code == 200, plan.text
        assert 'data-source="canonical-geometry"' in plan.text
        assert "GROUND FLOOR" in plan.text

        massing = await client.get(
            f"/api/v1/projects/{project_id}/architecture/massing.svg", headers=headers
        )
        assert massing.status_code == 200, massing.text
        assert 'data-source="canonical-geometry"' in massing.text

        updated = await client.patch(
            f"/api/v1/projects/{project_id}",
            headers=headers,
            json={"context": {"house_area_m2": 125, "floors": 1}},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["context"]["house_area_m2"] == 125
        assert updated.json()["context"]["architecture"]["schema_version"] == "1.0"

        architecture = await client.get(
            f"/api/v1/projects/{project_id}/architecture", headers=headers
        )
        assert architecture.status_code == 200, architecture.text
        assert architecture.json()["geometry"]["levels"][0]["id"] == "ground"
