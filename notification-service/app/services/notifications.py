from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import AuthUser
from app.exceptions import NotFound
from app.models import Notification


async def list_notifications(
    session: AsyncSession, user: AuthUser, unread_only: bool, limit: int, offset: int
) -> Sequence[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
    result = await session.scalars(stmt.limit(limit).offset(offset))
    return result.all()


async def mark_read(session: AsyncSession, user: AuthUser, notification_id: int) -> Notification:
    notification = await session.get(Notification, notification_id)
    # чужое уведомление — 404, чтобы не раскрывать его существование
    if notification is None or notification.user_id != user.id:
        raise NotFound("Notification not found")
    notification.is_read = True
    await session.commit()
    return notification


async def mark_all_read(session: AsyncSession, user: AuthUser) -> int:
    result = await session.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    await session.commit()
    return result.rowcount
