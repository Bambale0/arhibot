from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    normalize_email,
    verify_password,
    verify_telegram_init_data,
)
from app.db.models.users import AuthIdentity, RefreshToken, User
from app.domain.users.enums import AuthProvider, UserStatus
from app.repositories.users import UserRepository
from app.schemas.auth import TokenPairResponse
from app.services.user_service import UserService


class AuthService:
    def __init__(self, repository: UserRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings
        self.user_service = UserService(repository)

    async def register(self, email: str, password: str, display_name: str) -> TokenPairResponse:
        normalized_email = normalize_email(email)
        if await self.repository.get_identity(AuthProvider.EMAIL, normalized_email):
            raise AppError(
                type="email_already_registered",
                title="Email already registered",
                status=409,
                detail="An account with this email already exists.",
            )

        user = User(display_name=display_name.strip())
        identity = AuthIdentity(
            user=user,
            provider=AuthProvider.EMAIL,
            provider_user_id=normalized_email,
            password_hash=hash_password(password),
        )
        self.repository.add_user(user)
        self.repository.add_identity(identity)
        try:
            await self.repository.session.flush()
            response = await self._issue_token_pair(user)
            await self.repository.session.commit()
            return response
        except IntegrityError as exc:
            await self.repository.session.rollback()
            raise AppError(
                type="email_already_registered",
                title="Email already registered",
                status=409,
                detail="An account with this email already exists.",
            ) from exc

    async def login(self, email: str, password: str) -> TokenPairResponse:
        normalized_email = normalize_email(email)
        identity = await self.repository.get_identity(AuthProvider.EMAIL, normalized_email)
        candidate_hash = (
            identity.password_hash if identity and identity.password_hash else DUMMY_PASSWORD_HASH
        )
        password_valid = verify_password(password, candidate_hash)
        if not identity or not identity.password_hash or not password_valid:
            raise AppError(
                type="invalid_credentials",
                title="Invalid credentials",
                status=401,
                detail="Email or password is incorrect.",
            )
        self._assert_user_active(identity.user)
        response = await self._issue_token_pair(identity.user)
        await self.repository.session.commit()
        return response

    async def authenticate_telegram(self, init_data: str) -> TokenPairResponse:
        telegram = verify_telegram_init_data(init_data, self.settings)
        identity = await self.repository.get_identity(AuthProvider.TELEGRAM, telegram.provider_user_id)
        if identity:
            self._assert_user_active(identity.user)
            user = identity.user
        else:
            user = User(display_name=telegram.display_name)
            identity = AuthIdentity(
                user=user,
                provider=AuthProvider.TELEGRAM,
                provider_user_id=telegram.provider_user_id,
            )
            self.repository.add_user(user)
            self.repository.add_identity(identity)
            try:
                await self.repository.session.flush()
            except IntegrityError:
                # Handles two concurrent first-logins for the same Telegram identity.
                await self.repository.session.rollback()
                identity = await self.repository.get_identity(
                    AuthProvider.TELEGRAM, telegram.provider_user_id
                )
                if not identity:
                    raise
                user = identity.user
                self._assert_user_active(user)

        response = await self._issue_token_pair(user)
        await self.repository.session.commit()
        return response

    async def refresh(self, raw_refresh_token: str) -> TokenPairResponse:
        now = datetime.now(UTC)
        token_hash = hash_refresh_token(raw_refresh_token, self.settings)
        stored = await self.repository.get_refresh_token_for_update(token_hash)
        if not stored:
            raise self._invalid_refresh_token()

        if stored.revoked_at is not None or stored.used_at is not None:
            await self.repository.revoke_token_family(stored.family_id, now)
            await self.repository.session.commit()
            raise AppError(
                type="refresh_token_reused",
                title="Refresh token reuse detected",
                status=401,
                detail="This refresh token has already been used. The token family was revoked.",
            )
        if stored.expires_at <= now:
            stored.revoked_at = now
            await self.repository.session.commit()
            raise self._invalid_refresh_token()

        user = await self.repository.get_user(stored.user_id)
        if not user:
            stored.revoked_at = now
            await self.repository.session.commit()
            raise self._invalid_refresh_token()
        self._assert_user_active(user)

        stored.used_at = now
        stored.revoked_at = now
        raw_new_token = generate_refresh_token()
        new_stored = RefreshToken(
            user_id=user.id,
            family_id=stored.family_id,
            token_hash=hash_refresh_token(raw_new_token, self.settings),
            expires_at=now + timedelta(seconds=self.settings.refresh_token_ttl_seconds),
        )
        self.repository.add_refresh_token(new_stored)
        await self.repository.session.flush()
        stored.replaced_by_token_id = new_stored.id

        access_token, expires_in = create_access_token(user.id, self.settings)
        await self.repository.session.commit()
        return TokenPairResponse(
            access_token=access_token,
            refresh_token=raw_new_token,
            expires_in=expires_in,
            user=self.user_service.to_response(user),
        )

    async def logout(self, raw_refresh_token: str) -> None:
        now = datetime.now(UTC)
        token_hash = hash_refresh_token(raw_refresh_token, self.settings)
        stored = await self.repository.get_refresh_token_for_update(token_hash)
        if stored:
            await self.repository.revoke_token_family(stored.family_id, now)
            await self.repository.session.commit()

    async def _issue_token_pair(self, user: User) -> TokenPairResponse:
        now = datetime.now(UTC)
        raw_refresh_token = generate_refresh_token()
        stored = RefreshToken(
            user_id=user.id,
            family_id=uuid4(),
            token_hash=hash_refresh_token(raw_refresh_token, self.settings),
            expires_at=now + timedelta(seconds=self.settings.refresh_token_ttl_seconds),
        )
        self.repository.add_refresh_token(stored)
        await self.repository.session.flush()
        access_token, expires_in = create_access_token(user.id, self.settings)
        return TokenPairResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_in=expires_in,
            user=self.user_service.to_response(user),
        )

    @staticmethod
    def _assert_user_active(user: User) -> None:
        if user.status != UserStatus.ACTIVE:
            raise AppError(
                type="account_disabled",
                title="Account disabled",
                status=403,
                detail="This account is disabled.",
            )

    @staticmethod
    def _invalid_refresh_token() -> AppError:
        return AppError(
            type="invalid_refresh_token",
            title="Invalid refresh token",
            status=401,
            detail="The refresh token is invalid or expired.",
        )
