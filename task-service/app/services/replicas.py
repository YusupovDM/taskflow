from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserReplica


async def upsert_user_replica(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Идемпотентно: повторное событие обновит строку, а не создаст дубль."""
    stmt = insert(UserReplica).values(
        id=payload["user_id"], email=payload["email"], full_name=payload["full_name"]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[UserReplica.id],
        set_={
            "email": stmt.excluded.email,
            "full_name": stmt.excluded.full_name,
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)
    await session.commit()
