from typing import Annotated

from fastapi import APIRouter, Query

from app.dependencies import AdminUser, SessionDep
from app.schemas import RoleUpdate, UserRead
from app.schemas.errors import error_responses
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    response_model=list[UserRead],
    summary="Список пользователей (только admin)",
    responses=error_responses(401, 403),
)
async def list_users(
    _: AdminUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await users_service.list_users(session, limit, offset)


@router.patch(
    "/{user_id}/role",
    response_model=UserRead,
    summary="Изменить роль пользователя (только admin)",
    responses=error_responses(401, 403, 404),
)
async def change_role(user_id: int, data: RoleUpdate, _: AdminUser, session: SessionDep):
    return await users_service.change_role(session, user_id, data.role)
