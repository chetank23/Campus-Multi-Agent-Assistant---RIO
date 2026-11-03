from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from backend.models.academic import AcademicYear, Semester, Department, Program, Section, Batch, Faculty
from backend.models.courses import Course, CourseAssignment, ElectiveGroup, ElectiveGroupCourse
from backend.models.space_time import Room, Lab, TimeSlot, FacultyAvailability, AcademicCalendar, Building
from backend.schemas.timetable_generation import (
    GenerationScope, OptimizerInput, OptSection, OptBatch, OptCourse, OptCourseAssignment,
    OptFaculty, OptFacultyAvailability, OptTimeSlot, OptRoom, OptLab,
    OptAcademicCalendar, OptElectiveGroup, OptElectiveGroupCourse
)

def validate_and_load_input(db: Session, scope: GenerationScope) -> OptimizerInput:
    # 1. Validate Academic Scope
    academic_year = db.query(AcademicYear).filter(AcademicYear.id == scope.academic_year_id).first()
    if not academic_year:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Academic year not found")

    semester = db.query(Semester).filter(Semester.id == scope.semester_id, Semester.academic_year_id == scope.academic_year_id).first()
    if not semester:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Semester not found or does not belong to the academic year")

    department = db.query(Department).filter(Department.id == scope.department_id).first()
    if not department:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department not found")

    program = db.query(Program).filter(Program.id == scope.program_id, Program.department_id == scope.department_id).first()
    if not program:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Program not found or does not belong to the department")

    # 2. Sections
    section_query = db.query(Section).filter(
        Section.department_id == scope.department_id,
        Section.program_id == scope.program_id,
        Section.semester_id == scope.semester_id
    )
    if scope.section_ids:
        section_query = section_query.filter(Section.id.in_(scope.section_ids))
    sections_db = section_query.all()
    if not sections_db:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid sections found in the specified scope")
    
    loaded_section_ids = [s.id for s in sections_db]
    if scope.section_ids:
        missing = set(scope.section_ids) - set(loaded_section_ids)
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid section IDs provided: {missing}")

    opt_sections = [
        OptSection(
            id=s.id,
            department_id=s.department_id if s.department_id is not None else scope.department_id,
            program_id=s.program_id if s.program_id is not None else scope.program_id,
            semester_id=s.semester_id if s.semester_id is not None else scope.semester_id,
            student_count=s.student_count or 0,
        )
        for s in sections_db
    ]

    # 3. Batches
    batches_db = db.query(Batch).filter(Batch.section_id.in_(loaded_section_ids)).all()
    opt_batches = [
        OptBatch(id=b.id, section_id=b.section_id, student_count=b.student_count or 0)
        for b in batches_db
        if b.section_id is not None
    ]
    loaded_batch_ids = [b.id for b in batches_db]

    # 4. Course Assignments & Faculty
    # If curriculum_version_id is provided, validate snapshot and ensure course assignments are synced
    if scope.curriculum_version_id:
        from backend.models.curriculum import CurriculumVersion, SectionCourseOffering
        curr_ver = db.query(CurriculumVersion).filter(CurriculumVersion.id == scope.curriculum_version_id).first()
        if not curr_ver:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Curriculum version #{scope.curriculum_version_id} not found.")

        offerings = db.query(SectionCourseOffering).filter(
            SectionCourseOffering.curriculum_version_id == curr_ver.id,
            SectionCourseOffering.academic_year_id == scope.academic_year_id,
            SectionCourseOffering.semester_id == scope.semester_id,
            SectionCourseOffering.section_id.in_(loaded_section_ids),
        ).all()

        for off in offerings:
            sm = off.subject_mapping
            if sm and sm.course_id:
                for fa in off.faculty_allocations:
                    if fa.is_active and fa.faculty_id:
                        ca = db.query(CourseAssignment).filter(
                            CourseAssignment.course_id == sm.course_id,
                            CourseAssignment.faculty_id == fa.faculty_id,
                            CourseAssignment.section_id == off.section_id,
                            CourseAssignment.batch_id == off.batch_id,
                        ).first()
                        if not ca:
                            ca = CourseAssignment(
                                course_id=sm.course_id,
                                faculty_id=fa.faculty_id,
                                section_id=off.section_id,
                                batch_id=off.batch_id,
                            )
                            db.add(ca)
        db.flush()

    # We only care about courses assigned to the loaded sections and batches
    assignments_db = db.query(CourseAssignment).filter(
        (CourseAssignment.section_id.in_(loaded_section_ids)) | (CourseAssignment.batch_id.in_(loaded_batch_ids))
    ).all()
    
    if not assignments_db:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No course assignments found for the selected sections/batches")

    course_ids = list(set(a.course_id for a in assignments_db if a.course_id))
    faculty_ids = list(set(a.faculty_id for a in assignments_db if a.faculty_id))

    opt_assignments = [
        OptCourseAssignment(id=a.id, course_id=a.course_id, faculty_id=a.faculty_id, section_id=a.section_id, batch_id=a.batch_id)
        for a in assignments_db if a.course_id and a.faculty_id
    ]

    # Courses
    courses_db = db.query(Course).filter(Course.id.in_(course_ids)).all()
    opt_courses = [
        OptCourse(
            id=c.id,
            department_id=c.department_id if c.department_id is not None else scope.department_id,
            course_type=c.course_type or "CORE",
            credits=c.credits or 0,
            lecture_hours=c.lecture_hours or 0,
            tutorial_hours=c.tutorial_hours or 0,
            practical_hours=c.practical_hours or 0,
            requires_lab=c.requires_lab,
        )
        for c in courses_db
    ]

    # Faculty
    faculty_db = db.query(Faculty).filter(Faculty.id.in_(faculty_ids)).all()
    opt_faculty = [
        OptFaculty(
            id=f.id,
            department_id=f.department_id if f.department_id is not None else scope.department_id,
            max_weekly_load=f.max_weekly_load,
        )
        for f in faculty_db
    ]

    # Faculty Availability
    fa_db = db.query(FacultyAvailability).filter(FacultyAvailability.faculty_id.in_(faculty_ids)).all()
    opt_fa = [
        OptFacultyAvailability(
            id=fa.id,
            faculty_id=fa.faculty_id,
            slot_id=fa.slot_id,
            availability=fa.availability or "AVAILABLE",
            preference=fa.preference,
        )
        for fa in fa_db
        if fa.faculty_id is not None and fa.slot_id is not None
    ]

    # 5. Time Slots
    ts_query = db.query(TimeSlot)
    if scope.time_slot_ids:
        ts_query = ts_query.filter(TimeSlot.id.in_(scope.time_slot_ids))
    ts_db = ts_query.all()
    if not ts_db:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No time slots found")
    
    loaded_ts_ids = [ts.id for ts in ts_db]
    if scope.time_slot_ids:
        missing = set(scope.time_slot_ids) - set(loaded_ts_ids)
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid time slot IDs: {missing}")

    opt_ts = [
        OptTimeSlot(
            id=ts.id,
            day=ts.day,
            start_time=ts.start_time,
            end_time=ts.end_time,
            slot_type=ts.slot_type or "THEORY",
        )
        for ts in ts_db
        if ts.day is not None and ts.start_time is not None and ts.end_time is not None
    ]

    # 6. Infrastructure (Rooms & Labs)
    room_query = db.query(Room)
    if scope.building_ids:
        # Validate buildings exist
        buildings = db.query(Building).filter(Building.id.in_(scope.building_ids)).all()
        if len(buildings) != len(set(scope.building_ids)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Some building IDs are invalid")
        room_query = room_query.filter(Room.building_id.in_(scope.building_ids))
    if scope.room_ids:
        room_query = room_query.filter(Room.id.in_(scope.room_ids))
    
    rooms_db = room_query.all()
    if not rooms_db:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No rooms found matching the criteria")
    
    loaded_room_ids = [r.id for r in rooms_db]
    if scope.room_ids:
        missing = set(scope.room_ids) - set(loaded_room_ids)
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid room IDs provided: {missing}")
    
    opt_rooms = [
        OptRoom(
            id=r.id,
            building_id=r.building_id,
            capacity=r.capacity or 0,
            room_type=r.room_type or "CLASSROOM",
            department_id=r.department_id,
        )
        for r in rooms_db
        if r.building_id is not None
    ]

    lab_query = db.query(Lab).filter(Lab.room_id.in_(loaded_room_ids))
    if scope.lab_ids:
        lab_query = lab_query.filter(Lab.id.in_(scope.lab_ids))
    labs_db = lab_query.all()
    loaded_lab_ids = [l.id for l in labs_db]
    if scope.lab_ids:
        missing = set(scope.lab_ids) - set(loaded_lab_ids)
        if missing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid lab IDs provided: {missing}")

    opt_labs = [
        OptLab(
            id=l.id,
            room_id=l.room_id,
            department_id=l.department_id if l.department_id is not None else scope.department_id,
        )
        for l in labs_db
        if l.room_id is not None
    ]

    # Check lab requirement logic - if any course requires a lab, we need at least one lab available (or we could let the solver fail later, but fail early is good)
    needs_lab = any(c.requires_lab for c in courses_db)
    if needs_lab and not labs_db:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Courses require labs but no valid labs were provided in the scope")

    # 7. Academic Calendar
    ac_db = db.query(AcademicCalendar).filter(AcademicCalendar.academic_year_id == scope.academic_year_id).all()
    opt_ac = [
        OptAcademicCalendar(id=ac.id, date=ac.date, event_type=ac.event_type or "HOLIDAY")
        for ac in ac_db
        if ac.date is not None
    ]

    # 8. Electives
    eg_db = db.query(ElectiveGroup).filter(
        ElectiveGroup.department_id == scope.department_id,
        ElectiveGroup.semester_id == scope.semester_id
    ).all()
    opt_eg = [
        OptElectiveGroup(
            id=eg.id,
            semester_id=eg.semester_id if eg.semester_id is not None else scope.semester_id,
            department_id=eg.department_id if eg.department_id is not None else scope.department_id,
        )
        for eg in eg_db
    ]
    
    egc_db = []
    if eg_db:
        eg_ids = [eg.id for eg in eg_db]
        egc_db = db.query(ElectiveGroupCourse).filter(ElectiveGroupCourse.group_id.in_(eg_ids)).all()
    opt_egc = [
        OptElectiveGroupCourse(id=egc.id, group_id=egc.group_id, course_id=egc.course_id)
        for egc in egc_db
        if egc.group_id is not None and egc.course_id is not None
    ]

    return OptimizerInput(
        scope=scope,
        sections=opt_sections,
        batches=opt_batches,
        courses=opt_courses,
        course_assignments=opt_assignments,
        faculty=opt_faculty,
        faculty_availability=opt_fa,
        time_slots=opt_ts,
        rooms=opt_rooms,
        labs=opt_labs,
        academic_calendar=opt_ac,
        elective_groups=opt_eg,
        elective_group_courses=opt_egc
    )
