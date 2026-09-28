from datetime import datetime, timedelta, timezone

import jwt

from app.security.models import User
from app.core.config import settings

JWT_SECRET = settings.speed_jwt_secret
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "sub": user.id,
        "username": user.username,
        "roles": user.roles,
        "iat": now,
        "exp": now + timedelta(
            minutes=JWT_EXPIRE_MINUTES
        ),
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[JWT_ALGORITHM],
    )