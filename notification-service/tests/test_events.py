from sqlalchemy import func, select

from app.models import Notification
from app.services.events import build_drafts, handle_event
from tests.conftest import TASK, make_event


async def _all(session) -> list[Notification]:
    return list(await session.scalars(select(Notification).order_by(Notification.id)))


async def test_task_assigned_creates_notification_for_assignee(session):
    event = make_event("task.assigned", {**TASK, "assignee_id": 5, "assigned_by": 1})
    assert await handle_event(session, event) == 1

    [notification] = await _all(session)
    assert notification.user_id == 5
    assert notification.type == "task.assigned"
    assert "Slides" in notification.title and "Diploma" in notification.title
    assert notification.payload["task_id"] == 1
    assert notification.is_read is False


async def test_same_event_twice_does_not_duplicate(session):
    event = make_event("task.assigned", {**TASK, "assignee_id": 5, "assigned_by": 1})
    assert await handle_event(session, event) == 1
    assert await handle_event(session, event) == 0  # повторная доставка
    assert await session.scalar(select(func.count()).select_from(Notification)) == 1


async def test_user_registered_creates_welcome(session):
    payload = {"user_id": 9, "email": "e@example.com", "full_name": "N", "role": "user"}
    await handle_event(session, make_event("user.registered", payload))
    [notification] = await _all(session)
    assert (notification.user_id, notification.title) == (9, "Добро пожаловать в TaskFlow")


def test_status_changed_notifies_assignee_and_owner_except_actor():
    payload = {
        **TASK,
        "old_status": "todo",
        "new_status": "done",
        "assignee_id": 5,
        "owner_id": 1,
        "changed_by": 5,
    }
    assert [d.user_id for d in build_drafts("task.status_changed", payload)] == [1]

    by_admin = {**payload, "changed_by": 100}
    assert [d.user_id for d in build_drafts("task.status_changed", by_admin)] == [1, 5]


def test_task_created_skips_self_assigned():
    assert build_drafts("task.created", {**TASK, "creator_id": 1, "assignee_id": 1}) == []
    assert build_drafts("task.created", {**TASK, "creator_id": 1, "assignee_id": None}) == []
    [draft] = build_drafts("task.created", {**TASK, "creator_id": 1, "assignee_id": 2})
    assert draft.user_id == 2
