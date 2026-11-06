"""
scripts/import_aids_a_dataset.py
---------------------------------
Authoritative, idempotent data importer for AIDS-A master test dataset.
Imports:
  1. Department (AI & DS), Program (B.Tech AI & DS), Academic Year (2026-2027),
     Semester (VII), Section (AIDS-A), Batch (2023).
  2. Faculty (Dr. Nimrita Koul as Class Teacher + other subject faculty).
  3. Subjects & Course Assignments.
  4. Building (SIR M VISHWESH BLOCK: 9 floors, 225 rooms, 18 labs).
  5. Time Slots (9 periods, 6 days, TEA BREAK & LUNCH BREAK).
  6. 60 Students (R23EH001 - R23EH060) with deterministic test accounts.
  7. Reference Timetable version and entries.
  8. Git-ignored test credentials report: aids_a_seed_credentials.json.

Safety:
  Targets isolated PostgreSQL test database on port 5433.
  Idempotent: safe to run multiple times without duplicating records.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Ensure project root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.core.security import get_password_hash
from backend.models.academic import (
    AcademicYear,
    Batch,
    Department,
    Faculty,
    Program,
    Section,
    Semester,
    Student,
)
from backend.models.courses import (
    Course,
    CourseAssignment,
    ElectiveGroup,
    ElectiveGroupCourse,
)
from backend.models.identity import User
from backend.models.space_time import (
    Building,
    FacultyAvailability,
    Lab,
    Room,
    TimeSlot,
)
from backend.models.timetable import (
    TimetableEntry,
    TimetableVersion,
)

REPO_RAW_DATA_PATH = REPO_ROOT / "data" / "raw" / "RIO_MJP_AIDS_A_Clean_Merged_Test_Data.xlsx"
FALLBACK_USER_UPLOAD_PATH = Path(r"C:/Users/Chethan Kumar/.gemini/antigravity/brain/76a7f300-364a-4771-833a-c7670d38435c/.user_uploaded/media_1793980094606_098e9839.xlsx")


def resolve_excel_path(path_arg: Optional[str | Path] = None) -> Path:
    """Resolve authoritative path to the AIDS-A test dataset workbook."""
    if path_arg and Path(path_arg).exists():
        return Path(path_arg)
    env_path = os.environ.get("AIDS_A_EXCEL_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    if REPO_RAW_DATA_PATH.exists():
        return REPO_RAW_DATA_PATH
    if FALLBACK_USER_UPLOAD_PATH.exists():
        return FALLBACK_USER_UPLOAD_PATH
    return REPO_RAW_DATA_PATH


def safe_int(val: Any, default: int = 0) -> int:
    """Safely convert any cell or string value to integer without raising ValueError/TypeError."""
    if val is None:
        return default
    if isinstance(val, bool):
        return int(val)
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip()
    if not s:
        return default
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return default


DEFAULT_EXCEL_PATH = str(REPO_RAW_DATA_PATH)
CREDENTIALS_REPORT_PATH = REPO_ROOT / "aids_a_seed_credentials.json"
DEFAULT_TEST_PASSWORD = "Password@123"


def get_db_session(db_url: str) -> Session:
    if "options" not in db_url:
        sep = "&" if "?" in db_url else "?"
        db_url = f"{db_url}{sep}options=-csearch_path%3Dtest_schema"
    engine = create_engine(db_url)
    SessionMaker = sessionmaker(bind=engine)
    session = SessionMaker()
    session.execute(text("SET search_path TO test_schema, public;"))
    return session


def import_aids_a_dataset(
    db: Session,
    excel_path: Optional[str | Path] = None,
    test_password: str = DEFAULT_TEST_PASSWORD,
    configure_candidate_rooms: bool = True,
) -> Dict[str, Any]:
    resolved_path = resolve_excel_path(excel_path)
    print(f"[*] Opening Excel workbook: {resolved_path}")
    wb = openpyxl.load_workbook(str(resolved_path), data_only=True)

    pw_hash = get_password_hash(test_password)
    report_data: Dict[str, Any] = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "database_target": "campus_ai_test (isolated)",
        "default_test_password": test_password,
        "faculty_accounts": [],
        "student_accounts": [],
        "import_summary": {},
    }

    # =========================================================================
    # 1. ACADEMIC STRUCTURE (Department, Program, AcademicYear, Semester, Section, Batch)
    # =========================================================================
    print("[*] 1. Importing Academic Structure...")
    # Department
    dept = db.query(Department).filter(
        (Department.department_code == "AIDS") | (Department.name == "AI & DS")
    ).first()
    if not dept:
        dept = Department(department_code="AIDS", name="AI & DS")
        db.add(dept)
        db.flush()
    else:
        dept.department_code = "AIDS"
        dept.name = "AI & DS"
        db.flush()

    # Program
    prog = db.query(Program).filter(
        Program.department_id == dept.id,
        (Program.program_name == "B.Tech Artificial Intelligence and Data Science")
        | (Program.program_name == "B.Tech AI & DS"),
    ).first()
    if not prog:
        prog = Program(
            department_id=dept.id,
            program_name="B.Tech Artificial Intelligence and Data Science",
            degree="B.Tech",
            duration=4,
        )
        db.add(prog)
        db.flush()

    # Academic Year
    ay = db.query(AcademicYear).filter(AcademicYear.name == "2026-2027").first()
    if not ay:
        ay = AcademicYear(
            name="2026-2027",
            start_date=datetime.date(2026, 7, 27),
            end_date=datetime.date(2027, 6, 30),
        )
        db.add(ay)
        db.flush()

    # Semester (Semester VII / 7)
    sem = db.query(Semester).filter(
        Semester.academic_year_id == ay.id,
        Semester.semester_number == 7,
    ).first()
    if not sem:
        sem = Semester(
            academic_year_id=ay.id,
            semester_number=7,
            start_date=datetime.date(2026, 7, 27),
            end_date=datetime.date(2026, 12, 31),
        )
        db.add(sem)
        db.flush()

    # Section AIDS-A
    sec = db.query(Section).filter(
        Section.department_id == dept.id,
        Section.semester_id == sem.id,
        Section.section_name == "AIDS-A",
    ).first()
    if not sec:
        sec = Section(
            department_id=dept.id,
            program_id=prog.id,
            semester_id=sem.id,
            section_name="AIDS-A",
            student_count=60,
        )
        db.add(sec)
        db.flush()
    else:
        sec.program_id = prog.id
        sec.student_count = 60
        db.flush()

    # Batch 2023
    batch = db.query(Batch).filter(
        Batch.section_id == sec.id,
        Batch.batch_name == "2023",
    ).first()
    if not batch:
        batch = Batch(
            section_id=sec.id,
            batch_name="2023",
            student_count=60,
        )
        db.add(batch)
        db.flush()

    # =========================================================================
    # 2. FACULTY RECORDS (Faculty Sheet)
    # =========================================================================
    print("[*] 2. Importing Faculty...")
    faculty_sheet = wb["Faculty"]
    faculty_rows = list(faculty_sheet.iter_rows(values_only=True))[1:]

    faculty_map: Dict[str, Faculty] = {}

    for row in faculty_rows:
        if not row or not row[0]:
            continue
        fac_name = str(row[0]).strip()
        designation = str(row[1]).strip() if row[1] and row[1] != "Not stated" else "Faculty Member"
        dept_text = str(row[2]).strip() if row[2] and row[2] != "Not stated" else "AI & DS"
        specialization = str(row[3]).strip() if row[3] else None
        qualification = str(row[4]).strip() if row[4] else None
        experience = str(row[5]).strip() if row[5] else None
        contact = str(row[6]).strip() if row[6] else None

        # Build clean deterministic email
        # e.g. Dr. Nimrita Koul -> nimrita.koul@rio-mjp.test
        clean_prefix = (
            fac_name.lower()
            .replace("dr.", "")
            .replace("prof.", "")
            .strip()
            .replace(" ", ".")
            .replace("..", ".")
        )
        fac_email = f"{clean_prefix}@rio-mjp.test"

        # User account
        fac_user = db.query(User).filter(User.email == fac_email).first()
        if not fac_user:
            fac_user = User(
                email=fac_email,
                name=fac_name,
                password_hash=pw_hash,
                role="FACULTY",
                department_id=dept.id,
                is_active=True,
            )
            db.add(fac_user)
            db.flush()
        else:
            fac_user.name = fac_name
            fac_user.role = "FACULTY"
            fac_user.department_id = dept.id
            fac_user.password_hash = pw_hash
            db.flush()

        # Faculty record
        fac_rec = db.query(Faculty).filter(Faculty.user_id == fac_user.id).first()
        if not fac_rec:
            # Code from initials
            initials = "".join([w[0] for w in fac_name.replace(".", "").split() if w])
            fac_code = f"FAC-{initials[:4].upper()}-{fac_user.id}"
            fac_rec = Faculty(
                user_id=fac_user.id,
                faculty_id=fac_code,
                department_id=dept.id,
                designation=designation,
                contact_number=contact,
                specialization=specialization,
                areas_of_interest=qualification or specialization,
                max_weekly_load=16,
            )
            db.add(fac_rec)
            db.flush()
        else:
            fac_rec.department_id = dept.id
            fac_rec.designation = designation
            fac_rec.contact_number = contact or fac_rec.contact_number
            if specialization:
                fac_rec.specialization = specialization
            db.flush()

        faculty_map[fac_name] = fac_rec
        report_data["faculty_accounts"].append({
            "name": fac_name,
            "email": fac_email,
            "role": "FACULTY",
            "faculty_id": fac_rec.faculty_id,
            "designation": designation,
            "contact": contact,
            "is_class_teacher": (fac_name == "Dr. Nimrita Koul"),
        })

    # Explicitly link Dr. Nimrita Koul as Class Teacher of AIDS-A
    nimrita_fac = faculty_map.get("Dr. Nimrita Koul")
    if nimrita_fac:
        sec.class_teacher_id = nimrita_fac.id
        db.flush()
        print(f"  [+] Connected Dr. Nimrita Koul (id={nimrita_fac.id}) as Class Teacher of {sec.section_name}")

    # =========================================================================
    # 3. SUBJECTS & COURSE ASSIGNMENTS (Subjects Sheet)
    # =========================================================================
    print("[*] 3. Importing Subjects & Assignments...")
    subjects_sheet = wb["Subjects"]
    subject_rows = list(subjects_sheet.iter_rows(values_only=True))[1:]

    course_map: Dict[str, Course] = {}

    for row in subject_rows:
        if not row or not row[0]:
            continue
        code = str(row[0]).strip()
        short_name = str(row[1]).strip() if row[1] else None
        title = str(row[2]).strip()
        type_str = str(row[3]).strip() if row[3] else "Core"
        group_str = str(row[4]).strip() if row[4] else None
        fac_assigned_str = str(row[5]).strip() if row[5] else None

        # Map to enum: THEORY, LAB, TUTORIAL, PROJECT, ELECTIVE
        if "Elective" in type_str:
            c_type = "ELECTIVE"
        elif "Project" in title or "Project" in type_str or "Internship" in title:
            c_type = "PROJECT"
        elif "Lab" in type_str or "Practical" in type_str:
            c_type = "LAB"
        else:
            c_type = "THEORY"

        # Determine hours / credits defaults for scheduling
        # In AIDS-A curriculum: Theory = 3-4 hours, Project/Internship = 3-6 hours
        is_lab = (c_type == "LAB")
        lec_hours = 3 if c_type in ("THEORY", "ELECTIVE") else 0
        tut_hours = 0
        prac_hours = 3 if is_lab else (3 if c_type == "PROJECT" else 0)
        credits_val = 3

        course = db.query(Course).filter(Course.course_code == code).first()
        if not course:
            course = Course(
                course_code=code,
                course_name=title,
                department_id=dept.id,
                course_type=c_type,
                credits=credits_val,
                lecture_hours=lec_hours,
                tutorial_hours=tut_hours,
                practical_hours=prac_hours,
                requires_lab=is_lab,
            )
            db.add(course)
            db.flush()
        else:
            course.course_name = title
            course.department_id = dept.id
            course.course_type = c_type
            course.credits = credits_val
            course.lecture_hours = lec_hours
            course.practical_hours = prac_hours
            db.flush()

        course_map[code] = course

        # Create CourseAssignment for Section AIDS-A
        # Find which faculty corresponds to fac_assigned_str
        assigned_faculty_objs: List[Faculty] = []
        if fac_assigned_str and fac_assigned_str != "Not specified":
            for fname, fac_obj in faculty_map.items():
                # Check if fname or last name in assigned string
                first_last = fname.replace("Dr.", "").replace("Prof.", "").strip()
                if first_last in fac_assigned_str or fname in fac_assigned_str:
                    assigned_faculty_objs.append(fac_obj)

        if not assigned_faculty_objs and "Dr. Nimrita Koul" in fac_assigned_str if fac_assigned_str else False:
            if nimrita_fac:
                assigned_faculty_objs.append(nimrita_fac)

        # Default fallback to Nimrita Koul for core AIDS-A hardcore courses
        if not assigned_faculty_objs and code in ("B25CS0701", "B22EF0704", "B22EH0704"):
            if nimrita_fac:
                assigned_faculty_objs.append(nimrita_fac)

        for af in assigned_faculty_objs:
            ca = db.query(CourseAssignment).filter(
                CourseAssignment.course_id == course.id,
                CourseAssignment.section_id == sec.id,
                CourseAssignment.faculty_id == af.id,
            ).first()
            if not ca:
                ca = CourseAssignment(
                    course_id=course.id,
                    faculty_id=af.id,
                    section_id=sec.id,
                    batch_id=batch.id,
                )
                db.add(ca)
                db.flush()

    # =========================================================================
    # 4. BUILDING, FLOORS, ROOMS & LABS (Buildings, Floors, Rooms Sheets)
    # =========================================================================
    print("[*] 4. Importing Buildings, Rooms & Labs...")
    # Building
    bldg = db.query(Building).filter(
        (Building.code == "SMV-BLK-01") | (Building.name == "SIR M VISHWESH BLOCK")
    ).first()
    if not bldg:
        bldg = Building(
            name="SIR M VISHWESH BLOCK",
            code="SMV-BLK-01",
            location="Main Campus, Academic Zone",
            number_of_floors=9,
        )
        db.add(bldg)
        db.flush()
    else:
        bldg.name = "SIR M VISHWESH BLOCK"
        bldg.code = "SMV-BLK-01"
        bldg.number_of_floors = 9
        db.flush()

    rooms_sheet = wb["Rooms"]
    room_rows = list(rooms_sheet.iter_rows(values_only=True))[1:]

    rooms_imported = 0
    labs_imported = 0

    for r_row in room_rows:
        if not r_row or not r_row[5]:
            continue
        floor_idx = safe_int(r_row[2], default=0)
        floor_name = str(r_row[3]).strip() if r_row[3] else "Floor"
        room_no = str(r_row[5]).strip()
        code_str = str(r_row[6]).strip() if r_row[6] else room_no
        type_str = str(r_row[7]).strip() if r_row[7] else "Room"
        lab_name = str(r_row[8]).strip() if r_row[8] else None
        status_str = str(r_row[11]).strip() if r_row[11] else "Needs Setup"

        is_lab = ("Lab" in type_str) or (lab_name is not None)
        room_type = "LAB" if is_lab else "CLASSROOM"

        # Check existing room in this building
        room = db.query(Room).filter(
            Room.building_id == bldg.id,
            Room.room_number == room_no,
        ).first()

        # In testing default configuration:
        # Ground and 1st floor rooms 101, 102, 103, 104, 105, 001, 002, G-08, G-09, F-08, F-09
        # are configured with active status and standard capacity (60 for classrooms, 40 for labs)
        # to allow CP-SAT solver and timetabling engine to schedule classes.
        is_candidate = configure_candidate_rooms and (floor_idx in (0, 1, 2) and safe_int(room_no.split("-")[-1], default=999) <= 10)
        room_capacity = 60 if is_candidate else None
        room_status = "ACTIVE" if is_candidate else status_str

        if not room:
            room = Room(
                building_id=bldg.id,
                room_number=room_no,
                floor_number=floor_idx,
                capacity=room_capacity,
                room_type=room_type,
                department_id=dept.id,
                has_projector=True if is_candidate else False,
                has_smart_board=True if is_candidate else False,
                status=room_status,
            )
            db.add(room)
            db.flush()
        else:
            room.floor_number = floor_idx
            room.room_type = room_type
            if is_candidate:
                room.capacity = room_capacity
                room.status = "ACTIVE"
            db.flush()

        rooms_imported += 1

        if is_lab:
            lab = db.query(Lab).filter(Lab.room_id == room.id).first()
            if not lab:
                lab = Lab(
                    room_id=room.id,
                    lab_name=lab_name or f"Lab {code_str}",
                    department_id=dept.id,
                    computer_count=35 if is_candidate else 0,
                    equipment="High-Performance AI Workstations",
                    software="PyTorch, TensorFlow, Python 3.13, JupyterLab",
                )
                db.add(lab)
                db.flush()
            labs_imported += 1

    print(f"  [+] Imported {rooms_imported} rooms, {labs_imported} labs in {bldg.name}")

    # =========================================================================
    # 5. PERIODS & TIME SLOTS (Periods Sheet)
    # =========================================================================
    print("[*] 5. Importing Periods & Time Slots...")
    periods_sheet = wb["Periods"]
    period_rows = list(periods_sheet.iter_rows(values_only=True))[1:]

    # Working days: Monday to Saturday
    working_days = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]
    time_slots_created = 0

    slots_by_day_and_period: Dict[Tuple[str, str], TimeSlot] = {}

    for day in working_days:
        for p_row in period_rows:
            if not p_row or not p_row[0]:
                continue
            period_label = str(p_row[0]).strip()
            st_str = str(p_row[1]).strip()
            et_str = str(p_row[2]).strip()
            slot_kind = str(p_row[3]).strip()

            st = datetime.time.fromisoformat(st_str[:5])
            et = datetime.time.fromisoformat(et_str[:5])

            if "TEA" in period_label:
                slot_type = "BREAK"
            elif "LUNCH" in period_label:
                slot_type = "LUNCH"
            else:
                slot_type = "CLASS"

            ts = db.query(TimeSlot).filter(
                TimeSlot.day == day,
                TimeSlot.start_time == st,
                TimeSlot.end_time == et,
            ).first()

            if not ts:
                ts = TimeSlot(
                    day=day,
                    start_time=st,
                    end_time=et,
                    slot_type=slot_type,
                )
                db.add(ts)
                db.flush()
                time_slots_created += 1
            else:
                ts.slot_type = slot_type
                db.flush()

            slots_by_day_and_period[(day, period_label)] = ts

    print(f"  [+] Ensured {len(slots_by_day_and_period)} time slots across 6 working days")

    # Set faculty availability for all CLASS slots
    all_faculties = db.query(Faculty).filter(Faculty.department_id == dept.id).all()
    all_class_slots = db.query(TimeSlot).filter(TimeSlot.slot_type == "CLASS").all()
    for f in all_faculties:
        for cs in all_class_slots:
            fa = db.query(FacultyAvailability).filter(
                FacultyAvailability.faculty_id == f.id,
                FacultyAvailability.slot_id == cs.id,
            ).first()
            if not fa:
                fa = FacultyAvailability(
                    faculty_id=f.id,
                    slot_id=cs.id,
                    availability="AVAILABLE",
                    preference=1,
                )
                db.add(fa)
    db.flush()

    # =========================================================================
    # 6. STUDENTS & TEST ACCOUNTS (Students Sheet: 60 students R23EH001 - R23EH060)
    # =========================================================================
    print("[*] 6. Importing 60 Students (R23EH001 - R23EH060)...")
    students_sheet = wb["Students"]
    student_rows = list(students_sheet.iter_rows(values_only=True))[1:]

    students_imported = 0
    for s_row in student_rows:
        if not s_row or not s_row[0]:
            continue
        srn = str(s_row[0]).strip().upper()
        raw_name = str(s_row[1]).strip() if s_row[1] else None
        # Preserve empty name; do not invent fake names
        student_name = raw_name if raw_name else ""

        # Deterministic local test email
        # R23EH001 -> r23eh001@rio-mjp.test
        student_email = f"{srn.lower()}@rio-mjp.test"

        # User account
        stu_user = db.query(User).filter(User.email == student_email).first()
        if not stu_user:
            stu_user = User(
                email=student_email,
                name=student_name,
                password_hash=pw_hash,
                role="STUDENT",
                department_id=dept.id,
                is_active=True,
            )
            db.add(stu_user)
            db.flush()
        else:
            stu_user.name = student_name
            stu_user.role = "STUDENT"
            stu_user.department_id = dept.id
            stu_user.password_hash = pw_hash
            db.flush()

        # Student academic record
        stu_rec = db.query(Student).filter(Student.student_id == srn).first()
        if not stu_rec:
            stu_rec = Student(
                user_id=stu_user.id,
                student_id=srn,
                department_id=dept.id,
                program_id=prog.id,
                semester_id=sem.id,
                section_id=sec.id,
                batch_id=batch.id,
            )
            db.add(stu_rec)
            db.flush()
        else:
            stu_rec.user_id = stu_user.id
            stu_rec.department_id = dept.id
            stu_rec.program_id = prog.id
            stu_rec.semester_id = sem.id
            stu_rec.section_id = sec.id
            stu_rec.batch_id = batch.id
            db.flush()

        students_imported += 1
        report_data["student_accounts"].append({
            "srn": srn,
            "name": student_name or "(Blank / Not Provided)",
            "email": student_email,
            "role": "STUDENT",
            "section": sec.section_name,
            "batch": "2023",
            "class_teacher": "Dr. Nimrita Koul",
            "account_status": "PROVISIONED",
        })

    print(f"  [+] Imported {students_imported} student records (SRN R23EH001..R23EH060)")

    # =========================================================================
    # 7. REFERENCE TIMETABLE VERSION & ENTRIES (Timetable Sheet)
    # =========================================================================
    print("[*] 7. Importing Reference Timetable...")
    timetable_sheet = wb["Timetable"]
    tt_rows = list(timetable_sheet.iter_rows(values_only=True))[1:]

    # Reference version (set as PUBLISHED reference so student & faculty views are populated)
    ref_version = db.query(TimetableVersion).filter(
        TimetableVersion.academic_year_id == ay.id,
        TimetableVersion.version_number == "AIDS-A-REF",
    ).first()

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if not ref_version:
        ref_version = TimetableVersion(
            academic_year_id=ay.id,
            version_number="AIDS-A-REF",
            status="PUBLISHED",
            published_at=now_utc,
            reason="Imported Reference Timetable from Master Excel (AIDS-A Semester VII)",
            created_at=now_utc,
        )
        db.add(ref_version)
        db.flush()
    else:
        ref_version.status = "PUBLISHED"
        if not ref_version.published_at:
            ref_version.published_at = now_utc
        db.flush()

    # Pick a classroom from SMV-BLK-01 for reference entries (e.g. 101 or 001)
    ref_room = db.query(Room).filter(Room.building_id == bldg.id, Room.room_type == "CLASSROOM").first()
    ref_lab = db.query(Room).filter(Room.building_id == bldg.id, Room.room_type == "LAB").first()

    tt_entries_count = 0
    for t_row in tt_rows:
        if not t_row or not t_row[0]:
            continue
        day_str = str(t_row[0]).strip().upper()
        period_str = str(t_row[1]).strip()
        subj_activity = str(t_row[3]).strip() if t_row[3] else None

        if not subj_activity or subj_activity in ("TEA BREAK", "LUNCH BREAK"):
            continue

        ts = slots_by_day_and_period.get((day_str, period_str))
        if not ts:
            continue

        # Match course
        matched_course: Optional[Course] = None
        matched_fac = nimrita_fac

        if "PFL" in subj_activity:
            matched_course = course_map.get("B25CS0701")
            matched_fac = nimrita_fac
        elif "PP-1" in subj_activity:
            matched_course = course_map.get("B22EH0704")
            matched_fac = nimrita_fac
        elif "Internship" in subj_activity:
            matched_course = course_map.get("B22EF0704")
            matched_fac = nimrita_fac
        elif "ECET" in subj_activity:
            matched_course = course_map.get("B25CSS712")
            matched_fac = faculty_map.get("Prof. Suhasini N") or nimrita_fac
        elif "PE-6" in subj_activity:
            matched_course = course_map.get("B23EAS701") or course_map.get("B25CSS712")
            matched_fac = faculty_map.get("Prof. Aarthy G") or nimrita_fac
        elif "OE-3" in subj_activity:
            matched_course = course_map.get("B23ASO711")
            matched_fac = faculty_map.get("Prof. Kiran M") or nimrita_fac
        elif "OE-4" in subj_activity:
            matched_course = course_map.get("B23MEO720")
            matched_fac = faculty_map.get("Prof. K Jeevan Pradeep") or nimrita_fac

        if not matched_course:
            # Fallback to general course
            matched_course = list(course_map.values())[0]

        entry = db.query(TimetableEntry).filter(
            TimetableEntry.version_id == ref_version.id,
            TimetableEntry.slot_id == ts.id,
            TimetableEntry.section_id == sec.id,
        ).first()

        chosen_room = ref_lab if matched_course.requires_lab else ref_room

        if not entry:
            entry = TimetableEntry(
                version_id=ref_version.id,
                department_id=dept.id,
                program_id=prog.id,
                semester_id=sem.id,
                section_id=sec.id,
                batch_id=batch.id,
                course_id=matched_course.id,
                faculty_id=matched_fac.id if matched_fac else None,
                room_id=chosen_room.id if chosen_room else None,
                slot_id=ts.id,
                status="ACTIVE",
            )
            db.add(entry)
            db.flush()
            tt_entries_count += 1
        else:
            entry.status = "ACTIVE"
            db.flush()

    print(f"  [+] Saved reference timetable entries: {tt_entries_count}")

    # Commit all changes atomically
    db.commit()

    # Write Git-ignored Credentials Report
    report_data["import_summary"] = {
        "department": dept.name,
        "program": prog.program_name,
        "academic_year": ay.name,
        "semester": sem.semester_number,
        "section": sec.section_name,
        "class_teacher": "Dr. Nimrita Koul",
        "building": bldg.name,
        "total_rooms": rooms_imported,
        "total_labs": labs_imported,
        "total_students": students_imported,
        "reference_timetable_version": ref_version.version_number,
    }

    with open(CREDENTIALS_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    print(f"[SUCCESS] AIDS-A Master Dataset imported successfully.")
    print(f"[REPORT] Saved Git-ignored seed credentials to: {CREDENTIALS_REPORT_PATH}")
    return report_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import AIDS-A Master Test Data")
    parser.add_argument("--excel", default=DEFAULT_EXCEL_PATH, help="Path to Excel workbook")
    parser.add_argument("--db-url", default=None, help="Database connection URL")
    args = parser.parse_args()

    target_url = (
        args.db_url
        or os.environ.get("TEST_DATABASE_URL")
        or "postgresql+psycopg://campus_user:@127.0.0.1:5433/campus_ai_test?options=-csearch_path%3Dtest_schema"
    )

    print(f"Connecting to: {target_url}")
    session = get_db_session(target_url)
    try:
        import_aids_a_dataset(session, excel_path=args.excel)
    finally:
        session.close()
