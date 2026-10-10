from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import TaskPriority, TaskStatus
from app.schemas.common import UserShort, ensure_aware


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_id: int | None = None
    deadline: datetime | None = None

    _aware_deadline = field_validator("deadline")(ensure_aware)


class TaskUpdate(BaseModel):
    """Частичное обновление: меняются только переданные поля (null тоже значение)."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    priority: TaskPriority | None = None
    assignee_id: int | None = None
    deadline: datetime | None = None

    _aware_deadline = field_validator("deadline")(ensure_aware)


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    assignee: UserShort | None
    creator_id: int
    deadline: datetime | None
    created_at: datetime
    updated_at: datetime
