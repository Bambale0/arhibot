from app.core.errors import AppError
from app.db.models.users import User
from app.domain.users.enums import UserStatus
from app.repositories.users import UserRepository
from app.schemas.users import CurrentUserResponse, UpdateCurrentUserRequest, UserCapabilities


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    def to_response(self, user: User) -> CurrentUserResponse:
        return CurrentUserResponse(
            id=user.id,
            display_name=user.display_name,
            avatar_url=None,
            status=user.status,
            credits_balance=user.credits_balance,
            created_at=user.created_at,
            updated_at=user.updated_at,
            capabilities=UserCapabilities(can_generate=user.status == UserStatus.ACTIVE),
        )

    async def update_current_user(
        self, user: User, payload: UpdateCurrentUserRequest
    ) -> CurrentUserResponse:
        display_name = payload.display_name.strip()
        if not display_name:
            raise AppError(
                type="validation_error",
                title="Request validation failed",
                status=422,
                detail="Display name must not be blank.",
            )
        user.display_name = display_name
        await self.repository.session.commit()
        await self.repository.session.refresh(user)
        return self.to_response(user)
