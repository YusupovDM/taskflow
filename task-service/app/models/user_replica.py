from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserReplica(Base):
    """Локальная копия пользователя из auth-service (наполняется событием user.registered)."""

    __tablename__ = "user_replicas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    email: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
