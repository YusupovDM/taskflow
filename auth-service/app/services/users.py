from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFound
from app.models import User, UserRole


async def list_users(session: AsyncSession, limit: int, offset: int) -> Sequence[User]:
    result = await session.scalars(select(User).order_by(User.id).limit(limit).offset(offset))
    return result.all()


async def change_role(session: AsyncSession, user_id: int, role: UserRole) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFound("User not found")
    user.role = role
    await session.commit()
    return user
