from sqlalchemy import func, select

from app.consumer import handle_event
from app.models import UserReplica
from app.services.replicas import upsert_user_replica


async def test_user_registered_upsert_is_idempotent(session):
    payload = {"user_id": 7, "email": "u7@example.com", "full_name": "First", "role": "user"}
    await upsert_user_replica(session, payload)
    await upsert_user_replica(session, {**payload, "full_name": "Renamed"})

    assert await session.scalar(select(func.count()).select_from(UserReplica)) == 1
    replica = await session.get(UserReplica, 7, populate_existing=True)
    assert replica.full_name == "Renamed"


async def test_unknown_event_is_ignored(session):
    await handle_event({"event_type": "something.else", "payload": {}})
    assert await session.scalar(select(func.count()).select_from(UserReplica)) == 0
