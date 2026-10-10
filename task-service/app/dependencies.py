from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import Cache
from app.database import get_session
from app.exceptions import NotAuthenticated
from app.messaging import EventPublisher
from app.security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@dataclass(frozen=True)
class AuthUser:
    """Пользователь из JWT. В БД task-service за ним не ходим."""

    id: int
    email: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def get_publisher(request: Request) -> EventPublisher:
    return request.app.state.publisher


PublisherDep = Annotated[EventPublisher, Depends(get_publisher)]


def get_cache(request: Request) -> Cache:
    return request.app.state.cache


CacheDep = Annotated[Cache, Depends(get_cache)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthUser:
    if credentials is None:
        raise NotAuthenticated()
    try:
        payload = decode_token(credentials.credentials)
        return AuthUser(
            id=int(payload["sub"]), email=payload.get("email", ""), role=payload.get("role", "user")
        )
    except (jwt.PyJWTError, ValueError):
        raise NotAuthenticated("Invalid or expired token") from None


CurrentUser = Annotated[AuthUser, Depends(get_current_user)]
