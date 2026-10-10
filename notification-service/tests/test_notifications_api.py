from app.services.events import handle_event
from tests.conftest import TASK, make_event


async def _seed(session) -> None:
    for assignee in (1, 1, 2):
        event = make_event("task.assigned", {**TASK, "assignee_id": assignee, "assigned_by": 9})
        await handle_event(session, event)


async def test_list_returns_only_own_notifications(client, session, auth_headers):
    await _seed(session)
    response = await client.get("/api/v1/notifications", headers=auth_headers(1))
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert items[0]["id"] > items[1]["id"]  # новые сверху


async def test_mark_foreign_notification_returns_404(client, session, auth_headers):
    await _seed(session)
    foreign_id = (await client.get("/api/v1/notifications", headers=auth_headers(2))).json()[0][
        "id"
    ]
    response = await client.patch(
        f"/api/v1/notifications/{foreign_id}/read", headers=auth_headers(1)
    )
    assert response.status_code == 404


async def test_mark_read_and_unread_filter(client, session, auth_headers):
    await _seed(session)
    headers = auth_headers(1)
    first_id = (await client.get("/api/v1/notifications", headers=headers)).json()[0]["id"]

    response = await client.patch(f"/api/v1/notifications/{first_id}/read", headers=headers)
    assert response.status_code == 200 and response.json()["is_read"] is True

    unread = await client.get(
        "/api/v1/notifications", params={"unread_only": True}, headers=headers
    )
    assert len(unread.json()) == 1

    result = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert result.json() == {"updated": 1}


async def test_notifications_require_token(client):
    assert (await client.get("/api/v1/notifications")).status_code == 401
