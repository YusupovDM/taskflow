from unittest.mock import ANY

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
NEW_USER = {"email": "New@Example.com", "password": "password123", "full_name": "New User"}


async def test_register_returns_201_without_password(client):
    response = await client.post(REGISTER, json=NEW_USER)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["role"] == "user"
    assert "password" not in body and "hashed_password" not in body


async def test_register_duplicate_email_returns_409(client):
    assert (await client.post(REGISTER, json=NEW_USER)).status_code == 201
    response = await client.post(REGISTER, json={**NEW_USER, "email": "new@example.com"})
    assert response.status_code == 409
    assert response.json() == {"detail": "User with this email already exists"}


async def test_register_short_password_returns_422(client):
    response = await client.post(REGISTER, json={**NEW_USER, "password": "short"})
    assert response.status_code == 422


async def test_register_publishes_user_registered(client, publisher):
    response = await client.post(REGISTER, json=NEW_USER)
    publisher.publish.assert_awaited_once_with(
        "user.registered",
        {
            "user_id": response.json()["id"],
            "email": "new@example.com",
            "full_name": "New User",
            "role": "user",
        },
    )


async def test_login_success_and_me(client):
    await client.post(REGISTER, json=NEW_USER)
    credentials = {"email": "new@example.com", "password": "password123"}
    response = await client.post(LOGIN, json=credentials)
    assert response.status_code == 200
    assert response.json() == {"access_token": ANY, "token_type": "bearer"}

    token = response.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "new@example.com"


async def test_login_wrong_password_returns_401(client, user):
    response = await client.post(LOGIN, json={"email": user.email, "password": "wrong-password"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


async def test_me_without_token_returns_401(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_me_with_invalid_token_returns_401(client):
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401


async def test_list_users_forbidden_for_user_allowed_for_admin(client, user_headers, admin_headers):
    assert (await client.get("/api/v1/users", headers=user_headers)).status_code == 403
    response = await client.get("/api/v1/users", headers=admin_headers)
    assert response.status_code == 200
    assert {u["email"] for u in response.json()} == {"user@example.com", "admin@example.com"}


async def test_admin_changes_role(client, user, admin_headers):
    response = await client.patch(
        f"/api/v1/users/{user.id}/role", json={"role": "admin"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    missing = await client.patch(
        "/api/v1/users/9999/role", json={"role": "admin"}, headers=admin_headers
    )
    assert missing.status_code == 404
