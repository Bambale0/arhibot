from fastapi import APIRouter

from app.api.dependencies.auth import CurrentUser, DbSession
from app.repositories.users import UserRepository
from app.schemas.errors import ProblemDetails
from app.schemas.users import CurrentUserResponse, UpdateCurrentUserRequest
from app.services.user_service import UserService

router = APIRouter(tags=["Users"])


@router.get(
    "/me",
    operation_id="getCurrentUser",
    summary="Get current user",
    description="Returns the platform user associated with the bearer access token.",
    response_model=CurrentUserResponse,
    responses={401: {"model": ProblemDetails, "description": "Authentication required."}},
)
async def get_current_user_profile(user: CurrentUser, session: DbSession) -> CurrentUserResponse:
    return UserService(UserRepository(session)).to_response(user)


@router.patch(
    "/me",
    operation_id="updateCurrentUser",
    summary="Update current user",
    description="Updates editable profile fields for the current platform user.",
    response_model=CurrentUserResponse,
    responses={
        401: {"model": ProblemDetails, "description": "Authentication required."},
        422: {"model": ProblemDetails, "description": "Invalid profile data."},
    },
)
async def update_current_user_profile(
    payload: UpdateCurrentUserRequest,
    user: CurrentUser,
    session: DbSession,
) -> CurrentUserResponse:
    return await UserService(UserRepository(session)).update_current_user(user, payload)
