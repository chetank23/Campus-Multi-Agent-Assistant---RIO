import urllib.request
import urllib.error
import json

base_url = "http://127.0.0.1:8000"

# Need to fetch an admin email using psycopg directly or just hardcode if we know one.
# For now, I'll use psycopg directly to get it since we know DB works.
import psycopg
from backend.config import DATABASE_URL

print("Connecting to DB...")
with psycopg.connect(DATABASE_URL.replace("+psycopg", "")) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM users WHERE role = 'ADMIN' LIMIT 1")
        row = cur.fetchone()
        if not row:
            raise RuntimeError("No ADMIN user found in database. Please run generate_sample_data.py first.")
        admin_email = row[0]

print(f"Admin email: {admin_email}")

# 1. Failed login
req = urllib.request.Request(
    f"{base_url}/auth/login",
    data=json.dumps({"email": admin_email, "password": "wrongpassword"}).encode('utf-8'),
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    with urllib.request.urlopen(req) as response:
        print("Failed login surprisingly succeeded.")
except urllib.error.HTTPError as e:
    print(f"\n--- Failed Login (Wrong Password) ---")
    print(f"Status: {e.code}")
    print(f"Response: {e.read().decode('utf-8')}")

import os
test_password = os.environ.get("TEST_PASSWORD")
if not test_password:
    raise ValueError("TEST_PASSWORD environment variable is missing. Please provide it to run this utility.")

# 2. Successful login
req2 = urllib.request.Request(
    f"{base_url}/auth/login",
    data=json.dumps({"email": admin_email, "password": test_password}).encode('utf-8'),
    headers={"Content-Type": "application/json"},
    method="POST"
)
try:
    with urllib.request.urlopen(req2) as response:
        print(f"\n--- Successful Admin Login ---")
        print(f"Status: {response.code}")
        body = response.read().decode('utf-8')
        print(f"Response: {body}")
        
        token = json.loads(body)["access_token"]
        
        # 3. GET /auth/me
        req3 = urllib.request.Request(
            f"{base_url}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            method="GET"
        )
        with urllib.request.urlopen(req3) as me_response:
            print(f"\n--- GET /auth/me with valid token ---")
            print(f"Status: {me_response.code}")
            print(f"Response: {me_response.read().decode('utf-8')}")

except urllib.error.HTTPError as e:
    print(f"Unexpected error: {e.code} {e.read().decode('utf-8')}")
