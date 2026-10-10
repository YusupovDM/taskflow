from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, SessionDep
from app.schemas import NotificationRead, ReadAllResult
from app.services import notifications as notifications_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    user: CurrentUser,
    session: SessionDep,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await notifications_service.list_notifications(
        session, user, unread_only, limit, offset
    )


@router.patch("/{notification_id}/read", response_model=NotificationRead)
async def mark_read(notification_id: int, user: CurrentUser, session: SessionDep):
    return await notifications_service.mark_read(session, user, notification_id)


@router.post("/read-all", response_model=ReadAllResult)
async def mark_all_read(user: CurrentUser, session: SessionDep):
    return ReadAllResult(updated=await notifications_service.mark_all_read(session, user))
