"""Проверки прав доступа к проектам. Вызываются из сервисов, а не из роутов."""

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import AuthUser
from app.exceptions import BadRequest, Forbidden, NotFound
from app.models import Project, ProjectMember, UserReplica


async def is_member(session: AsyncSession, project_id: int, user_id: int) -> bool:
    stmt = select(
        exists().where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
    )
    return bool(await session.scalar(stmt))


async def load_project(session: AsyncSession, project_id: int) -> Project:
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .execution_options(populate_existing=True)
    )
    project = await session.scalar(stmt)
    if project is None:
        raise NotFound("Project not found")
    return project


async def get_project_for_member(
    session: AsyncSession, project_id: int, user: AuthUser
) -> Project:
    """Проект, который пользователь может смотреть: участник, владелец или admin."""
    project = await load_project(session, project_id)
    if user.is_admin or project.owner_id == user.id:
        return project
    if not await is_member(session, project_id, user.id):
        raise Forbidden("You are not a member of this project")
    return project


async def get_project_for_owner(
    session: AsyncSession, project_id: int, user: AuthUser
) -> Project:
    """Проект, которым пользователь может управлять: владелец или admin."""
    project = await load_project(session, project_id)
    if not (user.is_admin or project.owner_id == user.id):
        raise Forbidden("Only the project owner or admin can do this")
    return project


async def ensure_assignable(session: AsyncSession, project_id: int, user_id: int) -> None:
    if not await is_member(session, project_id, user_id):
        raise BadRequest("Assignee must be a member of the project")


async def ensure_replica(session: AsyncSession, user: AuthUser) -> None:
    """Гарантирует строку в user_replicas для автора запроса (FK owner_id / creator_id).

    Обычно реплику создаёт событие user.registered; если оно ещё не дошло,
    создаём заглушку из данных токена — событие потом обновит имя.
    """
    stmt = (
        insert(UserReplica)
        .values(id=user.id, email=user.email, full_name=user.email.split("@")[0] or str(user.id))
        .on_conflict_do_nothing(index_elements=[UserReplica.id])
    )
    await session.execute(stmt)
