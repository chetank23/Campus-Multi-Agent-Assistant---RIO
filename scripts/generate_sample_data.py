import os
import csv
import random
import re
import argparse
from pathlib import Path
from faker import Faker
import bcrypt

# Fixed seed for reproducibility
SEED = 42
random.seed(SEED)
faker = Faker()
Faker.seed(SEED)

# Fixed test password
import os
TEST_PASSWORD = os.environ.get("TEST_PASSWORD")
if not TEST_PASSWORD:
    raise ValueError("TEST_PASSWORD environment variable is missing. It is strictly required to generate seed data.")
# Pre-hash to avoid hashing thousands of times
HASHED_PASSWORD = bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt()).decode("utf-8")

DATASET_CONFIG = {
    "A": {"depts": 3, "faculty": 10, "courses": 15, "rooms": 10, "sections": 5},
    "B": {"depts": 5, "faculty": 50, "courses": 80, "rooms": 30, "sections": 20},
    "C": {"depts": 10, "faculty": 120, "courses": 150, "rooms": 60, "sections": 50},
}

def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)

def generate_data(dataset_name):
    cfg = DATASET_CONFIG[dataset_name]
    out_dir = Path(f"data/sample/{dataset_name}")
    ensure_dir(out_dir)
    
    # ID trackers
    next_id = {
        "users": 1, "departments": 1, "programs": 1, "academic_years": 1,
        "semesters": 1, "sections": 1, "batches": 1, "students": 1,
        "faculty": 1, "courses": 1, "course_assignments": 1,
        "elective_groups": 1, "elective_group_courses": 1, "buildings": 1,
        "rooms": 1, "labs": 1, "time_slots": 1, "faculty_availability": 1,
        "academic_calendar": 1, "resources": 1,
    }
    
    def get_id(table):
        val = next_id[table]
        next_id[table] += 1
        return val

    # Uniqueness sets
    used_emails = set()
    used_faculty_ids = set()
    used_student_ids = set()
    used_course_codes = set()

    def unique_email(name):
        base = re.sub(r'[^a-z0-9.]', '', name.lower().replace(" ", ".")).strip('.')
        email = f"{base}@campus.edu"
        counter = 1
        while email in used_emails:
            email = f"{base}{counter}@campus.edu"
            counter += 1
        used_emails.add(email)
        return email

    def unique_faculty_id():
        while True:
            fid = f"FAC{random.randint(1000, 9999)}"
            if fid not in used_faculty_ids:
                used_faculty_ids.add(fid)
                return fid

    def unique_student_id():
        while True:
            sid = f"STU{random.randint(10000, 99999)}"
            if sid not in used_student_ids:
                used_student_ids.add(sid)
                return sid
                
    def unique_course_code(dept_code):
        while True:
            cc = f"{dept_code}{random.randint(100, 999)}"
            if cc not in used_course_codes:
                used_course_codes.add(cc)
                return cc

    # --- 1. Departments ---
    departments = []
    dept_names = ["Computer Science", "Mechanical Engineering", "Electrical Engineering", 
                  "Civil Engineering", "Mathematics", "Physics", "Chemistry", 
                  "Business Administration", "Design", "Data Science"]
    
    for i in range(cfg["depts"]):
        dept_name = dept_names[i % len(dept_names)]
        code = "".join(w[0] for w in dept_name.split())
        if len(code) < 2: code = dept_name[:3].upper()
        
        departments.append({
            "id": get_id("departments"),
            "department_code": code,
            "name": dept_name,
        })

    # --- 2. Programs ---
    programs = []
    for dept in departments:
        programs.append({
            "id": get_id("programs"),
            "department_id": dept["id"],
            "program_name": f"B.Tech {dept['name']}",
            "degree": "B.Tech",
            "duration": 4
        })

    # --- 3. Academic Years & Semesters ---
    academic_years = [{
        "id": get_id("academic_years"),
        "name": "2026-2027",
        "start_date": "2026-08-01",
        "end_date": "2027-05-31"
    }]
    
    semesters = [
        {"id": get_id("semesters"), "academic_year_id": 1, "semester_number": 1, "start_date": "2026-08-01", "end_date": "2026-12-15"},
        {"id": get_id("semesters"), "academic_year_id": 1, "semester_number": 2, "start_date": "2027-01-10", "end_date": "2027-05-31"}
    ]

    # --- 4. Sections & Batches ---
    sections = []
    batches = []
    for _ in range(cfg["sections"]):
        prog = random.choice(programs)
        sem = random.choice(semesters)
        sec_id = get_id("sections")
        sec_name = random.choice(["A", "B", "C"])
        student_count = random.randint(40, 60)
        
        sections.append({
            "id": sec_id,
            "department_id": prog["department_id"],
            "program_id": prog["id"],
            "semester_id": sem["id"],
            "section_name": sec_name,
            "student_count": student_count
        })
        
        # 2 batches per section
        for b_name in ["B1", "B2"]:
            batches.append({
                "id": get_id("batches"),
                "section_id": sec_id,
                "batch_name": b_name,
                "student_count": student_count // 2
            })

    # --- 5. Users, Faculty, Students ---
    users = []
    faculty = []
    students = []
    
    # 5a. Admin
    users.append({"id": get_id("users"), "name": "System Admin", "email": "admin@campus.edu", "password_hash": HASHED_PASSWORD, "role": "ADMIN", "department_id": None, "is_active": True, "created_at": "2026-01-01 00:00:00"})
    used_emails.update(["admin@campus.edu"])
    
    # 5b. Faculty
    dept_faculty = {d["id"]: [] for d in departments}
    
    for _ in range(cfg["faculty"]):
        dept = random.choice(departments)
        name = faker.name()
        email = unique_email(name)
        u_id = get_id("users")
        
        users.append({
            "id": u_id, "name": name, "email": email, "password_hash": HASHED_PASSWORD, 
            "role": "FACULTY", "department_id": dept["id"], "is_active": True, "created_at": "2026-01-01 00:00:00"
        })
        
        f_id = get_id("faculty")
        fac = {
            "id": f_id, "user_id": u_id, "faculty_id": unique_faculty_id(),
            "department_id": dept["id"], "designation": random.choice(["Professor", "Associate Professor", "Assistant Professor"]),
            "max_weekly_load": 16
        }
        faculty.append(fac)
        dept_faculty[dept["id"]].append(fac)

    # Promote one faculty per department to ADMIN for dept visibility
    for dept in departments:
        if dept_faculty[dept["id"]]:
            hod_fac = dept_faculty[dept["id"]][0]
            # Keep them as FACULTY (no HOD role in 3-role model)

    # 5c. Students (derive from sections/batches)
    for b in batches:
        sec = next(s for s in sections if s["id"] == b["section_id"])
        for _ in range(b["student_count"]):
            name = faker.name()
            email = unique_email(name)
            u_id = get_id("users")
            
            users.append({
                "id": u_id, "name": name, "email": email, "password_hash": HASHED_PASSWORD, 
                "role": "STUDENT", "department_id": sec["department_id"], "is_active": True, "created_at": "2026-01-01 00:00:00"
            })
            
            students.append({
                "id": get_id("students"), "user_id": u_id, "student_id": unique_student_id(),
                "department_id": sec["department_id"], "program_id": sec["program_id"],
                "semester_id": sec["semester_id"], "section_id": sec["id"], "batch_id": b["id"]
            })

    # --- 6. Courses & Assignments ---
    courses = []
    course_assignments = []
    course_topics = ["Intro to", "Advanced", "Applied", "Principles of", "Fundamentals of"]
    
    for _ in range(cfg["courses"]):
        dept = random.choice(departments)
        ctype = random.choices(["THEORY", "LAB", "TUTORIAL", "ELECTIVE"], weights=[60, 20, 10, 10])[0]
        cname = f"{random.choice(course_topics)} {faker.catch_phrase().title()}"
        
        requires_lab = ctype == "LAB" or (ctype == "THEORY" and random.random() < 0.2)
        
        courses.append({
            "id": get_id("courses"),
            "course_code": unique_course_code(dept["department_code"]),
            "course_name": cname,
            "department_id": dept["id"],
            "course_type": ctype,
            "credits": random.randint(1, 4),
            "lecture_hours": 3 if ctype in ["THEORY", "ELECTIVE"] else 0,
            "tutorial_hours": 1 if ctype == "TUTORIAL" else 0,
            "practical_hours": 2 if requires_lab else 0,
            "requires_lab": requires_lab
        })

    # Assign courses to faculty (respecting department)
    for sec in sections:
        sec_courses = random.sample(courses, min(5, len(courses)))
        for c in sec_courses:
            # Find faculty in the same department as the course (fallback to any if empty)
            fac_candidates = dept_faculty[c["department_id"]]
            if not fac_candidates: fac_candidates = faculty
            fac = random.choice(fac_candidates)
            
            course_assignments.append({
                "id": get_id("course_assignments"),
                "course_id": c["id"],
                "faculty_id": fac["id"],
                "section_id": sec["id"],
                "batch_id": None # Whole section
            })

    # --- 7. Electives ---
    elective_groups = []
    elective_group_courses = []
    for dept in departments:
        eg_id = get_id("elective_groups")
        elective_groups.append({
            "id": eg_id, "name": f"Dept {dept['department_code']} Electives",
            "semester_id": random.choice(semesters)["id"], "department_id": dept["id"]
        })
        dept_courses = [c for c in courses if c["department_id"] == dept["id"] and c["course_type"] == "ELECTIVE"]
        for c in dept_courses[:3]: # Add up to 3
            elective_group_courses.append({
                "id": get_id("elective_group_courses"),
                "group_id": eg_id, "course_id": c["id"]
            })

    # --- 8. Buildings, Rooms, Labs ---
    buildings = [
        {"id": get_id("buildings"), "name": "Main Block", "code": "MB", "location": "North Campus", "number_of_floors": 4},
        {"id": get_id("buildings"), "name": "Science Block", "code": "SB", "location": "South Campus", "number_of_floors": 3}
    ]
    
    rooms = []
    labs = []
    for i in range(cfg["rooms"]):
        rtype = random.choices(["CLASSROOM", "LAB", "SEMINAR_HALL"], weights=[70, 20, 10])[0]
        bldg = random.choice(buildings)
        r_id = get_id("rooms")
        dept = random.choice(departments)
        
        rooms.append({
            "id": r_id, "building_id": bldg["id"], "room_number": f"{bldg['code']}-{100 + i}",
            "capacity": random.choice([40, 60, 100, 120]), "room_type": rtype,
            "department_id": dept["id"], "has_projector": random.choice([True, False]),
            "has_smart_board": random.choice([True, False]), "status": "ACTIVE"
        })
        
        if rtype == "LAB":
            labs.append({
                "id": get_id("labs"), "room_id": r_id, "lab_name": f"{dept['department_code']} Lab {i}",
                "department_id": dept["id"], "computer_count": 30,
                "equipment": "Standard Lab Eq", "software": "VS Code, AutoCAD"
            })

    # --- 9. Time Slots ---
    time_slots = []
    days = ["MON", "TUE", "WED", "THU", "FRI", "SAT"]
    periods = [
        ("08:30", "09:25", "CLASS"),
        ("09:25", "10:20", "CLASS"),
        ("10:20", "10:40", "BREAK"),
        ("10:40", "11:35", "CLASS"),
        ("11:35", "12:30", "CLASS"),
        ("12:30", "13:30", "LUNCH"),
        ("13:30", "14:25", "CLASS"),
        ("14:25", "15:20", "CLASS"),
        ("15:20", "16:15", "CLASS"),
    ]
    for day in days:
        for st, et, typ in periods:
            time_slots.append({
                "id": get_id("time_slots"), "day": day, "start_time": st, "end_time": et, "slot_type": typ
            })

    # --- 10. Faculty Availability, Calendar, Resources ---
    faculty_availability = []
    for fac in faculty:
        # Mostly available, mark a few as unavailable/preferred
        for ts in time_slots:
            if ts["slot_type"] == "CLASS":
                r = random.random()
                avail = "UNAVAILABLE" if r < 0.05 else ("PREFERRED" if r < 0.15 else "AVAILABLE")
                faculty_availability.append({
                    "id": get_id("faculty_availability"), "faculty_id": fac["id"], "slot_id": ts["id"],
                    "availability": avail, "preference": 1 if avail == "PREFERRED" else 0
                })

    academic_calendar = []
    for sem in semesters:
        academic_calendar.append({
            "id": get_id("academic_calendar"), "academic_year_id": sem["academic_year_id"],
            "date": sem["start_date"], "event_type": "EVENT", "description": "Semester Start"
        })
        
        # Add realistic dates (just offsets from start_date for simplicity in sample data)
        # Assuming start_date is in 'YYYY-MM-DD' string format
        import datetime
        start_dt = datetime.datetime.strptime(str(sem["start_date"]), "%Y-%m-%d")
        
        # Holiday 1
        h1_dt = (start_dt + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        academic_calendar.append({
            "id": get_id("academic_calendar"), "academic_year_id": sem["academic_year_id"],
            "date": h1_dt, "event_type": "HOLIDAY", "description": "Mid-Term Break"
        })
        
        # Holiday 2
        h2_dt = (start_dt + datetime.timedelta(days=60)).strftime("%Y-%m-%d")
        academic_calendar.append({
            "id": get_id("academic_calendar"), "academic_year_id": sem["academic_year_id"],
            "date": h2_dt, "event_type": "HOLIDAY", "description": "Public Holiday"
        })
        
        # Exam
        exam_dt = (start_dt + datetime.timedelta(days=100)).strftime("%Y-%m-%d")
        academic_calendar.append({
            "id": get_id("academic_calendar"), "academic_year_id": sem["academic_year_id"],
            "date": exam_dt, "event_type": "EXAM", "description": "Final Exams Start"
        })

    resources = [
        {"id": get_id("resources"), "name": "Main Auditorium", "resource_type": "AUDITORIUM", "location": "MB-Ground", "capacity": 500, "status": "ACTIVE"},
        {"id": get_id("resources"), "name": "Portable Projector 1", "resource_type": "PROJECTOR", "location": "Admin Office", "capacity": 0, "status": "ACTIVE"}
    ]

    # --- OUTPUT TO CSV ---
    datasets = {
        "departments": departments, "programs": programs, "academic_years": academic_years,
        "semesters": semesters, "sections": sections, "batches": batches,
        "users": users, "faculty": faculty, "students": students,
        "courses": courses, "course_assignments": course_assignments,
        "elective_groups": elective_groups, "elective_group_courses": elective_group_courses,
        "buildings": buildings, "rooms": rooms, "labs": labs,
        "time_slots": time_slots, "faculty_availability": faculty_availability,
        "academic_calendar": academic_calendar, "resources": resources
    }

    for name, data in datasets.items():
        if not data: continue
        keys = data[0].keys()
        with open(out_dir / f"{name}.csv", 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
            
    print(f"Dataset {dataset_name} generated in {out_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic sample data")
    parser.add_argument("--dataset", choices=["A", "B", "C"], required=True, help="Dataset size (A=small, B=medium, C=large)")
    args = parser.parse_args()
    
    # Generate all requested dataset sizes if needed, but script is parameterized
    generate_data(args.dataset)
