from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.users import AuthIdentity, RefreshToken, User
from app.domain.users.enums import AuthProvider


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_user_with_identities(self, user_id: UUID) -> User | None:
        result = await self.session.execute(
            select(User).options(selectinload(User.identities)).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_identity(self, provider: AuthProvider, provider_user_id: str) -> AuthIdentity | None:
        result = await self.session.execute(
            select(AuthIdentity)
            .options(selectinload(AuthIdentity.user))
            .where(
                AuthIdentity.provider == provider,
                AuthIdentity.provider_user_id == provider_user_id,
            )
        )
        return result.scalar_one_or_none()

    def add_user(self, user: User) -> None:
        self.session.add(user)

    def add_identity(self, identity: AuthIdentity) -> None:
        self.session.add(identity)

    def add_refresh_token(self, token: RefreshToken) -> None:
        self.session.add(token)

    async def get_refresh_token_for_update(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def revoke_token_family(self, family_id: UUID, revoked_at: datetime) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
