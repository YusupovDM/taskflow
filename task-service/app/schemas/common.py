from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict


class UserShort(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str


def ensure_aware(value: datetime | None) -> datetime | None:
    """Дедлайн без часового пояса считаем UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
