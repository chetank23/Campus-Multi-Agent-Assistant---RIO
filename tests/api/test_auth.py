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
