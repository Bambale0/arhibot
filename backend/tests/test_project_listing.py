from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.repositories.projects import ProjectRepository


class EmptyScalarResult:
    def scalars(self):
        return self

    def all(self) -> list:
        return []


class CaptureSession:
    def __init__(self) -> None:
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return EmptyScalarResult()


@pytest.mark.asyncio
async def test_project_repository_can_page_owned_projects_by_updated_at() -> None:
    session = CaptureSession()
    cursor_at = datetime(2026, 9, 16, 10, 30, tzinfo=UTC)

    await ProjectRepository(session).list_owned(
        uuid4(),
        limit=51,
        cursor_at=cursor_at,
        cursor_id=uuid4(),
        sort_by="updated_at",
    )

    compiled = str(session.statement)
    assert "projects.updated_at <" in compiled
    assert "ORDER BY projects.updated_at DESC, projects.id DESC" in compiled
