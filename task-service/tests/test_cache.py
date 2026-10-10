import pytest
from sqlalchemy import event

from app.cache import Cache, project_key, tasks_version_key
from app.dependencies import get_cache
from app.main import app
from tests.conftest import BrokenRedis


@pytest.fixture
def task_selects(engine):
    """Считает SELECT'ы из таблицы tasks."""
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith("SELECT") and "FROM tasks" in statement:
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    yield statements
    event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)


async def test_second_list_request_served_from_cache(
    client, project, owner_headers, redis, task_selects
):
    url = f"/api/v1/projects/{project['id']}/tasks"
    await client.post(url, json={"title": "T"}, headers=owner_headers)
    task_selects.clear()

    first = await client.get(url, headers=owner_headers)
    assert len(task_selects) == 1
    assert [k async for k in redis.scan_iter(f"tasks:project:{project['id']}:v*:*")]

    second = await client.get(url, headers=owner_headers)
    assert second.json() == first.json()
    assert len(task_selects) == 1  # в БД за задачами не ходили


async def test_status_change_invalidates_list(client, project, owner_headers, redis):
    url = f"/api/v1/projects/{project['id']}/tasks"
    task = (await client.post(url, json={"title": "T"}, headers=owner_headers)).json()
    assert (await client.get(url, headers=owner_headers)).json()[0]["status"] == "todo"
    version = int(await redis.get(tasks_version_key(project["id"])) or 0)

    await client.patch(
        f"/api/v1/tasks/{task['id']}/status", json={"status": "done"}, headers=owner_headers
    )
    assert int(await redis.get(tasks_version_key(project["id"]))) == version + 1
    assert (await client.get(url, headers=owner_headers)).json()[0]["status"] == "done"


async def test_project_card_cached_and_invalidated(client, project, owner_headers, redis):
    url = f"/api/v1/projects/{project['id']}"
    await client.get(url, headers=owner_headers)
    assert await redis.exists(project_key(project["id"]))

    await client.patch(url, json={"name": "Renamed"}, headers=owner_headers)
    assert not await redis.exists(project_key(project["id"]))
    assert (await client.get(url, headers=owner_headers)).json()["name"] == "Renamed"


async def test_access_checked_before_cache(client, project, owner_headers, auth_headers):
    url = f"/api/v1/projects/{project['id']}"
    await client.get(url, headers=owner_headers)  # карточка теперь в кэше
    assert (await client.get(url, headers=auth_headers(3))).status_code == 403


async def test_api_works_when_redis_is_down(client, project, owner_headers):
    app.dependency_overrides[get_cache] = lambda: Cache(BrokenRedis())
    url = f"/api/v1/projects/{project['id']}/tasks"

    created = await client.post(url, json={"title": "T"}, headers=owner_headers)
    assert created.status_code == 201
    response = await client.get(url, headers=owner_headers)
    assert response.status_code == 200
    assert [t["title"] for t in response.json()] == ["T"]
    assert (
        await client.get(f"/api/v1/projects/{project['id']}", headers=owner_headers)
    ).status_code == 200
