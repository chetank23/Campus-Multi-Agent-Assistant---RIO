from typing import List
from collections import defaultdict
from pydantic import BaseModel
from backend.schemas.timetable_generation import OptimizerInput, TimetableEntryResult

class ValidationViolation(BaseModel):
    severity: str
    message: str

class ValidationResult(BaseModel):
    is_valid: bool
    violations: List[ValidationViolation]

def validate_timetable(entries: List[TimetableEntryResult], opt_input: OptimizerInput) -> ValidationResult:
    violations = []
    
    courses = {c.id: c for c in opt_input.courses}
    sections = {s.id: s for s in opt_input.sections}
    batches = {b.id: b for b in opt_input.batches}
    rooms = {r.id: r for r in opt_input.rooms}
    labs = {l.room_id: l for l in opt_input.labs}
    faculty = {f.id: f for f in opt_input.faculty}
    slots = {t.id: t for t in opt_input.time_slots}
    assignments = {a.id: a for a in opt_input.course_assignments}
    
    faculty_availability = defaultdict(dict)
    for fa in opt_input.faculty_availability:
        faculty_availability[fa.faculty_id][fa.slot_id] = fa

    faculty_schedule = defaultdict(list)
    section_schedule = defaultdict(list)
    room_schedule = defaultdict(list)
    course_hours_assigned = defaultdict(int)
    
    for entry in entries:
        a = assignments[entry.course_assignment_id]
        
        # 1. Faculty collision
        if entry.slot_id in faculty_schedule[a.faculty_id]:
            violations.append(ValidationViolation(severity="HARD", message=f"Faculty {a.faculty_id} double-booked in slot {entry.slot_id}"))
        faculty_schedule[a.faculty_id].append(entry.slot_id)
        
        # 2. Section collision
        if a.section_id:
            if entry.slot_id in section_schedule[a.section_id]:
                violations.append(ValidationViolation(severity="HARD", message=f"Section {a.section_id} double-booked in slot {entry.slot_id}"))
            section_schedule[a.section_id].append(entry.slot_id)
            
        # 3. Room collision
        if entry.slot_id in room_schedule[entry.room_id]:
            violations.append(ValidationViolation(severity="HARD", message=f"Room {entry.room_id} double-booked in slot {entry.slot_id}"))
        room_schedule[entry.room_id].append(entry.slot_id)
        
        # 4. Capacity and Lab requirements
        student_count = sections[a.section_id].student_count if a.section_id else (batches[a.batch_id].student_count if a.batch_id else 0)
        room = rooms[entry.room_id]
        if room.capacity < student_count:
            violations.append(ValidationViolation(severity="HARD", message=f"Room {room.id} capacity ({room.capacity}) insufficient for {student_count} students"))
            
        if entry.hour_type == 'PRACTICAL':
            if room.room_type != 'LAB' or room.id not in labs:
                violations.append(ValidationViolation(severity="HARD", message=f"Practical hour for assignment {a.id} scheduled in non-lab room {room.id}"))
                
        # 5. Faculty Availability
        fa = faculty_availability[a.faculty_id].get(entry.slot_id)
        if fa and fa.availability == 'UNAVAILABLE':
            violations.append(ValidationViolation(severity="HARD", message=f"Faculty {a.faculty_id} scheduled during UNAVAILABLE slot {entry.slot_id}"))
            
        course_hours_assigned[(entry.course_assignment_id, entry.hour_type)] += 1

    # 6. Required Course Hours
    for a in assignments.values():
        c = courses[a.course_id]
        req_theory = c.lecture_hours + c.tutorial_hours
        req_practical = c.practical_hours
        
        if req_theory > 0:
            assigned = course_hours_assigned.get((a.id, 'THEORY'), 0)
            if assigned != req_theory:
                violations.append(ValidationViolation(severity="HARD", message=f"Assignment {a.id} missing THEORY hours: required {req_theory}, got {assigned}"))
                
        if req_practical > 0:
            assigned = course_hours_assigned.get((a.id, 'PRACTICAL'), 0)
            if assigned != req_practical:
                violations.append(ValidationViolation(severity="HARD", message=f"Assignment {a.id} missing PRACTICAL hours: required {req_practical}, got {assigned}"))

    # 7. Elective Groups
    elective_groups = {eg.id: eg for eg in opt_input.elective_groups}
    eg_courses = defaultdict(list)
    for egc in opt_input.elective_group_courses:
        eg_courses[egc.group_id].append(egc.course_id)
        
    for eg_id, course_ids in eg_courses.items():
        eg_schedule = defaultdict(int)
        for entry in entries:
            a = assignments[entry.course_assignment_id]
            if a.course_id in course_ids:
                if a.section_id is not None:
                    eg_schedule[(a.section_id, entry.slot_id)] += 1
                else:
                    for s_id in sections.keys():
                        eg_schedule[(s_id, entry.slot_id)] += 1
                        
        for (s_id, t_id), count in eg_schedule.items():
            if count > 1:
                violations.append(ValidationViolation(severity="HARD", message=f"Elective group {eg_id} has {count} overlapping courses in slot {t_id} for section {s_id}"))

    return ValidationResult(
        is_valid=len(violations) == 0,
        violations=violations
    )
