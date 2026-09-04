from app.main import app


def test_openapi_has_stable_operation_ids() -> None:
    schema = app.openapi()
    operations = []
    for path in schema["paths"].values():
        for method, operation in path.items():
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                operations.append(operation["operationId"])

    assert len(operations) == len(set(operations))
    expected = {
        "getLiveness",
        "getReadiness",
        "getApiV1Info",
        "registerUser",
        "loginUser",
        "authenticateWithTelegram",
        "refreshAccessToken",
        "logoutUser",
        "getCurrentUser",
        "updateCurrentUser",
        "createProject",
        "listProjects",
        "getProject",
        "updateProject",
        "deleteProject",
        "uploadAsset",
        "getAsset",
        "deleteAsset",
    }
    assert expected.issubset(set(operations))


def test_openapi_routes_are_published() -> None:
    schema = app.openapi()
    expected_paths = {
        "/health/live",
        "/health/ready",
        "/api/v1",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/telegram",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/me",
        "/api/v1/projects",
        "/api/v1/projects/{project_id}",
        "/api/v1/assets",
        "/api/v1/assets/{asset_id}",
    }
    assert expected_paths.issubset(set(schema["paths"]))


def test_secured_me_endpoint_declares_bearer_auth() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/api/v1/me"]["get"]
    assert operation["security"]
    assert "HTTPBearer" in schema["components"]["securitySchemes"]
