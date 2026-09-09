"""Read-only deployed runtime consistency checks.

The command intentionally reports only entity IDs and validation error paths/types;
it never prints project context values or user data.
"""

from __future__ import annotations

import asyncio

from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models.projects import Project
from app.db.models.users import AuthIdentity, User
from app.db.session import dispose_engine, get_session_factory
from app.domain.users.enums import AuthProvider, UserRole, UserStatus
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

    print(f"project_context_validation checked={checked} invalid={invalid}")
    return 1 if invalid else 0


async def validate_questionnaire_delivery_readiness() -> int:
    token_configured = bool((get_settings().telegram_bot_token or "").strip())
    async with get_session_factory()() as session:
        result = await session.execute(
            select(func.count())
            .select_from(AuthIdentity)
            .join(User, User.id == AuthIdentity.user_id)
            .where(
                AuthIdentity.provider == AuthProvider.TELEGRAM,
                User.status == UserStatus.ACTIVE,
                User.role.in_([UserRole.ADMIN, UserRole.SUPERADMIN]),
            )
        )
        recipient_count = int(result.scalar_one())

    ready = token_configured and recipient_count > 0
    print(
        "questionnaire_telegram_delivery "
        f"token_configured={str(token_configured).lower()} "
        f"admin_recipients={recipient_count} ready={str(ready).lower()}"
    )
    return 0 if ready else 1


async def run_checks() -> int:
    try:
        project_status = await validate_project_contexts()
        delivery_status = await validate_questionnaire_delivery_readiness()
        return 1 if project_status or delivery_status else 0
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_checks()))
