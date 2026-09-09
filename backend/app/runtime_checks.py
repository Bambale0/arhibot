"""Read-only deployed runtime consistency checks.

The command intentionally reports only entity IDs and validation error paths/types;
it never prints project context values or user data.
"""

from __future__ import annotations

import asyncio

from pydantic import ValidationError
from sqlalchemy import select

from app.db.models.projects import Project
from app.db.session import dispose_engine, get_session_factory
from app.schemas.projects import ProjectContextResponse


async def validate_project_contexts() -> int:
    checked = 0
    invalid = 0
    async with get_session_factory()() as session:
        result = await session.execute(
            select(Project.id, Project.context).where(Project.deleted_at.is_(None))
        )
        for project_id, raw_context in result.all():
            checked += 1
            try:
                ProjectContextResponse.model_validate(raw_context or {})
            except ValidationError as exc:
                invalid += 1
                print(f"invalid_project_context project_id={project_id}")
                for error in exc.errors(include_input=False, include_url=False):
                    location = ".".join(str(part) for part in error.get("loc", ())) or "context"
                    print(f"  field={location} type={error.get('type', 'validation_error')}")
                if invalid >= 50:
                    print("stopping_after=50_invalid_projects")
                    break

    await dispose_engine()
    print(f"project_context_validation checked={checked} invalid={invalid}")
    return 1 if invalid else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(validate_project_contexts()))
