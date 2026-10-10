from typing import Annotated

from fastapi import APIRouter, Query, status

from app.dependencies import CacheDep, CurrentUser, PublisherDep, SessionDep
from app.models import TaskStatus
from app.schemas import (
    MemberAdd,
    ProjectCreate,
    ProjectDetail,
    ProjectRead,
    ProjectUpdate,
    TaskCreate,
    TaskRead,
)
from app.services import projects as projects_service
from app.services import tasks as tasks_service

router = APIRouter(prefix="/projects", tags=["projects"])

Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.post("", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
async def create_project(data: ProjectCreate, user: CurrentUser, session: SessionDep):
    return await projects_service.create_project(session, user, data)


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    user: CurrentUser, session: SessionDep, limit: Limit = 20, offset: Offset = 0
):
    return await projects_service.list_projects(session, user, limit, offset)


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(project_id: int, user: CurrentUser, session: SessionDep, cache: CacheDep):
    return await projects_service.get_project(session, cache, user, project_id)


@router.patch("/{project_id}", response_model=ProjectDetail)
async def update_project(
    project_id: int, data: ProjectUpdate, user: CurrentUser, session: SessionDep, cache: CacheDep
):
    return await projects_service.update_project(session, cache, user, project_id, data)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int, user: CurrentUser, session: SessionDep, cache: CacheDep
):
    await projects_service.delete_project(session, cache, user, project_id)


@router.post(
    "/{project_id}/members", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED
)
async def add_member(
    project_id: int, data: MemberAdd, user: CurrentUser, session: SessionDep, cache: CacheDep
):
    return await projects_service.add_member(session, cache, user, project_id, data.user_id)


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    project_id: int, user_id: int, user: CurrentUser, session: SessionDep, cache: CacheDep
):
    await projects_service.remove_member(session, cache, user, project_id, user_id)


@router.post(
    "/{project_id}/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED
)
async def create_task(
    project_id: int,
    data: TaskCreate,
    user: CurrentUser,
    session: SessionDep,
    cache: CacheDep,
    publisher: PublisherDep,
):
    return await tasks_service.create_task(session, cache, publisher, user, project_id, data)


@router.get("/{project_id}/tasks", response_model=list[TaskRead])
async def list_project_tasks(
    project_id: int,
    user: CurrentUser,
    session: SessionDep,
    cache: CacheDep,
    status: TaskStatus | None = None,
    assignee_id: int | None = None,
    overdue: Annotated[
        bool | None, Query(description="true — дедлайн прошёл и задача не выполнена")
    ] = None,
    limit: Limit = 20,
    offset: Offset = 0,
):
    return await tasks_service.list_project_tasks(
        session,
        cache,
        user,
        project_id,
        status=status,
        assignee_id=assignee_id,
        overdue=overdue,
        limit=limit,
        offset=offset,
    )
