from typing import Annotated

from fastapi import APIRouter, Query, status

from app.dependencies import CurrentUser, PublisherDep, SessionDep
from app.models import TaskStatus
from app.schemas import TaskRead, TaskStatusUpdate, TaskUpdate
from app.services import tasks as tasks_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/my", response_model=list[TaskRead])
async def my_tasks(
    user: CurrentUser,
    session: SessionDep,
    status: TaskStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await tasks_service.list_my_tasks(session, user, status, limit, offset)


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: int, user: CurrentUser, session: SessionDep):
    return await tasks_service.get_task(session, user, task_id)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    data: TaskUpdate,
    user: CurrentUser,
    session: SessionDep,
    publisher: PublisherDep,
):
    return await tasks_service.update_task(session, publisher, user, task_id, data)


@router.patch("/{task_id}/status", response_model=TaskRead)
async def change_status(
    task_id: int,
    data: TaskStatusUpdate,
    user: CurrentUser,
    session: SessionDep,
    publisher: PublisherDep,
):
    return await tasks_service.change_status(session, publisher, user, task_id, data)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: int, user: CurrentUser, session: SessionDep):
    await tasks_service.delete_task(session, user, task_id)
