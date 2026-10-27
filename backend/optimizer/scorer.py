import math
from typing import List, Dict
from collections import defaultdict
from backend.schemas.timetable_generation import OptimizerInput, TimetableEntryResult
from backend.optimizer.validator import ValidationResult

def compute_score(validation_result: ValidationResult, entries: List[TimetableEntryResult], opt_input: OptimizerInput) -> dict:
    """
    Computes a deterministic quality score [0, 100] based on the exact normalizations 
    derived from the dataset boundaries.
    """
    
    # 1. Weights
    W_FACULTY_GAP = 10.0
    W_STUDENT_GAP = 10.0
    W_PREFERRED_SLOT = 5.0
    W_ROOM_CHANGE = 5.0
    W_LATE_LAB = 20.0
    W_WORKLOAD_BALANCE = 15.0

    # Lookups
    assignments = {a.id: a for a in opt_input.course_assignments}
    courses = {c.id: c for c in opt_input.courses}
    slots = {t.id: t for t in opt_input.time_slots}
    faculty = {f.id: f for f in opt_input.faculty}
    rooms = {r.id: r for r in opt_input.rooms}
    
    faculty_availability = defaultdict(dict)
    for fa in opt_input.faculty_availability:
        faculty_availability[fa.faculty_id][fa.slot_id] = fa

    slots_by_day = defaultdict(list)
    for t_id, t in slots.items():
        slots_by_day[t.day].append(t_id)

    # Pre-group timetable entries
    f_schedule = defaultdict(lambda: defaultdict(list)) # f_id -> day -> list of slots
    s_schedule = defaultdict(lambda: defaultdict(list)) # s_id -> day -> list of slots
    f_total_hours = defaultdict(int)
    s_room_usage = defaultdict(lambda: defaultdict(set)) # s_id -> day -> set of r_ids
    
    actual_preferred_assigned = 0
    actual_late_labs = 0
    total_lab_slots = 0

    for entry in entries:
        a = assignments[entry.course_assignment_id]
        c = courses[a.course_id]
        t = slots[entry.slot_id]
        
        f_schedule[a.faculty_id][t.day].append(t.id)
        f_total_hours[a.faculty_id] += 1
        
        if a.section_id is not None:
            s_schedule[a.section_id][t.day].append(t.id)
            s_room_usage[a.section_id][t.day].add(entry.room_id)
        else:
            # If elective, applies to all sections in that department/semester (simplified here)
            # To be completely safe and match the validator/solver, we map to all sections of same dept
            sec_matches = [s for s in opt_input.sections if s.department_id == c.department_id]
            for sec in sec_matches:
                s_schedule[sec.id][t.day].append(t.id)
                s_room_usage[sec.id][t.day].add(entry.room_id)

        # Preferred slots
        fa = faculty_availability[a.faculty_id].get(t.id)
        if fa and fa.availability == 'PREFERRED':
            actual_preferred_assigned += 1

        # Late labs
        if entry.hour_type == 'PRACTICAL' or c.course_type == 'LAB':
            total_lab_slots += 1
            if t.start_time.hour >= 14:
                actual_late_labs += 1

    # Component 1: Faculty Gaps
    actual_faculty_gaps = 0
    max_possible_faculty_gaps = 0
    
    for f_id, days in f_schedule.items():
        for day, teaching_slots in days.items():
            if not teaching_slots:
                continue
            day_t_ids = sorted(slots_by_day[day])
            # Find indices
            indices = [day_t_ids.index(t_id) for t_id in teaching_slots]
            first_idx = min(indices)
            last_idx = max(indices)
            
            num_classes = len(teaching_slots)
            actual_gap = (last_idx - first_idx + 1) - num_classes
            actual_faculty_gaps += max(0, actual_gap)
            
            day_slots = len(day_t_ids)
            max_possible_faculty_gaps += max(0, day_slots - num_classes)
            
    faculty_gap_quality = 1.0
    if max_possible_faculty_gaps > 0:
        faculty_gap_quality = 1.0 - (actual_faculty_gaps / max_possible_faculty_gaps)
        faculty_gap_quality = max(0.0, min(1.0, faculty_gap_quality))

    # Component 2: Student Gaps
    actual_student_gaps = 0
    max_possible_student_gaps = 0
    
    for s_id, days in s_schedule.items():
        for day, teaching_slots in days.items():
            if not teaching_slots:
                continue
            # Remove duplicates for student schedule (e.g. parallel electives)
            teaching_slots = list(set(teaching_slots))
            
            day_t_ids = sorted(slots_by_day[day])
            indices = [day_t_ids.index(t_id) for t_id in teaching_slots]
            first_idx = min(indices)
            last_idx = max(indices)
            
            num_classes = len(teaching_slots)
            actual_gap = (last_idx - first_idx + 1) - num_classes
            actual_student_gaps += max(0, actual_gap)
            
            day_slots = len(day_t_ids)
            max_possible_student_gaps += max(0, day_slots - num_classes)
            
    student_gap_quality = 1.0
    if max_possible_student_gaps > 0:
        student_gap_quality = 1.0 - (actual_student_gaps / max_possible_student_gaps)
        student_gap_quality = max(0.0, min(1.0, student_gap_quality))

    # Component 3: Preferred Slots
    max_possible_preferred = 0
    for f in opt_input.faculty:
        total_classes_week = f_total_hours.get(f.id, 0)
        num_preferred_avail = sum(1 for fa in opt_input.faculty_availability if fa.faculty_id == f.id and fa.availability == 'PREFERRED')
        max_possible_preferred += min(total_classes_week, num_preferred_avail)
        
    preferred_slot_quality = 1.0
    if max_possible_preferred > 0:
        preferred_slot_quality = actual_preferred_assigned / max_possible_preferred
        preferred_slot_quality = max(0.0, min(1.0, preferred_slot_quality))

    # Component 4: Room Changes
    actual_room_changes = 0
    max_possible_room_changes = 0
    
    for s_id, days in s_room_usage.items():
        for day, r_ids in days.items():
            num_classes = len(set(s_schedule[s_id][day]))
            if num_classes > 0:
                actual_room_changes += max(0, len(r_ids) - 1)
                max_possible_room_changes += max(0, num_classes - 1)
                
    room_change_quality = 1.0
    if max_possible_room_changes > 0:
        room_change_quality = 1.0 - (actual_room_changes / max_possible_room_changes)
        room_change_quality = max(0.0, min(1.0, room_change_quality))

    # Component 5: Late Labs
    late_lab_quality = 1.0
    if total_lab_slots > 0:
        late_lab_quality = 1.0 - (actual_late_labs / total_lab_slots)
        late_lab_quality = max(0.0, min(1.0, late_lab_quality))

    # Component 6: Workload Balance (Standard Deviation)
    active_faculty = [f.id for f in opt_input.faculty if f_total_hours.get(f.id, 0) > 0]
    workload_stddev = 0.0
    
    max_weekly_load = max([f.max_weekly_load for f in opt_input.faculty]) if opt_input.faculty else 16
    max_possible_stddev = max_weekly_load / 2.0
    
    if len(active_faculty) > 1:
        hours = [f_total_hours.get(f_id, 0) for f_id in active_faculty]
        mean_hours = sum(hours) / len(hours)
        variance = sum((h - mean_hours) ** 2 for h in hours) / len(hours)
        workload_stddev = math.sqrt(variance)
        
    workload_balance_quality = 1.0
    if max_possible_stddev > 0 and len(active_faculty) > 1:
        workload_balance_quality = 1.0 - (workload_stddev / max_possible_stddev)
        workload_balance_quality = max(0.0, min(1.0, workload_balance_quality))

    # Final Composite Score
    total_weights = W_FACULTY_GAP + W_STUDENT_GAP + W_PREFERRED_SLOT + W_ROOM_CHANGE + W_LATE_LAB + W_WORKLOAD_BALANCE
    weighted_quality = (
        W_FACULTY_GAP * faculty_gap_quality +
        W_STUDENT_GAP * student_gap_quality +
        W_PREFERRED_SLOT * preferred_slot_quality +
        W_ROOM_CHANGE * room_change_quality +
        W_LATE_LAB * late_lab_quality +
        W_WORKLOAD_BALANCE * workload_balance_quality
    ) / total_weights if total_weights > 0 else 0.0
    
    total_score = round(weighted_quality * 100, 2)
    
    # Calculate room utilization percentage
    total_slots = len(slots)
    total_rooms = len(rooms)
    max_room_slots = total_slots * total_rooms
    actual_room_slots = len(entries) # assuming each entry takes 1 room for 1 slot
    room_utilization_pct = (actual_room_slots / max_room_slots * 100) if max_room_slots > 0 else 0.0

    # Calculate student gap avg
    student_gap_minutes_avg = 0.0
    if actual_student_gaps > 0:
        # We assume 1 slot = 60 minutes for this simple metric, 
        # or calculate actual time difference
        # Here we just use gaps * 60 / num_active_sections
        num_sections = len(s_schedule)
        if num_sections > 0:
            student_gap_minutes_avg = (actual_student_gaps * 60.0) / num_sections

    return {
        "total_score": total_score,
        "hard_violations": len([v for v in validation_result.violations if v.severity in ("HARD", "BLOCKER")]),
        "soft_violations": actual_faculty_gaps + actual_student_gaps + actual_room_changes + actual_late_labs, 
        "room_utilization_pct": round(room_utilization_pct, 2),
        "faculty_workload_balance": round(workload_stddev, 2),
        "student_gap_minutes_avg": round(student_gap_minutes_avg, 2),
        
        # Individual quality metrics [0, 1] for debugging and transparency
        "faculty_gap_quality": round(faculty_gap_quality, 4),
        "student_gap_quality": round(student_gap_quality, 4),
        "preferred_slot_quality": round(preferred_slot_quality, 4),
        "room_change_quality": round(room_change_quality, 4),
        "late_lab_quality": round(late_lab_quality, 4),
        "workload_balance_quality": round(workload_balance_quality, 4),
    }
