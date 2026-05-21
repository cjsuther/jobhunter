"""Auth endpoint tests."""


def test_login_success(client, user_a):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": user_a.email, "password": "secret123"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]


def test_login_bad_password(client, user_a):
    r = client.post(
        "/api/v1/auth/login",
        json={"email": user_a.email, "password": "wrong"},
    )
    assert r.status_code == 401


def test_me_requires_auth(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_me_returns_user(client, auth_a, user_a):
    r = client.get("/api/v1/auth/me", headers=auth_a)
    assert r.status_code == 200
    assert r.json()["email"] == user_a.email


def test_register_requires_admin(client, auth_a):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "x@y.z", "password": "abc12345"},
        headers=auth_a,
    )
    assert r.status_code == 403


def test_register_as_admin(client, auth_admin):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "abc12345", "role": "user"},
        headers=auth_admin,
    )
    assert r.status_code == 201
    assert r.json()["email"] == "new@example.com"
