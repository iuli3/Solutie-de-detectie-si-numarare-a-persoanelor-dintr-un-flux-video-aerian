from conftest import register_user


def test_register_creates_user_and_does_not_leak_password(client):
    response = register_user(client)

    assert response.status_code == 201
    body = response.get_json()
    assert body["access_token"]
    assert body["user"]["email"] == "ana@example.com"
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]


def test_register_requires_email_and_password(client):
    response = client.post("/auth/register", json={"email": "missing-password@example.com"})

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_register_rejects_duplicate_email(client):
    first = register_user(client)
    second = register_user(client)

    assert first.status_code == 201
    assert second.status_code == 409


def test_login_accepts_valid_credentials(client):
    register_user(client, email="login@example.com", password="Secret123!")

    response = client.post("/auth/login", json={"username": "login@example.com", "password": "Secret123!"})

    assert response.status_code == 200
    assert response.get_json()["access_token"]


def test_login_rejects_wrong_password(client):
    register_user(client, email="login@example.com", password="Secret123!")

    response = client.post("/auth/login", json={"username": "login@example.com", "password": "bad"})

    assert response.status_code == 401


def test_me_requires_jwt(client):
    response = client.get("/auth/me")

    assert response.status_code == 401


def test_me_returns_current_user(client, auth_header):
    response = client.get("/auth/me", headers=auth_header)

    assert response.status_code == 200
    assert response.get_json()["user"]["email"] == "ana@example.com"
