from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.exceptions import Forbidden, NotAuthenticated
from app.messaging import EventPublisher
from app.models import User, UserRole
from app.security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_publisher(request: Request) -> EventPublisher:
    return request.app.state.publisher


PublisherDep = Annotated[EventPublisher, Depends(get_publisher)]


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None:
        raise NotAuthenticated()
    try:
        payload = decode_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        raise NotAuthenticated("Invalid or expired token") from None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise NotAuthenticated("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != UserRole.ADMIN:
        raise Forbidden()
    return user


AdminUser = Annotated[User, Depends(require_admin)]
