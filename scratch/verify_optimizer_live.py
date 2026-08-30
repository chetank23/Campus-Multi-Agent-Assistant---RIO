import asyncio
import httpx
import json

async def run():
    async with httpx.AsyncClient() as client:
        # 1. Login to get token
        login_res = await client.post("http://127.0.0.1:8000/auth/login", json={
            "email": "admin@rio.edu",
            "password": "hashed_password"
        })
        if login_res.status_code != 200:
            print("Login failed:", login_res.status_code, login_res.text)
            # fallback to direct function call if API not running
            return
            
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Call generate
        payload = {
            "academic_year_id": 1,
            "semester_id": 1,
            "department_id": 1,
            "program_id": 1
        }
        print("Calling /timetable/generate...")
        res = await client.post("http://127.0.0.1:8000/timetable/generate", json=payload, headers=headers)
        
        print("Status:", res.status_code)
        if res.status_code == 200:
            data = res.json()
            print("Status:", data.get("status"))
            print("Message:", data.get("message"))
            print("Solve Time:", data.get("solve_time_seconds"))
            entries = data.get("generated_entries", [])
            print(f"Generated {len(entries)} entries.")
            for e in entries[:5]:
                print(f"  Assignment {e['course_assignment_id']} -> Room {e['room_id']} Slot {e['slot_id']} ({e['hour_type']})")
        else:
            print(res.text)

if __name__ == "__main__":
    asyncio.run(run())
