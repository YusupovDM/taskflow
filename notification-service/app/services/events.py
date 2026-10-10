"""Превращение событий в уведомления: кому и с каким текстом."""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.metrics import notifications_created_total
from app.models import Notification

logger = logging.getLogger(__name__)

STATUS_LABELS = {"todo": "К выполнению", "in_progress": "В работе", "done": "Готово"}


@dataclass(frozen=True)
class Draft:
    user_id: int
    title: str


def _task_ref(p: dict[str, Any]) -> str:
    return f"«{p['title']}» в проекте «{p['project_name']}»"


def build_drafts(event_type: str, p: dict[str, Any]) -> list[Draft]:
    if event_type == "user.registered":
        return [Draft(p["user_id"], "Добро пожаловать в TaskFlow")]

    if event_type == "task.created":
        assignee = p.get("assignee_id")
        if assignee is None or assignee == p.get("creator_id"):
            return []
        return [Draft(assignee, f"Создана задача {_task_ref(p)}, вы исполнитель")]

    if event_type == "task.assigned":
        return [Draft(p["assignee_id"], f"Вам назначена задача {_task_ref(p)}")]

    if event_type == "task.status_changed":
        old = STATUS_LABELS.get(p["old_status"], p["old_status"])
        new = STATUS_LABELS.get(p["new_status"], p["new_status"])
        title = f"Статус задачи {_task_ref(p)} изменён: {old} → {new}"
        recipients = {p.get("assignee_id"), p.get("owner_id")} - {None, p.get("changed_by")}
        return [Draft(user_id, title) for user_id in sorted(recipients)]

    return []


async def handle_event(session: AsyncSession, event: dict[str, Any]) -> int:
    """Создаёт уведомления по событию. Возвращает, сколько записей реально добавлено."""
    event_type = event["event_type"]
    payload = event["payload"]
    drafts = build_drafts(event_type, payload)
    if not drafts:
        logger.info("Event %s (%s): no recipients", event_type, event["event_id"])
        return 0

    rows = [
        {
            "event_id": uuid.UUID(event["event_id"]),
            "user_id": d.user_id,
            "type": event_type,
            "title": d.title[:255],
            "payload": payload,
        }
        for d in drafts
    ]
    stmt = (
        insert(Notification)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_notifications_event_user")
        .returning(Notification.id)
    )
    created = len((await session.execute(stmt)).all())
    await session.commit()
    if created:
        notifications_created_total.labels(type=event_type).inc(created)
    logger.info("Event %s (%s): %s notification(s) created", event_type, event["event_id"], created)
    return created
