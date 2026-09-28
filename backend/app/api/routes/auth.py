from fastapi import APIRouter, Depends, HTTPException, status

from app.api.schemas.auth import (
    LoginRequest,
    TokenResponse,
    UserResponse,
)
from app.security.dependencies import get_current_user
from app.security.jwt import create_access_token
from app.security.store import get_user, verify_password


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):

    user = get_user(request.username)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not verify_password(
        request.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = create_access_token(user)

    return TokenResponse(
        access_token=token,
    )


@router.get("/me", response_model=UserResponse)
async def me(
    user=Depends(get_current_user),
):
    return UserResponse(
        id=user.id,
        username=user.username,
        roles=user.roles,
    )