from tests.conftest import MEMBER_ID, OUTSIDER_ID, OWNER_ID


async def test_create_project_owner_is_member(client, users, owner_headers):
    response = await client.post(
        "/api/v1/projects", json={"name": "New", "description": "d"}, headers=owner_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["owner_id"] == OWNER_ID
    assert body["members_count"] == 1
    assert [m["user_id"] for m in body["members"]] == [OWNER_ID]
    assert body["members"][0]["full_name"] == "Owner"


async def test_outsider_gets_403_on_project(client, project, auth_headers):
    response = await client.get(
        f"/api/v1/projects/{project['id']}", headers=auth_headers(OUTSIDER_ID)
    )
    assert response.status_code == 403


async def test_admin_sees_any_project(client, project, admin_headers):
    response = await client.get(f"/api/v1/projects/{project['id']}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["members_count"] == 2


async def test_add_member_not_in_replicas_returns_404(client, project, owner_headers):
    response = await client.post(
        f"/api/v1/projects/{project['id']}/members", json={"user_id": 4242}, headers=owner_headers
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


async def test_member_cannot_manage_members(client, project, auth_headers):
    response = await client.post(
        f"/api/v1/projects/{project['id']}/members",
        json={"user_id": OUTSIDER_ID},
        headers=auth_headers(MEMBER_ID),
    )
    assert response.status_code == 403


async def test_owner_cannot_be_removed(client, project, owner_headers):
    response = await client.delete(
        f"/api/v1/projects/{project['id']}/members/{OWNER_ID}", headers=owner_headers
    )
    assert response.status_code == 400


async def test_list_projects_only_own(client, project, auth_headers, admin_headers):
    mine = await client.get("/api/v1/projects", headers=auth_headers(MEMBER_ID))
    assert [p["id"] for p in mine.json()] == [project["id"]]
    assert (await client.get("/api/v1/projects", headers=auth_headers(OUTSIDER_ID))).json() == []
    assert len((await client.get("/api/v1/projects", headers=admin_headers)).json()) == 1


async def test_requests_without_token_return_401(client):
    assert (await client.get("/api/v1/projects")).status_code == 401
