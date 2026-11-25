"""
scripts/seed_placements_and_events.py
--------------------------------------
Idempotent seeder for Placements, Clubs, and Campus Events.
Populates realistic, production-grade records in PostgreSQL:
- Student Academic Records (verified CGPA, backlogs, grading scale)
- Placement Drives with multi-round selection schedules & eligibility criteria
- Placement Applications (candidate submissions & status transitions)
- Clubs & Organizations with faculty coordinators & student memberships
- Campus Events with room allocations & student registrations
"""

import os
import sys
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def seed_placements_and_events():
    load_dotenv(".env")
    env_name = os.environ.get("ENVIRONMENT", "development").strip().lower()
    if env_name in ("production", "prod") and "--force-production" not in sys.argv:
        print("[seed] Safety Check: Refusing to seed mock records in production environment without --force-production.")
        return

    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        print("[seed] Error: DATABASE_URL environment variable is required to execute database seeding.")
        sys.exit(1)

    engine = create_engine(db_url)
    now = datetime.now(timezone.utc)

    with engine.begin() as conn:
        print("[seed] Connecting to database and inspecting existing reference records...")

        # Find existing admin user for coordinator_id
        admin_row = conn.execute(
            text("SELECT id FROM users WHERE role IN ('ADMIN', 'SUPER_ADMIN') ORDER BY id LIMIT 1")
        ).fetchone()
        admin_id = admin_row[0] if admin_row else 1

        # Find existing department ids
        dept_rows = conn.execute(text("SELECT id, department_code FROM departments LIMIT 5")).fetchall()
        dept_ids = [d[0] for d in dept_rows] if dept_rows else [1]
        primary_dept_id = dept_ids[0]

        # Find students
        student_rows = conn.execute(
            text("SELECT id, user_id, student_id FROM students ORDER BY id LIMIT 10")
        ).fetchall()

        if not student_rows:
            print("[seed] Warning: No students found in students table. Run main seed first.")
            return

        print(f"[seed] Found {len(student_rows)} students and admin user (id={admin_id}).")

        # 1. Seed Student Academic Records
        print("[seed] Seeding student academic records...")
        for idx, s in enumerate(student_rows):
            s_id = s[0]
            cgpa = 9.2 if idx == 0 else round(7.5 + (idx * 0.25) % 2.4, 2)
            backlogs = 0 if idx in (0, 1, 2) else (1 if idx % 4 == 0 else 0)
            conn.execute(
                text("""
                    INSERT INTO student_academic_records (
                        student_id, cgpa, grading_scale, percentage,
                        active_backlogs, total_backlogs, graduation_year,
                        tenth_percentage, twelfth_percentage,
                        is_verified, verified_by, verified_at,
                        updated_at
                    ) VALUES (
                        :s_id, :cgpa, 10.0, :perc,
                        :backlogs, :total_backlogs, 2026,
                        91.5, 89.2,
                        true, :admin_id, :now,
                        :now
                    )
                    ON CONFLICT (student_id) DO UPDATE SET
                        cgpa = EXCLUDED.cgpa,
                        active_backlogs = EXCLUDED.active_backlogs,
                        is_verified = true
                """),
                {
                    "s_id": s_id,
                    "cgpa": cgpa,
                    "perc": cgpa * 9.5,
                    "backlogs": backlogs,
                    "total_backlogs": backlogs,
                    "admin_id": admin_id,
                    "now": now,
                }
            )

        # 2. Seed Placement Drives
        print("[seed] Seeding placement drives...")
        drives_data = [
            {
                "company_name": "Google",
                "company_description": "Global technology leader in search, cloud computing, software, and hardware.",
                "company_website": "https://careers.google.com",
                "title": "Google Campus SDE Drive 2026",
                "job_role": "Software Development Engineer (SDE-I)",
                "job_description": "Build large-scale distributed systems, search algorithms, and machine learning infrastructure.",
                "job_type": "FULL_TIME",
                "work_location": "Bengaluru / Hyderabad",
                "compensation_details": "CTC: 28.5 LPA (Base: 18 LPA + Stocks: 8.5 LPA + Performance Bonus)",
                "tier": "DREAM",
                "graduation_year": 2026,
                "min_cgpa": 8.0,
                "grading_scale": 10.0,
                "max_active_backlogs": 0,
                "max_total_backlogs": 0,
                "allowed_genders": "ALL",
                "application_deadline": now + timedelta(days=14),
                "application_instructions": "Submit application with resume URL and portfolio links. Shortlisted candidates will be invited to Round 1.",
                "contact_email": "placements@campus.edu",
                "status": "PUBLISHED",
                "published_at": now - timedelta(days=2),
                "coordinator_id": admin_id,
            },
            {
                "company_name": "Microsoft",
                "company_description": "Empowering every person and organization on the planet to achieve more.",
                "company_website": "https://careers.microsoft.com",
                "title": "Microsoft SDE Intern & FTE Campus Recruitment",
                "job_role": "Software Engineer (Intern + FTE)",
                "job_description": "Develop enterprise cloud solutions on Azure, Office 365, and AI productivity tools.",
                "job_type": "INTERN_PLUS_FULL_TIME",
                "work_location": "Hyderabad / Bengaluru / Noida",
                "compensation_details": "Stipend: 1.25 Lakh/mo, FTE CTC: 24.0 LPA",
                "tier": "DREAM",
                "graduation_year": 2026,
                "min_cgpa": 7.5,
                "grading_scale": 10.0,
                "max_active_backlogs": 0,
                "max_total_backlogs": 1,
                "allowed_genders": "ALL",
                "application_deadline": now + timedelta(days=21),
                "application_instructions": "Apply directly on this portal. Ensure your CGPA matches official semester transcripts.",
                "contact_email": "cdc-microsoft@campus.edu",
                "status": "PUBLISHED",
                "published_at": now - timedelta(days=1),
                "coordinator_id": admin_id,
            },
            {
                "company_name": "Amazon",
                "company_description": "Earth's most customer-centric company and cloud platform leader (AWS).",
                "company_website": "https://amazon.jobs",
                "title": "Amazon Cloud & Systems Recruitment 2026",
                "job_role": "Cloud Support Associate / SDE",
                "job_description": "Architect, troubleshoot, and scale AWS infrastructure for global enterprise customers.",
                "job_type": "FULL_TIME",
                "work_location": "Bengaluru / Chennai",
                "compensation_details": "CTC: 19.0 LPA (Base: 13.5 LPA + Sign-on: 3.5 LPA + Stocks)",
                "tier": "SUPER_DREAM",
                "graduation_year": 2026,
                "min_cgpa": 7.0,
                "grading_scale": 10.0,
                "max_active_backlogs": 1,
                "max_total_backlogs": 2,
                "allowed_genders": "ALL",
                "application_deadline": now + timedelta(days=28),
                "application_instructions": "Online coding assessment followed by 2 technical interview rounds.",
                "contact_email": "placements@campus.edu",
                "status": "PUBLISHED",
                "published_at": now,
                "coordinator_id": admin_id,
            },
            {
                "company_name": "Infosys",
                "company_description": "Next-generation digital services and consulting multinational corporation.",
                "company_website": "https://infosys.com",
                "title": "Infosys Specialist Programmer Campus Drive",
                "job_role": "Specialist Programmer (SP)",
                "job_description": "High-complexity software engineering, full-stack application development, and AI engineering.",
                "job_type": "FULL_TIME",
                "work_location": "Mysuru / Bengaluru / Pune",
                "compensation_details": "CTC: 9.5 LPA",
                "tier": "REGULAR",
                "graduation_year": 2026,
                "min_cgpa": 6.5,
                "grading_scale": 10.0,
                "max_active_backlogs": 1,
                "max_total_backlogs": 2,
                "allowed_genders": "ALL",
                "application_deadline": now + timedelta(days=40),
                "application_instructions": "HackWithInfy qualifiers and direct test applicants eligible.",
                "contact_email": "infosys-campus@campus.edu",
                "status": "PUBLISHED",
                "published_at": now - timedelta(days=3),
                "coordinator_id": admin_id,
            },
        ]

        inserted_drives = []
        for d in drives_data:
            existing = conn.execute(
                text("SELECT id FROM placement_drives WHERE company_name = :c AND job_role = :r"),
                {"c": d["company_name"], "r": d["job_role"]}
            ).fetchone()

            if existing:
                drive_id = existing[0]
            else:
                drive_id = conn.execute(
                    text("""
                        INSERT INTO placement_drives (
                            company_name, company_description, company_website,
                            title, job_role, job_description, job_type,
                            work_location, compensation_details, tier,
                            eligible_department_ids,
                            graduation_year, min_cgpa, grading_scale,
                            max_active_backlogs, max_total_backlogs, allowed_genders,
                            application_deadline, application_instructions, contact_email,
                            status, published_at, coordinator_id, created_by,
                            created_at, updated_at
                        ) VALUES (
                            :company_name, :company_description, :company_website,
                            :title, :job_role, :job_description, :job_type,
                            :work_location, :compensation_details, :tier,
                            :eligible_department_ids,
                            :graduation_year, :min_cgpa, :grading_scale,
                            :max_active_backlogs, :max_total_backlogs, :allowed_genders,
                            :application_deadline, :application_instructions, :contact_email,
                            :status, :published_at, :coordinator_id, :coordinator_id,
                            :now, :now
                        ) RETURNING id
                    """),
                    {**d, "eligible_department_ids": json.dumps(dept_ids), "now": now}
                ).scalar()

            inserted_drives.append(drive_id)

            # Seed schedules / rounds for drive
            rounds = [
                ("Online Coding Assessment", "ONLINE_TEST", 1, now + timedelta(days=16), now + timedelta(days=16, hours=2), True, "https://assessment.campus.edu/test"),
                ("Technical Interview Round 1", "TECHNICAL_INTERVIEW", 2, now + timedelta(days=19), now + timedelta(days=19, hours=4), False, "Campus CDC Interview Block A"),
                ("HR & Culture Discussion", "HR_INTERVIEW", 3, now + timedelta(days=22), now + timedelta(days=22, hours=3), False, "Campus CDC Boardroom"),
            ]
            for title, rtype, order, st, et, is_on, venue in rounds:
                conn.execute(
                    text("""
                        INSERT INTO placement_schedules (
                            drive_id, round_order, title, round_type,
                            start_time, end_time, is_online,
                            meeting_link, venue_name, created_at
                        ) VALUES (
                            :drive_id, :order, :title, :rtype,
                            :st, :et, :is_on,
                            :link, :venue, :now
                        )
                        ON CONFLICT DO NOTHING
                    """),
                    {
                        "drive_id": drive_id,
                        "order": order,
                        "title": title,
                        "rtype": rtype,
                        "st": st,
                        "et": et,
                        "is_on": is_on,
                        "link": venue if is_on else None,
                        "venue": venue if not is_on else "Online Portal",
                        "now": now,
                    }
                )

        # 3. Seed Placement Applications
        print("[seed] Seeding candidate applications...")
        sample_student = student_rows[0]
        sample_student_id = sample_student[0]
        sample_student_2 = student_rows[1] if len(student_rows) > 1 else sample_student

        applications_seed = [
            (inserted_drives[0], sample_student_id, "SHORTLISTED", "https://drive.google.com/file/d/sample-resume-1/view", "Proficient in Python, C++, and Distributed Systems."),
            (inserted_drives[1], sample_student_id, "APPLIED", "https://drive.google.com/file/d/sample-resume-1/view", "Azure Certified Developer Associate. Completed cloud capstone project."),
            (inserted_drives[0], sample_student_2[0], "APPLIED", "https://drive.google.com/file/d/sample-resume-2/view", "Full stack engineer with React & Node experience."),
        ]

        for drive_id, st_id, status, res_url, notes in applications_seed:
            conn.execute(
                text("""
                    INSERT INTO placement_applications (
                        drive_id, student_id, status, resume_url, notes,
                        applied_at, updated_at
                    ) VALUES (
                        :drive_id, :st_id, :status, :res_url, :notes,
                        :now, :now
                    )
                    ON CONFLICT (drive_id, student_id) DO UPDATE SET
                        status = EXCLUDED.status,
                        notes = EXCLUDED.notes
                """),
                {
                    "drive_id": drive_id,
                    "st_id": st_id,
                    "status": status,
                    "res_url": res_url,
                    "notes": notes,
                    "now": now,
                }
            )

        # 4. Seed Clubs
        print("[seed] Seeding campus clubs...")
        clubs_data = [
            ("AI & Robotics Society", "AIRS", "TECHNICAL", "Advancing artificial intelligence, autonomous robotics, and applied machine learning on campus.", admin_id),
            ("ACM Student Chapter", "ACM-SC", "TECHNICAL", "University chapter of the Association for Computing Machinery. Coding contests, hackathons, and guest lectures.", admin_id),
            ("Literary & Debating Society", "LIT-SOC", "CULTURAL", "Fostering parliamentary debate, creative writing, and public speaking excellence.", admin_id),
            ("Campus Sports & Athletics Club", "SPORT-CL", "SPORTS", "Organizing inter-departmental tournaments in football, basketball, cricket, and badminton.", admin_id),
        ]

        club_ids = []
        for name, code, category, desc, coord in clubs_data:
            existing = conn.execute(text("SELECT id FROM clubs WHERE code = :code"), {"code": code}).fetchone()
            if existing:
                cid = existing[0]
            else:
                cid = conn.execute(
                    text("""
                        INSERT INTO clubs (
                            name, code, category, description, status,
                            created_by, created_at, updated_at
                        ) VALUES (
                            :name, :code, :category, :desc, 'ACTIVE',
                            :coord, :now, :now
                        ) RETURNING id
                    """),
                    {"name": name, "code": code, "category": category, "desc": desc, "coord": coord, "now": now}
                ).scalar()
            club_ids.append(cid)

        # 5. Seed Club Memberships
        print("[seed] Seeding club memberships...")
        # First student joins AIRS and ACM
        target_user_id = sample_student[1]
        for cid in club_ids[:2]:
            conn.execute(
                text("""
                    INSERT INTO club_memberships (
                        club_id, user_id, role, status, joined_at
                    ) VALUES (
                        :cid, :uid, 'MEMBER', 'ACTIVE', :now
                    )
                    ON CONFLICT (club_id, user_id) DO NOTHING
                """),
                {"cid": cid, "uid": target_user_id, "now": now}
            )

        # 6. Seed Campus Events
        print("[seed] Seeding campus events...")
        events_data = [
            {
                "title": "HackSphere 2026: 24-Hour AI & Edge Hackathon",
                "description": "Annual university hackathon focused on edge AI, generative agents, and sustainability. Mentorship and $5,000 prize pool.",
                "category": "HACKATHON",
                "club_id": club_ids[0],
                "start_time": now + timedelta(days=3, hours=10),
                "end_time": now + timedelta(days=4, hours=10),
                "venue_name": "Innovation & Incubation Hub, Central Block",
                "target_audience": "ALL",
                "status": "PUBLISHED",
                "requires_approval": False,
                "coordinator_id": admin_id,
            },
            {
                "title": "Cloud Architecture & Kubernetes Workshop",
                "description": "Hands-on masterclass on containerization, microservice patterns, CI/CD pipelines, and cloud security.",
                "category": "WORKSHOP",
                "club_id": club_ids[1],
                "start_time": now + timedelta(days=7, hours=14),
                "end_time": now + timedelta(days=7, hours=17),
                "venue_name": "Auditorium Hall B",
                "target_audience": "STUDENT",
                "status": "PUBLISHED",
                "requires_approval": False,
                "coordinator_id": admin_id,
            },
            {
                "title": "TechFest 2026: Annual Campus Tech Symposium",
                "description": "Keynote addresses from industry CTOs, project exhibitions, and research paper presentations.",
                "category": "ACADEMIC",
                "club_id": club_ids[0],
                "start_time": now - timedelta(hours=1),
                "end_time": now + timedelta(hours=4),
                "venue_name": "Main Auditorium Complex",
                "target_audience": "ALL",
                "status": "ONGOING",
                "requires_approval": False,
                "coordinator_id": admin_id,
            },
        ]

        event_ids = []
        for ev in events_data:
            existing = conn.execute(
                text("SELECT id FROM campus_events WHERE title = :t"),
                {"t": ev["title"]}
            ).fetchone()

            if existing:
                eid = existing[0]
            else:
                eid = conn.execute(
                    text("""
                        INSERT INTO campus_events (
                            title, description, category, club_id,
                            start_time, end_time, venue_name, target_audience,
                            status, requires_approval, coordinator_id, created_by,
                            version, created_at, updated_at
                        ) VALUES (
                            :title, :description, :category, :club_id,
                            :start_time, :end_time, :venue_name, :target_audience,
                            :status, :requires_approval, :coordinator_id, :coordinator_id,
                            1, :now, :now
                        ) RETURNING id
                    """),
                    {**ev, "now": now}
                ).scalar()
            event_ids.append(eid)

        # 7. Seed Event Registrations
        print("[seed] Seeding event registrations...")
        for eid in event_ids[:2]:
            conn.execute(
                text("""
                    INSERT INTO event_registrations (
                        event_id, user_id, status, notes, registered_at
                    ) VALUES (
                        :eid, :uid, 'CONFIRMED', 'Registered for workshop tracks.', :now
                    )
                    ON CONFLICT (event_id, user_id) DO NOTHING
                """),
                {"eid": eid, "uid": target_user_id, "now": now}
            )

        print("[seed] Seed successfully completed!")

if __name__ == "__main__":
    seed_placements_and_events()
