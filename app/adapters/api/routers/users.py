import os
from fastapi import APIRouter, Depends, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from app.application.dto.user import CreateUserRequest, UserResponse
from app.application.use_cases.manage_users import CreateUserUseCase, AuthenticateUserUseCase
from app.dependencies import get_create_user_use_case, get_authenticate_user_use_case

router = APIRouter()

_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))


@router.post("/users/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user: CreateUserRequest,
    use_case: CreateUserUseCase = Depends(get_create_user_use_case),
):
    """
    Create a new user.

    Args:
        user: User data to create
        use_case: Injected use case
    """
    return use_case.execute(user)


@router.post("/login")
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    use_case: AuthenticateUserUseCase = Depends(get_authenticate_user_use_case),
):
    """
    Authenticate a user and return a JWT in an HTTP-only cookie.

    Args:
        form_data: Login form data
        use_case: Injected use case
    """
    result = use_case.execute(form_data.username, form_data.password)

    response.set_cookie(
        key="access_token",
        value=f"Bearer {result['access_token']}",
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=_expire_minutes * 60,
    )

    return {"detail": "Login successful"}
