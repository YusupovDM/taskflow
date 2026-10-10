import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, UniqueConstraint, false, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        # идемпотентность: повторная доставка того же события не создаёт дубль
        UniqueConstraint("event_id", "user_id", name="uq_notifications_event_user"),
        Index("ix_notifications_user_is_read", "user_id", "is_read"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[uuid.UUID]
    user_id: Mapped[int]
    type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    is_read: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
