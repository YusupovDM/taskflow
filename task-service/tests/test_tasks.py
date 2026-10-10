from datetime import UTC, datetime, timedelta
from unittest.mock import ANY

from tests.conftest import MEMBER_ID, OUTSIDER_ID, OWNER_ID


def tasks_url(project) -> str:
    return f"/api/v1/projects/{project['id']}/tasks"


async def test_create_task_with_assignee_publishes_events(
    client, project, owner_headers, publisher
):
    publisher.reset_mock()
    response = await client.post(
        tasks_url(project), json={"title": "Write", "assignee_id": MEMBER_ID}, headers=owner_headers
    )
    assert response.status_code == 201
    task = response.json()
    assert task["assignee"] == {"id": MEMBER_ID, "full_name": "Member"}
    assert task["status"] == "todo" and task["priority"] == "medium"

    publisher.publish.assert_any_await(
        "task.created",
        {
            "task_id": task["id"],
            "project_id": project["id"],
            "project_name": "Diploma",
            "title": "Write",
            "creator_id": OWNER_ID,
            "assignee_id": MEMBER_ID,
        },
    )
    publisher.publish.assert_awaited_with("task.assigned", ANY)
    assert publisher.publish.await_args.args[1]["assigned_by"] == OWNER_ID


async def test_assign_non_member_returns_400(client, project, owner_headers, publisher):
    publisher.reset_mock()
    response = await client.post(
        tasks_url(project), json={"title": "X", "assignee_id": OUTSIDER_ID}, headers=owner_headers
    )
    assert response.status_code == 400
    publisher.publish.assert_not_awaited()


async def test_change_status_publishes_old_and_new(
    client, project, owner_headers, auth_headers, publisher
):
    task = (
        await client.post(
            tasks_url(project), json={"title": "T", "assignee_id": MEMBER_ID}, headers=owner_headers
        )
    ).json()
    publisher.reset_mock()

    response = await client.patch(
        f"/api/v1/tasks/{task['id']}/status",
        json={"status": "in_progress"},
        headers=auth_headers(MEMBER_ID),  # исполнитель может менять статус
    )
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    publisher.publish.assert_awaited_once_with("task.status_changed", ANY)
    payload = publisher.publish.await_args.args[1]
    assert payload["old_status"] == "todo"
    assert payload["new_status"] == "in_progress"
    assert payload["changed_by"] == MEMBER_ID
    assert payload["owner_id"] == OWNER_ID


async def test_non_assignee_cannot_change_status(client, project, owner_headers, auth_headers):
    task = (
        await client.post(tasks_url(project), json={"title": "T"}, headers=owner_headers)
    ).json()
    response = await client.patch(
        f"/api/v1/tasks/{task['id']}/status",
        json={"status": "done"},
        headers=auth_headers(MEMBER_ID),
    )
    assert response.status_code == 403


async def test_overdue_filter(client, project, owner_headers):
    now = datetime.now(UTC)
    past, future = (now - timedelta(days=1)).isoformat(), (now + timedelta(days=1)).isoformat()
    for title, deadline in [
        ("late", past),
        ("late-done", past),
        ("future", future),
        ("none", None),
    ]:
        await client.post(
            tasks_url(project), json={"title": title, "deadline": deadline}, headers=owner_headers
        )
    tasks = (await client.get(tasks_url(project), headers=owner_headers)).json()
    done_id = next(t["id"] for t in tasks if t["title"] == "late-done")
    await client.patch(
        f"/api/v1/tasks/{done_id}/status", json={"status": "done"}, headers=owner_headers
    )

    response = await client.get(
        tasks_url(project), params={"overdue": "true"}, headers=owner_headers
    )
    assert response.status_code == 200
    assert [t["title"] for t in response.json()] == ["late"]


async def test_reassign_publishes_task_assigned(client, project, owner_headers, publisher):
    task = (
        await client.post(tasks_url(project), json={"title": "T"}, headers=owner_headers)
    ).json()
    publisher.reset_mock()
    response = await client.patch(
        f"/api/v1/tasks/{task['id']}", json={"assignee_id": MEMBER_ID}, headers=owner_headers
    )
    assert response.status_code == 200
    publisher.publish.assert_awaited_once_with("task.assigned", ANY)


async def test_my_tasks(client, project, owner_headers, auth_headers):
    await client.post(
        tasks_url(project), json={"title": "mine", "assignee_id": MEMBER_ID}, headers=owner_headers
    )
    await client.post(tasks_url(project), json={"title": "not mine"}, headers=owner_headers)
    response = await client.get("/api/v1/tasks/my", headers=auth_headers(MEMBER_ID))
    assert [t["title"] for t in response.json()] == ["mine"]
