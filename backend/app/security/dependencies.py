from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.security.jwt import decode_access_token
from app.security.models import Permission, User
from app.security.store import get_user, get_user_permissions
from app.core.config import settings


bearer_scheme = HTTPBearer(auto_error=False)
DEMO_PRINCIPAL_ID = "speed-demo-admin"


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    demo_user: str | None = Header(default=None, alias="X-Speed-Demo-User"),
) -> User:
    if demo_user is not None:
        if not settings.speed_demo_auth or demo_user != DEMO_PRINCIPAL_ID:
            raise HTTPException(status_code=401, detail="Demo authentication unavailable")
        return User(id=DEMO_PRINCIPAL_ID, username="admin", roles=["admin"], password_hash="unused")

    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_access_token(
            credentials.credentials
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    username = payload.get("username")

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user = get_user(username)

    if user is None or user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


def require_permission(permission: Permission):
    def dependency(
        user: User = Depends(get_current_user),
    ) -> User:

        permissions = get_user_permissions(user)

        if permission not in permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PERMISSION_DENIED",
                    "permission": permission.value,
                },
            )

        return user

    return dependency
