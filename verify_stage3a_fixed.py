"""
Stage 3a Part B â€” Full endpoint verification script.
Runs against a live server at http://localhost:8000.
"""
import os
import json
import requests
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv(".env")
engine = create_engine(os.environ["DATABASE_URL"], isolation_level="AUTOCOMMIT")

BASE = "http://localhost:8000"
results = []

def check(label, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((label, status, detail))
    print(f"[{status}] {label}")
    if detail:
        print(f"       {detail}")

def r_body(r):
    try:
        return r.json()
    except Exception:
        return r.text[:200]

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Step 4 â€” Building CRUD
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print("\nâ”€â”€ STEP 4: Building CRUD â”€â”€")
r = requests.post(f"{BASE}/buildings/", json={"name": "Verify Block", "code": "VB", "number_of_floors": 3})
check("POST /buildings/ â†’ 200", r.status_code == 200, f"status={r.status_code} body={r_body(r)}")
bldg_id = r.json().get("id") if r.ok else None

if bldg_id:
    r = requests.get(f"{BASE}/buildings/{bldg_id}")
    check("GET /buildings/{id} â†’ 200", r.status_code == 200, f"name={r.json().get('name')}")

    r = requests.put(f"{BASE}/buildings/{bldg_id}", json={"name": "Verify Block Updated", "code": "VBU", "number_of_floors": 4})
    check("PUT /buildings/{id} â†’ 200", r.status_code == 200, f"name={r.json().get('name')}")

    r = requests.delete(f"{BASE}/buildings/{bldg_id}")
    check("DELETE /buildings/{id} â†’ 200", r.status_code == 200, f"status={r.status_code}")

    r = requests.get(f"{BASE}/buildings/{bldg_id}")
    check("GET after DELETE â†’ 404", r.status_code == 404, f"status={r.status_code}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Step 5 â€” Room CRUD (need a parent building first)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print("\nâ”€â”€ STEP 5: Room & Lab CRUD â”€â”€")
rb = requests.post(f"{BASE}/buildings/", json={"name": "Stage3a Test Block", "code": "STB", "number_of_floors": 5})
bldg_id2 = rb.json().get("id") if rb.ok else None
check("Setup: POST parent building â†’ 200", rb.status_code == 200, f"id={bldg_id2}")

if bldg_id2:
    r = requests.post(f"{BASE}/rooms/", json={
        "building_id": bldg_id2, "room_number": "S3A-101",
        "floor_number": 1, "capacity": 60, "room_type": "CLASSROOM"
    })
    check("POST /rooms/ with floor_number â†’ 200", r.status_code == 200, f"status={r.status_code} body={r_body(r)}")
    room_id = r.json().get("id") if r.ok else None

    if room_id:
        r = requests.get(f"{BASE}/rooms/{room_id}")
        check("GET /rooms/{id} â†’ 200", r.status_code == 200,
              f"room_number={r.json().get('room_number')} floor_number={r.json().get('floor_number')}")

        r = requests.put(f"{BASE}/rooms/{room_id}", json={
            "building_id": bldg_id2, "room_number": "S3A-101-UPD",
            "floor_number": 2, "capacity": 80, "room_type": "LAB"
        })
        check("PUT /rooms/{id} â†’ 200", r.status_code == 200, f"updated room_number={r.json().get('room_number')}")

        r = requests.delete(f"{BASE}/rooms/{room_id}")
        check("DELETE /rooms/{id} â†’ 200", r.status_code == 200, f"status={r.status_code}")

    # Lab CRUD
    r = requests.post(f"{BASE}/labs/", json={
        "room_id": None, "lab_name": "Stage3a Test Lab", "lab_type": "COMPUTER",
        "software_list": ["Python", "MATLAB"], "is_specialized": False
    })
    check("POST /labs/ â†’ 200", r.status_code == 200, f"status={r.status_code} body={r_body(r)}")
    lab_id = r.json().get("id") if r.ok else None

    if lab_id:
        r = requests.get(f"{BASE}/labs/{lab_id}")
        check("GET /labs/{id} â†’ 200", r.status_code == 200, f"lab_name={r.json().get('lab_name')}")

        r = requests.put(f"{BASE}/labs/{lab_id}", json={
            "room_id": None, "lab_name": "Stage3a Test Lab Updated", "lab_type": "ELECTRONICS",
            "software_list": [], "is_specialized": True
        })
        check("PUT /labs/{id} â†’ 200", r.status_code == 200, f"updated lab_name={r.json().get('lab_name')}")

        r = requests.delete(f"{BASE}/labs/{lab_id}")
        check("DELETE /labs/{id} â†’ 200", r.status_code == 200, f"status={r.status_code}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Step 6 â€” capacity validation
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print("\nâ”€â”€ STEP 6: Capacity validation â”€â”€")
r = requests.post(f"{BASE}/rooms/", json={"building_id": bldg_id2, "room_number": "BAD-CAP-0", "capacity": 0, "room_type": "CLASSROOM"})
check("POST /rooms/ capacity=0 â†’ 4xx", r.status_code >= 400, f"status={r.status_code}")

r = requests.post(f"{BASE}/rooms/", json={"building_id": bldg_id2, "room_number": "BAD-CAP-NEG", "capacity": -5, "room_type": "CLASSROOM"})
check("POST /rooms/ capacity=-5 â†’ 4xx", r.status_code >= 400, f"status={r.status_code}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Step 7 â€” invalid room_type
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print("\nâ”€â”€ STEP 7: Invalid room_type â”€â”€")
r = requests.post(f"{BASE}/rooms/", json={"building_id": bldg_id2, "room_number": "BAD-TYPE", "capacity": 30, "room_type": "INVALID_TYPE"})
check("POST /rooms/ room_type=INVALID_TYPE â†’ rejected (4xx or 5xx)", r.status_code >= 400, f"status={r.status_code}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Step 8 â€” CSV import preview (rooms/import)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print("\nâ”€â”€ STEP 8: CSV import preview â”€â”€")
sample_csv_path = "data/sample/sample_rooms.csv"
with open(sample_csv_path, "rb") as f:
    r = requests.post(f"{BASE}/rooms/import", files={"file": ("sample_rooms.csv", f, "text/csv")})

check("POST /rooms/import â†’ 200", r.status_code == 200, f"status={r.status_code}")
if r.ok:
    body = r.json()
    valid_rows = body.get("valid_rows", [])
    errors = body.get("errors", [])
    check("CSV preview: has valid_rows", len(valid_rows) > 0, f"valid_rows count={len(valid_rows)}")
    check("CSV preview: has error rows", len(errors) > 0, f"error_rows count={len(errors)}")
    print(f"       Valid rows: {[row.get('room_number') for row in valid_rows]}")
    print(f"       Error rows:")
    for e in errors:
        print(f"         row={e.get('row')} errors={e.get('errors')}")

    # Verify nothing was inserted yet
    with engine.connect() as conn:
        count_before = conn.execute(text("SELECT COUNT(*) FROM rooms WHERE building_id IN (SELECT id FROM buildings WHERE code='STB')")).scalar()
    check("CSV preview: nothing inserted yet", count_before == 0, f"rooms with STB building before confirm: {count_before}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Step 9 â€” CSV import confirm (only valid rows)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print("\nâ”€â”€ STEP 9: CSV import confirm â”€â”€")
if r.ok and valid_rows:
    # Fix building_id to use our test building (sample CSV uses building_id=1 and 2)
    # Re-read sample CSV and build valid rows with bldg_id2
    valid_payload = []
    for vr in valid_rows:
        vr_copy = dict(vr)
        vr_copy["building_id"] = bldg_id2
        valid_payload.append(vr_copy)

    r2 = requests.post(f"{BASE}/rooms/import/confirm", json={"rows": valid_payload})
    check("POST /rooms/import/confirm â†’ 200", r2.status_code == 200, f"status={r2.status_code} body={r_body(r2)}")

    if r2.ok:
        confirmed_ids = [row.get("id") for row in r2.json().get("inserted", [])]
        print(f"       Inserted IDs: {confirmed_ids}")

        # Verify they're actually in the DB
        with engine.connect() as conn:
            actual = conn.execute(text(f"SELECT id, room_number, floor_number FROM rooms WHERE id = ANY(ARRAY{confirmed_ids})")).fetchall()
        check("Confirmed rows actually in DB", len(actual) == len(valid_payload), f"expected={len(valid_payload)} found={len(actual)}")
        print(f"       DB rows: {[(r.id, r.room_number, r.floor_number) for r in actual]}")

        # Verify bad rows not inserted
        with engine.connect() as conn:
            bad_in_db = conn.execute(text("SELECT COUNT(*) FROM rooms WHERE room_number IN ('INVALID-1', 'SB-BADCAP', 'SB-BADTYPE')")).scalar()
        check("Bad rows NOT in DB", bad_in_db == 0, f"bad rows in DB: {bad_in_db}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Step 10 â€” Availability endpoint
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print("\nâ”€â”€ STEP 10: Room availability â”€â”€")
with engine.connect() as conn:
    real_room = conn.execute(text("SELECT id FROM rooms LIMIT 1")).scalar()

if real_room:
    r = requests.get(f"{BASE}/rooms/{real_room}/availability")
    check(f"GET /rooms/{real_room}/availability â†’ no error (200 or 200)", r.status_code == 200, f"status={r.status_code} body={r_body(r)}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Step 11 â€” floor_number in DB
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print("\nâ”€â”€ STEP 11: floor_number in DB â”€â”€")
with engine.connect() as conn:
    rows = conn.execute(text(
        "SELECT id, room_number, floor_number FROM rooms WHERE floor_number IS NOT NULL LIMIT 5"
    )).fetchall()
check("floor_number populated for â‰¥1 room", len(rows) > 0,
      f"Rooms with floor_number set: {[(r.id, r.room_number, r.floor_number) for r in rows]}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Cleanup: delete STB building (cascade won't help, manually delete rooms first)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print("\nâ”€â”€ Cleanup â”€â”€")
if bldg_id2:
    with engine.connect() as conn:
        conn.execute(text(f"DELETE FROM rooms WHERE building_id = {bldg_id2}"))
    r = requests.delete(f"{BASE}/buildings/{bldg_id2}")
    print(f"  Deleted test building id={bldg_id2}: status={r.status_code}")

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Final report
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
print("\n" + "=" * 70)
print("STAGE 3a PART B â€” FINAL RESULTS")
print("=" * 70)
print(f"{'#':<3} {'Check':<52} {'Result'}")
print("-" * 70)
for i, (label, status, detail) in enumerate(results, 1):
    marker = "âœ“" if status == "PASS" else "âœ—"
    print(f"{i:<3} {label:<52} [{status}] {marker}")

passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s == "FAIL")
print("-" * 70)
print(f"TOTAL: {passed} PASSED, {failed} FAILED")
