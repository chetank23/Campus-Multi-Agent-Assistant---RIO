import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.database import get_db
from backend.models.space_time import Building, Room
from dotenv import load_dotenv

load_dotenv(".env")
DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app, raise_server_exceptions=False)


def admin_headers(test_client=client):
    with TestingSessionLocal() as db:
        email = db.execute(
            __import__("sqlalchemy").text("SELECT email FROM users WHERE role = 'ADMIN' LIMIT 1")
        ).scalar()
    assert email
    login = test_client.post("/auth/login", json={"email": email, "password": "Test@1234"})
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}

@pytest.fixture(autouse=True)
def test_building():
    # Setup
    db = TestingSessionLocal()
    b = Building(name="Test Building", code="TB", number_of_floors=2)
    db.add(b)
    db.commit()
    db.refresh(b)
    
    yield b
    
    # Teardown
    db.query(Room).filter(Room.building_id == b.id).delete()
    db.delete(b)
    db.commit()
    db.close()

def test_create_room(test_building):
    client_raise = TestClient(app, raise_server_exceptions=True)
    response = client_raise.post(
        "/rooms/",
        headers=admin_headers(client_raise),
        json={"building_id": test_building.id, "room_number": "101", "capacity": 30, "room_type": "CLASSROOM"}
    )
    if response.status_code != 200:
        print(response.text)
    assert response.status_code == 200
    data = response.json()
    assert data["room_number"] == "101"
    assert data["capacity"] == 30
    assert "id" in data

def test_invalid_capacity(test_building):
    response = client.post(
        "/rooms/",
        headers=admin_headers(),
        json={"building_id": test_building.id, "room_number": "102", "capacity": 0, "room_type": "CLASSROOM"}
    )
    assert response.status_code == 422 # Pydantic validation error

def test_invalid_room_type_db_error(test_building):
    response = client.post(
        "/rooms/",
        json={"building_id": test_building.id, "room_number": "103", "capacity": 30, "room_type": "INVALID_TYPE"}
    )
    # Now rejected by Pydantic before reaching DB
    assert response.status_code == 422

def test_invalid_building_fk_error():
    # Provide a non-existent building_id to trigger SQLAlchemy IntegrityError (Foreign Key violation)
    response = client.post(
        "/rooms/",
        json={"building_id": 999999, "room_number": "104", "capacity": 30, "room_type": "CLASSROOM"}
    )
    # The global exception handler should catch this and return a 422 instead of 500
    assert response.status_code == 422
    assert "Database integrity error" in response.text

def test_csv_import_validation(test_building):
    csv_content = f"""building_id,room_number,capacity,room_type
{test_building.id},101,30,CLASSROOM
999999,102,30,CLASSROOM
{test_building.id},103,-10,CLASSROOM
{test_building.id},104,30,INVALID_TYPE
"""
    files = {"file": ("test.csv", csv_content.encode("utf-8"), "text/csv")}
    response = client.post("/rooms/import", files=files, headers=admin_headers())
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["valid_rows"]) == 1
    assert data["valid_rows"][0]["room_number"] == "101"
    
    assert len(data["errors"]) == 3
    # Row 3 (999999 building_id)
    assert any(err for err in data["errors"] if err["row"] == 3 and "Building ID 999999 does not exist" in err["errors"])
    # Row 4 (-10 capacity)
    assert any(err for err in data["errors"] if err["row"] == 4 and "capacity must be positive" in err["errors"])
    # Row 5 (INVALID_TYPE)
    assert any(err for err in data["errors"] if err["row"] == 5 and "room_type must be one of" in err["errors"][0])
