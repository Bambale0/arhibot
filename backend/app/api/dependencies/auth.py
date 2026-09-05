from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.db.models.users import User
from app.db.session import get_db_session
from app.domain.users.enums import UserRole, UserStatus
from app.repositories.users import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise AppError(
            type="authentication_required",
            title="Authentication required",
            status=401,
            detail="A bearer access token is required.",
        )
    user_id = decode_access_token(credentials.credentials, settings)
    user = await UserRepository(session).get_user(user_id)
    if not user:
        raise AppError(
            type="invalid_access_token",
            title="Invalid access token",
            status=401,
            detail="The access token is invalid or expired.",
        )
    if user.status != UserStatus.ACTIVE:
        raise AppError(
            type="account_disabled",
            title="Account disabled",
            status=403,
            detail="This account is disabled.",
        )
    return user


async def get_current_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role not in {UserRole.ADMIN, UserRole.SUPERADMIN}:
        raise AppError(
            type="admin_access_required",
            title="Admin access required",
            status=403,
            detail="This operation is available only to AuRoom administrators.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(get_current_admin)]
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
