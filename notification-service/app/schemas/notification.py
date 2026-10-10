import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: uuid.UUID
    type: str
    title: str
    payload: dict[str, Any]
    is_read: bool
    created_at: datetime


class ReadAllResult(BaseModel):
    updated: int
