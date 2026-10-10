from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import AuthUser
from app.exceptions import BadRequest, Forbidden, NotFound
from app.messaging import EventPublisher
from app.metrics import task_status_changes_total, tasks_created_total
from app.models import Project, Task, TaskStatus
from app.schemas import TaskCreate, TaskRead, TaskStatusUpdate, TaskUpdate
from app.services.access import (
    ensure_assignable,
    ensure_replica,
    get_project_for_member,
    load_project,
)


def _tasks_query() -> Select[tuple[Task]]:
    # исполнитель подгружается одним дополнительным запросом на весь список (без N+1)
    return select(Task).options(selectinload(Task.assignee))


async def _load_task(session: AsyncSession, task_id: int) -> Task:
    stmt = _tasks_query().where(Task.id == task_id).execution_options(populate_existing=True)
    task = await session.scalar(stmt)
    if task is None:
        raise NotFound("Task not found")
    return task


def _base_payload(task: Task, project: Project) -> dict:
    return {
        "task_id": task.id,
        "project_id": project.id,
        "project_name": project.name,
        "title": task.title,
    }


async def create_task(
    session: AsyncSession,
    publisher: EventPublisher,
    user: AuthUser,
    project_id: int,
    data: TaskCreate,
) -> TaskRead:
    project = await get_project_for_member(session, project_id, user)
    if data.assignee_id is not None:
        await ensure_assignable(session, project_id, data.assignee_id)
    await ensure_replica(session, user)
    task = Task(project_id=project_id, creator_id=user.id, **data.model_dump())
    session.add(task)
    await session.commit()
    tasks_created_total.inc()

    task = await _load_task(session, task.id)
    payload = _base_payload(task, project)
    await publisher.publish(
        "task.created", {**payload, "creator_id": user.id, "assignee_id": task.assignee_id}
    )
    if task.assignee_id is not None:
        await publisher.publish(
            "task.assigned", {**payload, "assignee_id": task.assignee_id, "assigned_by": user.id}
        )
    return TaskRead.model_validate(task)


async def list_project_tasks(
    session: AsyncSession,
    user: AuthUser,
    project_id: int,
    *,
    status: TaskStatus | None,
    assignee_id: int | None,
    overdue: bool | None,
    limit: int,
    offset: int,
) -> list[TaskRead]:
    await get_project_for_member(session, project_id, user)
    stmt = _tasks_query().where(Task.project_id == project_id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if assignee_id is not None:
        stmt = stmt.where(Task.assignee_id == assignee_id)
    if overdue:
        stmt = stmt.where(Task.deadline < datetime.now(UTC), Task.status != TaskStatus.DONE)
    tasks = await session.scalars(stmt.order_by(Task.id).limit(limit).offset(offset))
    return [TaskRead.model_validate(t) for t in tasks]


async def list_my_tasks(
    session: AsyncSession, user: AuthUser, status: TaskStatus | None, limit: int, offset: int
) -> list[TaskRead]:
    stmt = _tasks_query().where(Task.assignee_id == user.id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    stmt = stmt.order_by(Task.deadline.nulls_last(), Task.id).limit(limit).offset(offset)
    tasks = await session.scalars(stmt)
    return [TaskRead.model_validate(t) for t in tasks]


async def get_task(session: AsyncSession, user: AuthUser, task_id: int) -> TaskRead:
    task = await _load_task(session, task_id)
    await get_project_for_member(session, task.project_id, user)
    return TaskRead.model_validate(task)


async def update_task(
    session: AsyncSession,
    publisher: EventPublisher,
    user: AuthUser,
    task_id: int,
    data: TaskUpdate,
) -> TaskRead:
    task = await _load_task(session, task_id)
    project = await load_project(session, task.project_id)
    if not (user.is_admin or user.id in (project.owner_id, task.creator_id)):
        raise Forbidden("Only the task creator, project owner or admin can edit this task")

    changes = data.model_dump(exclude_unset=True)
    for field in ("title", "priority"):
        if field in changes and changes[field] is None:
            raise BadRequest(f"Field '{field}' cannot be null")
    new_assignee = changes.get("assignee_id")
    assignee_changed = "assignee_id" in changes and new_assignee != task.assignee_id
    if assignee_changed and new_assignee is not None:
        await ensure_assignable(session, project.id, new_assignee)

    for field, value in changes.items():
        setattr(task, field, value)
    await session.commit()

    task = await _load_task(session, task_id)
    if assignee_changed and new_assignee is not None:
        await publisher.publish(
            "task.assigned",
            {**_base_payload(task, project), "assignee_id": new_assignee, "assigned_by": user.id},
        )
    return TaskRead.model_validate(task)


async def change_status(
    session: AsyncSession,
    publisher: EventPublisher,
    user: AuthUser,
    task_id: int,
    data: TaskStatusUpdate,
) -> TaskRead:
    task = await _load_task(session, task_id)
    project = await load_project(session, task.project_id)
    if not (user.is_admin or user.id in (project.owner_id, task.assignee_id)):
        raise Forbidden("Only the assignee, project owner or admin can change the status")

    old_status = task.status
    if old_status == data.status:
        return TaskRead.model_validate(task)
    task.status = data.status
    await session.commit()
    task_status_changes_total.labels(new_status=data.status.value).inc()

    task = await _load_task(session, task_id)
    await publisher.publish(
        "task.status_changed",
        {
            **_base_payload(task, project),
            "old_status": old_status.value,
            "new_status": task.status.value,
            "changed_by": user.id,
            "assignee_id": task.assignee_id,
            "owner_id": project.owner_id,
        },
    )
    return TaskRead.model_validate(task)


async def delete_task(session: AsyncSession, user: AuthUser, task_id: int) -> None:
    task = await _load_task(session, task_id)
    project = await load_project(session, task.project_id)
    if not (user.is_admin or user.id in (project.owner_id, task.creator_id)):
        raise Forbidden("Only the task creator, project owner or admin can delete this task")
    await session.delete(task)
    await session.commit()
