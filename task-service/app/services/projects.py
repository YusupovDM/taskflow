from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cache import Cache, project_key
from app.config import settings
from app.dependencies import AuthUser
from app.exceptions import BadRequest, Conflict, NotFound
from app.models import Project, ProjectMember, Task, UserReplica
from app.schemas import MemberRead, ProjectCreate, ProjectDetail, ProjectRead, ProjectUpdate
from app.services.access import (
    ensure_replica,
    get_project_for_member,
    get_project_for_owner,
    is_member,
)


async def _project_detail(session: AsyncSession, project_id: int) -> ProjectDetail:
    stmt = (
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.members).selectinload(ProjectMember.user))
        .execution_options(populate_existing=True)
    )
    project = await session.scalar(stmt)
    if project is None:
        raise NotFound("Project not found")
    members = [
        MemberRead(
            user_id=m.user_id, email=m.user.email, full_name=m.user.full_name, joined_at=m.joined_at
        )
        for m in sorted(project.members, key=lambda m: (m.joined_at, m.id))
    ]
    return ProjectDetail(
        **ProjectRead.model_validate(project).model_dump(), members=members
    )


async def create_project(
    session: AsyncSession, user: AuthUser, data: ProjectCreate
) -> ProjectDetail:
    await ensure_replica(session, user)
    project = Project(name=data.name, description=data.description, owner_id=user.id)
    project.members.append(ProjectMember(user_id=user.id))  # владелец — тоже участник
    session.add(project)
    await session.commit()
    return await _project_detail(session, project.id)


async def list_projects(
    session: AsyncSession, user: AuthUser, limit: int, offset: int
) -> list[ProjectRead]:
    stmt = select(Project).order_by(Project.id).limit(limit).offset(offset)
    if not user.is_admin:
        my_projects = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
        stmt = stmt.where(Project.id.in_(my_projects))
    projects = await session.scalars(stmt)
    return [ProjectRead.model_validate(p) for p in projects]


async def get_project(
    session: AsyncSession, cache: Cache, user: AuthUser, project_id: int
) -> ProjectDetail:
    # права проверяем ДО кэша: в кэше данные, а не решение о доступе
    await get_project_for_member(session, project_id, user)
    key = project_key(project_id)
    cached = await cache.get_json(key)
    if cached is not None:
        return ProjectDetail.model_validate(cached)
    detail = await _project_detail(session, project_id)
    await cache.set_json(key, detail.model_dump(mode="json"), settings.cache_ttl_seconds)
    return detail


async def update_project(
    session: AsyncSession, cache: Cache, user: AuthUser, project_id: int, data: ProjectUpdate
) -> ProjectDetail:
    project = await get_project_for_owner(session, project_id, user)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        raise BadRequest("Project name cannot be null")
    for field, value in changes.items():
        setattr(project, field, value)
    await session.commit()
    await cache.invalidate_project(project_id)
    return await _project_detail(session, project_id)


async def delete_project(
    session: AsyncSession, cache: Cache, user: AuthUser, project_id: int
) -> None:
    project = await get_project_for_owner(session, project_id, user)
    await session.delete(project)  # участники и задачи удаляются каскадом в БД
    await session.commit()
    await cache.invalidate_project(project_id)
    await cache.invalidate_tasks(project_id)


async def add_member(
    session: AsyncSession, cache: Cache, user: AuthUser, project_id: int, member_id: int
) -> ProjectDetail:
    await get_project_for_owner(session, project_id, user)
    if await session.get(UserReplica, member_id) is None:
        raise NotFound("User not found")
    if await is_member(session, project_id, member_id):
        raise Conflict("User is already a member of this project")
    session.add(ProjectMember(project_id=project_id, user_id=member_id))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise Conflict("User is already a member of this project") from None
    await cache.invalidate_project(project_id)
    return await _project_detail(session, project_id)


async def remove_member(
    session: AsyncSession, cache: Cache, user: AuthUser, project_id: int, member_id: int
) -> None:
    project = await get_project_for_owner(session, project_id, user)
    if member_id == project.owner_id:
        raise BadRequest("Project owner cannot be removed")
    member = await session.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == member_id
        )
    )
    if member is None:
        raise NotFound("Member not found")
    await session.delete(member)
    await session.execute(
        update(Task)
        .where(Task.project_id == project_id, Task.assignee_id == member_id)
        .values(assignee_id=None)
    )
    await session.commit()
    await cache.invalidate_project(project_id)
    await cache.invalidate_tasks(project_id)
