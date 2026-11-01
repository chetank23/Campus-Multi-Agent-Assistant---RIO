import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from backend.main import app
from backend.config import engine

client = TestClient(app)

@pytest.fixture(scope="module")
def get_seeded_users():
    users = {}
    with engine.connect() as conn:
        for role in ["STUDENT", "FACULTY", "ADMIN"]:
            result = conn.execute(text(f"SELECT email, password_hash FROM users WHERE role = '{role}' LIMIT 1")).fetchone()
            if result:
                users[role] = result[0]
    return users

def test_login_success(get_seeded_users):
    for role, email in get_seeded_users.items():
        response = client.post("/auth/login", json={"email": email, "password": "Test@1234"})
        assert response.status_code == 200, f"Login failed for role {role}"
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        
        # Check that refresh token was set as httponly cookie
        assert "refresh_token" in response.cookies

def test_login_wrong_password(get_seeded_users):
    email = get_seeded_users["STUDENT"]
    response = client.post("/auth/login", json={"email": email, "password": "wrong_password"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"

def test_login_nonexistent_email():
    response = client.post("/auth/login", json={"email": "nonexistent@example.com", "password": "Test@1234"})
    assert response.status_code == 401
    # Check that it returns the SAME generic message as wrong password
    assert response.json()["detail"] == "Invalid credentials"

def test_get_me_success(get_seeded_users):
    email = get_seeded_users["ADMIN"]
    login_resp = client.post("/auth/login", json={"email": email, "password": "Test@1234"})
    token = login_resp.json()["access_token"]
    
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == email
    assert data["role"] == "ADMIN"
    assert "id" in data
    assert "name" in data

def test_get_me_expired_or_malformed_token():
    response = client.get("/auth/me", headers={"Authorization": "Bearer malformed.token.here"})
    assert response.status_code == 401

def test_get_me_missing_token():
    response = client.get("/auth/me")
    assert response.status_code == 401

def test_refresh_token_success(get_seeded_users):
    fresh_client = TestClient(app)
    email = get_seeded_users["ADMIN"]
    login_resp = fresh_client.post("/auth/login", json={"email": email, "password": "Test@1234"})
    assert login_resp.status_code == 200
    assert "refresh_token" in login_resp.cookies

    original_refresh_token = fresh_client.cookies.get("refresh_token")
    refresh_resp = fresh_client.post("/auth/refresh")
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    rotated_cookie = refresh_resp.cookies.get("refresh_token")
    assert rotated_cookie
    assert rotated_cookie != original_refresh_token

    # A rotated token is single-use: replaying the old cookie is rejected.
    fresh_client.cookies.set("refresh_token", original_refresh_token)
    replay_resp = fresh_client.post("/auth/refresh")
    assert replay_resp.status_code == 401

def test_refresh_token_missing_cookie():
    fresh_client = TestClient(app)
    response = fresh_client.post("/auth/refresh")
    assert response.status_code == 401
    assert response.json()["detail"] == "Refresh token missing"

def test_refresh_token_invalid_cookie():
    fresh_client = TestClient(app)
    fresh_client.cookies.set("refresh_token", "invalid.refresh.token")
    response = fresh_client.post("/auth/refresh")
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired refresh token"

def test_logout_clears_cookie_and_revokes_session(get_seeded_users):
    fresh_client = TestClient(app)
    email = get_seeded_users["ADMIN"]
    login_resp = fresh_client.post("/auth/login", json={"email": email, "password": "Test@1234"})
    old_refresh_token = fresh_client.cookies.get("refresh_token")
    assert old_refresh_token

    response = fresh_client.post("/auth/logout")
    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully"
    set_cookie = response.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie
    assert "max-age=0" in set_cookie.lower() or "expires=" in set_cookie.lower()

    fresh_client.cookies.set("refresh_token", old_refresh_token)
    revoked_resp = fresh_client.post("/auth/refresh")
    assert revoked_resp.status_code == 401


def test_access_token_cannot_be_used_as_refresh_token(get_seeded_users):
    fresh_client = TestClient(app)
    email = get_seeded_users["ADMIN"]
    login_resp = fresh_client.post("/auth/login", json={"email": email, "password": "Test@1234"})
    access_token = login_resp.json()["access_token"]
    fresh_client.cookies.set("refresh_token", access_token)
    response = fresh_client.post("/auth/refresh")
    assert response.status_code == 401


def test_login_rate_limit_blocks_repeated_invalid_attempts():
    fresh_client = TestClient(app)
    payload = {"email": "rate-limit-check@example.com", "password": "incorrect"}
    responses = [fresh_client.post("/auth/login", json=payload) for _ in range(9)]
    assert all(response.status_code == 401 for response in responses[:8])
    assert responses[8].status_code == 429
