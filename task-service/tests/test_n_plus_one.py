import pytest
from sqlalchemy import event

from app.cache import Cache
from app.dependencies import get_cache
from app.main import app
from app.models import Task
from tests.conftest import MEMBER_ID, OWNER_ID


@pytest.fixture
def query_counter(engine):
    counter = {"n": 0}

    def before_cursor_execute(*args):
        counter["n"] += 1

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    yield counter
    event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)


async def _count_list_queries(client, project_id, headers, counter) -> int:
    counter["n"] = 0
    response = await client.get(
        f"/api/v1/projects/{project_id}/tasks", params={"limit": 100}, headers=headers
    )
    assert response.status_code == 200
    return counter["n"], len(response.json())


async def test_task_list_query_count_does_not_grow(
    client, project, owner_headers, session, query_counter
):
    app.dependency_overrides[get_cache] = lambda: Cache(None)  # без кэша — честно в БД

    def add_tasks(n):
        session.add_all(
            Task(project_id=project["id"], title=f"t{i}", creator_id=OWNER_ID, assignee_id=uid)
            for i, uid in zip(range(n), [OWNER_ID, MEMBER_ID] * n, strict=False)
        )

    add_tasks(1)
    await session.commit()
    queries_one, count = await _count_list_queries(
        client, project["id"], owner_headers, query_counter
    )
    assert count == 1

    add_tasks(19)
    await session.commit()
    queries_twenty, count = await _count_list_queries(
        client, project["id"], owner_headers, query_counter
    )
    assert count == 20
    assert queries_twenty == queries_one


async def test_project_list_members_count_without_n_plus_one(
    client, users, owner_headers, query_counter
):
    for i in range(5):
        await client.post("/api/v1/projects", json={"name": f"p{i}"}, headers=owner_headers)
    query_counter["n"] = 0
    response = await client.get("/api/v1/projects", headers=owner_headers)
    assert [p["members_count"] for p in response.json()] == [1] * 5
    assert query_counter["n"] == 1
