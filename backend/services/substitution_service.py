"""
backend/services/substitution_service.py
----------------------------------------
Business logic for Faculty Substitution:
1. Faculty occurrence querying (inspecting upcoming scheduled classes).
2. Unavailability request lifecycle (creation, duplicate prevention, ownership validation).
3. Deterministic candidate ranking engine:
   - Qualification (direct course assignment, department match)
   - Timetable clash detection at slot
   - Availability check (FacultyAvailability)
   - Existing approved substitution conflicts
   - Workload limit bounds (current weekly hours + 1 <= max_weekly_load)
   - Self-exclusion
   - Deterministic ranking & CANNOT_DETERMINE fail-closed handling
4. Reviewer workflow (approve / reject with optimistic locking & candidate validation).
5. Cancellation workflow.
6. Multi-party notifications (with strict privacy barriers protecting absence reasons).
7. Non-destructive date occurrence overlay for student & faculty schedules.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from backend.models.academic import Department, Faculty, Section, Student
from backend.models.courses import Course, CourseAssignment
from backend.models.events import CoordinatorCapability
from backend.models.identity import User
from backend.models.space_time import FacultyAvailability, Room, TimeSlot
from backend.models.substitution import FacultySubstitution
from backend.models.timetable import TimetableEntry, TimetableVersion
from backend.models.workflow import AuditLog, Notification
from backend.schemas.substitution import (
    CandidateEligibilityReason,
    CandidateRecommendationResponse,
    ClassOccurrenceResponse,
    FacultySubstitutionResponse,
    SubstituteCandidateRecommendation,
)
from backend.services.event_service import check_user_has_capability
from backend.services.notification_service import create_bulk_notifications, create_notification
from backend.utils.datetime_utils import utc_now


DAY_NAME_MAP = {
    0: ("MON", "MONDAY"),
    1: ("TUE", "TUESDAY"),
    2: ("WED", "WEDNESDAY"),
    3: ("THU", "THURSDAY"),
    4: ("FRI", "FRIDAY"),
    5: ("SAT", "SATURDAY"),
    6: ("SUN", "SUNDAY"),
}


def day_matches_date(slot_day: Optional[str], target_date: datetime.date) -> bool:
    """Returns True if the given slot_day matches the day of the week of target_date."""
    if not slot_day:
        return False
    clean_day = slot_day.strip().upper()
    weekday_idx = target_date.weekday()
    short_name, full_name = DAY_NAME_MAP.get(weekday_idx, ("", ""))
    return (
        clean_day == short_name
        or clean_day == full_name
        or clean_day.startswith(short_name)
    )


# ---------------------------------------------------------------------------
# 1. Faculty Class Occurrences
# ---------------------------------------------------------------------------

def list_faculty_upcoming_classes(
    db: Session,
    faculty_user: User,
    from_date: Optional[datetime.date] = None,
    days_ahead: int = 14,
) -> List[ClassOccurrenceResponse]:
    """
    Returns real, scheduled class occurrences for the authenticated faculty member
    across the next `days_ahead` days, strictly derived from published timetable entries.
    Includes active substitution status if an unavailability request exists.
    """
    fac = (
        db.query(Faculty)
        .options(joinedload(Faculty.department))
        .filter(Faculty.user_id == faculty_user.id)
        .first()
    )
    if not fac:
        return []

    start_date = from_date or datetime.date.today()
    end_date = start_date + datetime.timedelta(days=max(1, min(days_ahead, 60)))

    # Fetch all published, active timetable entries for this faculty
    entries = (
        db.query(TimetableEntry)
        .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
        .filter(
            TimetableVersion.status == "PUBLISHED",
            TimetableEntry.faculty_id == fac.id,
            TimetableEntry.status != "CANCELLED",
        )
        .options(
            joinedload(TimetableEntry.course),
            joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(TimetableEntry.slot),
            joinedload(TimetableEntry.section),
            joinedload(TimetableEntry.batch),
            joinedload(TimetableEntry.department),
        )
        .all()
    )

    if not entries:
        return []

    # Pre-fetch any existing substitutions for this faculty in the date range
    existing_subs = (
        db.query(FacultySubstitution)
        .filter(
            FacultySubstitution.original_faculty_id == fac.id,
            FacultySubstitution.substitution_date >= start_date,
            FacultySubstitution.substitution_date <= end_date,
            FacultySubstitution.status.in_(["REQUESTED", "PROPOSED", "APPROVED"]),
        )
        .options(joinedload(FacultySubstitution.substitute_faculty).joinedload(Faculty.user))
        .all()
    )
    sub_map: Dict[Tuple[int, datetime.date], FacultySubstitution] = {
        (s.timetable_entry_id, s.substitution_date): s for s in existing_subs
    }

    occurrences: List[ClassOccurrenceResponse] = []

    # Iterate over calendar dates
    curr = start_date
    while curr <= end_date:
        for entry in entries:
            slot = entry.slot
            if not slot or not day_matches_date(slot.day, curr):
                continue

            sub = sub_map.get((entry.id, curr))
            sub_fac_name = None
            sub_fac_id = None
            if sub and sub.substitute_faculty and sub.substitute_faculty.user:
                sub_fac_name = sub.substitute_faculty.user.name
                sub_fac_id = sub.substitute_faculty.id

            start_str = slot.start_time.strftime("%H:%M") if slot.start_time else None
            end_str = slot.end_time.strftime("%H:%M") if slot.end_time else None

            occurrences.append(
                ClassOccurrenceResponse(
                    timetable_entry_id=entry.id,
                    date=curr,
                    day=slot.day or curr.strftime("%A"),
                    start_time=start_str,
                    end_time=end_str,
                    course_id=entry.course_id,
                    course_code=entry.course.course_code if entry.course else None,
                    course_name=entry.course.course_name if entry.course else None,
                    room_number=entry.room.room_number if entry.room else None,
                    building_name=entry.room.building.name if (entry.room and entry.room.building) else None,
                    section_id=entry.section_id,
                    section_name=entry.section.section_name if entry.section else None,
                    batch_id=entry.batch_id,
                    batch_name=entry.batch.batch_name if entry.batch else None,
                    department_id=entry.department_id,
                    department_name=entry.department.name if entry.department else None,
                    has_active_request=sub is not None,
                    active_substitution_id=sub.id if sub else None,
                    active_substitution_status=sub.status if sub else None,
                    substitute_faculty_id=sub_fac_id,
                    substitute_faculty_name=sub_fac_name,
                )
            )
        curr += datetime.timedelta(days=1)

    # Sort occurrences chronologically
    occurrences.sort(key=lambda o: (o.date, o.start_time or "00:00"))
    return occurrences


# ---------------------------------------------------------------------------
# 2. Request Unavailability
# ---------------------------------------------------------------------------

def create_substitution_request(
    db: Session,
    current_user: User,
    timetable_entry_id: int,
    substitution_date: datetime.date,
    reason: str,
) -> FacultySubstitution:
    """
    Submits a faculty unavailability request for a specific class occurrence on a specific date.
    Strictly verifies ownership, published status, weekday match, and duplicate avoidance.
    """
    clean_reason = reason.strip()
    if len(clean_reason) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A substantive reason for unavailability is required (minimum 3 characters).",
        )

    # Verify TimetableEntry exists and is from a published version
    entry = (
        db.query(TimetableEntry)
        .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
        .options(
            joinedload(TimetableEntry.slot),
            joinedload(TimetableEntry.course),
            joinedload(TimetableEntry.department),
            joinedload(TimetableEntry.section),
            joinedload(TimetableEntry.room),
        )
        .filter(
            TimetableEntry.id == timetable_entry_id,
            TimetableVersion.status == "PUBLISHED",
            TimetableEntry.status != "CANCELLED",
        )
        .first()
    )
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published timetable entry not found or is inactive.",
        )

    # Verify authorization
    fac = (
        db.query(Faculty)
        .filter(Faculty.user_id == current_user.id)
        .first()
    )
    is_admin = current_user.role == "ADMIN"
    if not is_admin:
        if not fac or entry.faculty_id != fac.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only request substitution for classes assigned to your schedule.",
            )

    original_faculty_id = entry.faculty_id
    if not original_faculty_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Timetable entry does not have an assigned faculty member.",
        )

    # Verify date is not in the past
    if substitution_date < datetime.date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Substitution cannot be requested for past dates.",
        )

    # Verify weekday matches slot day
    if not entry.slot or not day_matches_date(entry.slot.day, substitution_date):
        expected_day = entry.slot.day if entry.slot else "Unknown"
        actual_day = substitution_date.strftime("%A")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The selected date ({substitution_date}, {actual_day}) does not match the scheduled class day ({expected_day}).",
        )

    # Duplicate check: Is there already an active request?
    existing = (
        db.query(FacultySubstitution)
        .filter(
            FacultySubstitution.timetable_entry_id == entry.id,
            FacultySubstitution.substitution_date == substitution_date,
            FacultySubstitution.status.in_(["REQUESTED", "PROPOSED", "APPROVED"]),
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An active substitution request (status: {existing.status}) already exists for this class on {substitution_date}.",
        )

    sub = FacultySubstitution(
        timetable_entry_id=entry.id,
        substitution_date=substitution_date,
        original_faculty_id=original_faculty_id,
        status="REQUESTED",
        reason=clean_reason,
        created_by_id=current_user.id,
        version=1,
    )
    db.add(sub)
    db.flush()

    # Audit log
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="SUBSTITUTION_REQUESTED",
            entity_type="FacultySubstitution",
            entity_id=sub.id,
            new_value={
                "timetable_entry_id": entry.id,
                "substitution_date": substitution_date.isoformat(),
                "original_faculty_id": original_faculty_id,
                "status": "REQUESTED",
            },
        )
    )

    # Notify Reviewers / Admins
    _notify_reviewers_new_request(db, sub, entry)

    db.commit()
    db.refresh(sub)
    return sub


# ---------------------------------------------------------------------------
# 3. Deterministic Candidate Ranking Engine
# ---------------------------------------------------------------------------

def find_and_rank_substitute_candidates(
    db: Session,
    substitution_id: int,
) -> CandidateRecommendationResponse:
    """
    Identifies and deterministically ranks available and qualified substitute faculty
    for a given substitution request.
    Evaluates:
      1. Qualification / Teaching Assignment (direct course assignment > department match > general)
      2. Timetable clash at slot on this day
      3. FacultyAvailability record
      4. Conflicting approved substitutions on this date
      5. Workload limit compliance (current weekly load + 1 <= max_weekly_load)
      6. Strict self-exclusion
    Fails closed with CANNOT_DETERMINE if essential timetable or curriculum references are missing.
    """
    sub = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.department),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
        )
        .filter(FacultySubstitution.id == substitution_id)
        .first()
    )
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Substitution request not found.",
        )

    entry = sub.timetable_entry
    if not entry or not entry.slot:
        return CandidateRecommendationResponse(
            substitution_id=sub.id,
            timetable_entry_id=sub.timetable_entry_id,
            substitution_date=sub.substitution_date,
            original_faculty_id=sub.original_faculty_id,
            original_faculty_name=sub.original_faculty.user.name if (sub.original_faculty and sub.original_faculty.user) else "Unknown",
            cannot_determine=True,
            cannot_determine_reason="Underlying timetable entry or time slot information is missing.",
            candidates=[],
        )

    target_slot_id = entry.slot_id
    target_slot = entry.slot
    target_course_id = entry.course_id
    target_dept_id = entry.department_id
    target_date = sub.substitution_date

    # Fetch all active faculty members excluding original faculty
    all_faculty = (
        db.query(Faculty)
        .options(
            joinedload(Faculty.user),
            joinedload(Faculty.department),
        )
        .filter(Faculty.id != sub.original_faculty_id)
        .all()
    )

    if not all_faculty:
        return CandidateRecommendationResponse(
            substitution_id=sub.id,
            timetable_entry_id=entry.id,
            substitution_date=target_date,
            course_code=entry.course.course_code if entry.course else None,
            course_name=entry.course.course_name if entry.course else None,
            slot_day=target_slot.day,
            slot_time=f"{target_slot.start_time.strftime('%H:%M')}-{target_slot.end_time.strftime('%H:%M')}" if (target_slot.start_time and target_slot.end_time) else None,
            original_faculty_id=sub.original_faculty_id,
            original_faculty_name=sub.original_faculty.user.name if (sub.original_faculty and sub.original_faculty.user) else "Unknown",
            cannot_determine=True,
            cannot_determine_reason="No other faculty profiles exist in the system to consider.",
            candidates=[],
        )

    # 1. Pre-fetch Course Assignments for target_course_id
    course_assignments = (
        db.query(CourseAssignment.faculty_id)
        .filter(CourseAssignment.course_id == target_course_id)
        .all()
    )
    direct_assignment_fac_ids: Set[int] = {ca[0] for ca in course_assignments if ca[0] is not None}

    # 2. Pre-fetch Timetable Entries clashing on target_slot_id in published timetables
    clashing_entries = (
        db.query(TimetableEntry.faculty_id)
        .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
        .filter(
            TimetableVersion.status == "PUBLISHED",
            TimetableEntry.slot_id == target_slot_id,
            TimetableEntry.status != "CANCELLED",
        )
        .all()
    )
    clashing_faculty_ids: Set[int] = {ce[0] for ce in clashing_entries if ce[0] is not None}

    # 3. Pre-fetch Faculty Availability records for target_slot_id
    avail_records = (
        db.query(FacultyAvailability)
        .filter(FacultyAvailability.slot_id == target_slot_id)
        .all()
    )
    availability_by_fac: Dict[int, FacultyAvailability] = {
        fa.faculty_id: fa for fa in avail_records if fa.faculty_id is not None
    }

    # 4. Pre-fetch other APPROVED substitutions on target_date
    conflicting_subs = (
        db.query(FacultySubstitution)
        .join(TimetableEntry, FacultySubstitution.timetable_entry_id == TimetableEntry.id)
        .filter(
            FacultySubstitution.substitution_date == target_date,
            FacultySubstitution.status == "APPROVED",
            TimetableEntry.slot_id == target_slot_id,
        )
        .all()
    )
    busy_as_substitute_ids: Set[int] = {
        cs.substitute_faculty_id for cs in conflicting_subs if cs.substitute_faculty_id is not None
    }
    unavailable_as_original_ids: Set[int] = {
        cs.original_faculty_id for cs in conflicting_subs if cs.original_faculty_id is not None
    }

    # 5. Pre-calculate weekly workload for all candidates
    # Count of published timetable entries per faculty
    workload_query = (
        db.query(TimetableEntry.faculty_id)
        .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
        .filter(
            TimetableVersion.status == "PUBLISHED",
            TimetableEntry.status != "CANCELLED",
        )
        .all()
    )
    workload_counts: Dict[int, int] = {}
    for w in workload_query:
        if w[0] is not None:
            workload_counts[w[0]] = workload_counts.get(w[0], 0) + 1

    candidate_recommendations: List[SubstituteCandidateRecommendation] = []

    for fac in all_faculty:
        fac_name = fac.user.name if fac.user else f"Faculty #{fac.id}"
        dept_name = fac.department.name if fac.department else None
        max_load = fac.max_weekly_load or 16
        current_load = workload_counts.get(fac.id, 0)
        load_pct = round((current_load / max_load) * 100.0, 1) if max_load > 0 else 100.0

        breakdown: List[CandidateEligibilityReason] = []
        ineligibility_reasons: List[str] = []

        # A. Qualification Check
        if fac.id in direct_assignment_fac_ids:
            tier = "DIRECT_ASSIGNMENT"
            qual_score = 100.0
            breakdown.append(
                CandidateEligibilityReason(
                    factor="QUALIFICATION",
                    status="PASS",
                    detail=f"Currently assigned to teach this course ({entry.course.course_code if entry.course else 'Course'}).",
                )
            )
        elif target_dept_id is not None and fac.department_id == target_dept_id:
            tier = "DEPARTMENT_MATCH"
            qual_score = 70.0
            breakdown.append(
                CandidateEligibilityReason(
                    factor="QUALIFICATION",
                    status="PASS",
                    detail=f"Member of the offering department ({dept_name or 'Department'}).",
                )
            )
        else:
            tier = "GENERAL"
            qual_score = 30.0
            breakdown.append(
                CandidateEligibilityReason(
                    factor="QUALIFICATION",
                    status="PASS",
                    detail="General faculty member (cross-departmental).",
                )
            )

        # B. Timetable Clash Check
        if fac.id in clashing_faculty_ids:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="TIMETABLE_CLASH",
                    status="FAIL",
                    detail="Scheduled to teach another class during this time slot in the master timetable.",
                )
            )
            ineligibility_reasons.append("Master timetable clash at this time slot")
        else:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="TIMETABLE_CLASH",
                    status="PASS",
                    detail="Free during this time slot in the master timetable.",
                )
            )

        # C. Faculty Availability Check
        fa_rec = availability_by_fac.get(fac.id)
        pref_score = 0.0
        if fa_rec:
            if fa_rec.availability == "UNAVAILABLE":
                breakdown.append(
                    CandidateEligibilityReason(
                        factor="AVAILABILITY",
                        status="FAIL",
                        detail="Marked as UNAVAILABLE in faculty availability preferences.",
                    )
                )
                ineligibility_reasons.append("Marked unavailable in preferences")
            elif fa_rec.availability == "PREFERRED":
                pref_score = 15.0
                breakdown.append(
                    CandidateEligibilityReason(
                        factor="AVAILABILITY",
                        status="PASS",
                        detail="Marked this time slot as PREFERRED.",
                    )
                )
            else:
                breakdown.append(
                    CandidateEligibilityReason(
                        factor="AVAILABILITY",
                        status="PASS",
                        detail="Available according to stated preferences.",
                    )
                )
        else:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="AVAILABILITY",
                    status="PASS",
                    detail="No negative availability constraints recorded.",
                )
            )

        # D. Existing Substitution Conflicts
        if fac.id in busy_as_substitute_ids:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="EXISTING_SUBSTITUTION",
                    status="FAIL",
                    detail=f"Already assigned to another substitution on {target_date} during this time slot.",
                )
            )
            ineligibility_reasons.append("Already assigned as substitute during this slot")
        elif fac.id in unavailable_as_original_ids:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="EXISTING_SUBSTITUTION",
                    status="FAIL",
                    detail=f"Has an approved absence/substitution for their own class on {target_date} during this time slot.",
                )
            )
            ineligibility_reasons.append("Has approved absence during this slot")
        else:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="EXISTING_SUBSTITUTION",
                    status="PASS",
                    detail="No existing substitution commitments on this date.",
                )
            )

        # E. Workload Limit Check
        if current_load + 1 > max_load:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="WORKLOAD_LIMIT",
                    status="FAIL",
                    detail=f"Adding this class ({current_load + 1} hrs) would exceed maximum load of {max_load} hrs/week.",
                )
            )
            ineligibility_reasons.append(f"Workload limit exceeded ({current_load + 1}/{max_load} hrs)")
        else:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="WORKLOAD_LIMIT",
                    status="PASS",
                    detail=f"Within workload limits ({current_load + 1}/{max_load} hrs).",
                )
            )

        is_eligible = len(ineligibility_reasons) == 0

        # Load balancing score: More available headroom gets higher score
        headroom = max(0, max_load - current_load)
        load_score = min(30.0, headroom * 5.0)

        total_score = qual_score + pref_score + load_score if is_eligible else 0.0

        candidate_recommendations.append(
            SubstituteCandidateRecommendation(
                faculty_id=fac.id,
                faculty_code=fac.faculty_id,
                faculty_name=fac_name,
                department_id=fac.department_id,
                department_name=dept_name,
                designation=fac.designation,
                qualification_tier=tier,
                current_weekly_load=current_load,
                max_weekly_load=max_load,
                load_percentage=load_pct,
                score=round(total_score, 2),
                is_eligible=is_eligible,
                ineligibility_reasons=ineligibility_reasons,
                eligibility_breakdown=breakdown,
            )
        )

    # Sort deterministically:
    # 1. is_eligible DESC (eligible candidates at the top)
    # 2. score DESC (highest qualification & availability score)
    # 3. current_weekly_load ASC (distribute load fairly)
    # 4. faculty_id ASC (stable tie-breaker)
    candidate_recommendations.sort(
        key=lambda c: (
            not c.is_eligible,
            -c.score,
            c.current_weekly_load,
            c.faculty_id,
        )
    )

    slot_time_str = None
    if target_slot.start_time and target_slot.end_time:
        slot_time_str = f"{target_slot.start_time.strftime('%H:%M')} - {target_slot.end_time.strftime('%H:%M')}"

    return CandidateRecommendationResponse(
        substitution_id=sub.id,
        timetable_entry_id=entry.id,
        substitution_date=target_date,
        course_code=entry.course.course_code if entry.course else None,
        course_name=entry.course.course_name if entry.course else None,
        slot_day=target_slot.day,
        slot_time=slot_time_str,
        original_faculty_id=sub.original_faculty_id,
        original_faculty_name=sub.original_faculty.user.name if (sub.original_faculty and sub.original_faculty.user) else "Unknown",
        cannot_determine=False,
        cannot_determine_reason=None,
        candidates=candidate_recommendations,
    )


# ---------------------------------------------------------------------------
# 4. Reviewer Approval Workflow
# ---------------------------------------------------------------------------

def approve_substitution_request(
    db: Session,
    reviewer_user: User,
    substitution_id: int,
    substitute_faculty_id: int,
    expected_version: int = 1,
) -> FacultySubstitution:
    """
    Approves a substitution request, assigning the chosen substitute faculty member.
    Verifies reviewer authority (ADMIN or SUBSTITUTION_COORDINATOR / SUBSTITUTION_REVIEWER),
    optimistic locking version, candidate eligibility, and dispatches multi-party notifications.
    Strictly preserves the canonical master timetable unchanged.
    """
    # Check reviewer authority
    is_admin = reviewer_user.role == "ADMIN"
    has_cap = (
        check_user_has_capability(db, reviewer_user, "SUBSTITUTION_COORDINATOR")
        or check_user_has_capability(db, reviewer_user, "SUBSTITUTION_REVIEWER")
    )
    if not (is_admin or has_cap):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You lack the required capability (SUBSTITUTION_COORDINATOR or SUBSTITUTION_REVIEWER) to approve substitutions.",
        )

    sub = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.slot),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.room).joinedload(Room.building),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.section),
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.batch),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
        )
        .filter(FacultySubstitution.id == substitution_id)
        .first()
    )
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Substitution request not found.",
        )

    # Optimistic locking check
    if sub.version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Concurrency conflict: Substitution request was modified by another reviewer (version {sub.version} != expected {expected_version}). Please refresh.",
        )

    if sub.status == "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Substitution request is already approved.",
        )

    if sub.status not in ("REQUESTED", "PROPOSED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve request with current status: {sub.status}.",
        )

    # Verify substitute faculty exists and is not original faculty
    if substitute_faculty_id == sub.original_faculty_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A faculty member cannot substitute for their own class.",
        )

    sub_fac = (
        db.query(Faculty)
        .options(joinedload(Faculty.user))
        .filter(Faculty.id == substitute_faculty_id)
        .first()
    )
    if not sub_fac:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Substitute faculty profile not found.",
        )

    entry = sub.timetable_entry
    if not entry or not entry.slot:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Associated timetable entry is missing or invalid.",
        )

    # Re-validate substitute candidate availability in transaction to prevent double-booking
    clash = (
        db.query(TimetableEntry)
        .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
        .filter(
            TimetableVersion.status == "PUBLISHED",
            TimetableEntry.faculty_id == substitute_faculty_id,
            TimetableEntry.slot_id == entry.slot_id,
            TimetableEntry.status != "CANCELLED",
        )
        .first()
    )
    if clash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Selected substitute faculty has a timetable clash in the master schedule at this time slot.",
        )

    conflicting_sub = (
        db.query(FacultySubstitution)
        .join(TimetableEntry, FacultySubstitution.timetable_entry_id == TimetableEntry.id)
        .filter(
            FacultySubstitution.substitution_date == sub.substitution_date,
            FacultySubstitution.status == "APPROVED",
            FacultySubstitution.substitute_faculty_id == substitute_faculty_id,
            TimetableEntry.slot_id == entry.slot_id,
        )
        .first()
    )
    if conflicting_sub:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Selected substitute faculty is already committed to another approved substitution at this time slot on this date.",
        )

    old_status = sub.status
    sub.substitute_faculty_id = substitute_faculty_id
    sub.status = "APPROVED"
    sub.reviewed_by_id = reviewer_user.id
    sub.reviewed_at = utc_now()
    sub.version += 1

    # Audit log
    db.add(
        AuditLog(
            user_id=reviewer_user.id,
            action="SUBSTITUTION_APPROVED",
            entity_type="FacultySubstitution",
            entity_id=sub.id,
            old_value={"status": old_status, "version": expected_version},
            new_value={
                "status": "APPROVED",
                "substitute_faculty_id": substitute_faculty_id,
                "reviewed_by_id": reviewer_user.id,
                "version": sub.version,
            },
        )
    )

    # Multi-party notifications
    _notify_parties_substitution_approved(db, sub, entry, sub_fac)

    db.commit()
    db.refresh(sub)
    return sub


# ---------------------------------------------------------------------------
# 5. Reviewer Rejection Workflow
# ---------------------------------------------------------------------------

def reject_substitution_request(
    db: Session,
    reviewer_user: User,
    substitution_id: int,
    rejection_reason: str,
    expected_version: int = 1,
) -> FacultySubstitution:
    """
    Rejects a substitution request.
    Verifies reviewer authority, optimistic locking version, records rejection reason,
    and notifies the requesting faculty.
    """
    clean_reason = (rejection_reason or "").strip()
    if len(clean_reason) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A substantive rejection reason is required (minimum 3 characters).",
        )

    is_admin = reviewer_user.role == "ADMIN"
    has_cap = (
        check_user_has_capability(db, reviewer_user, "SUBSTITUTION_COORDINATOR")
        or check_user_has_capability(db, reviewer_user, "SUBSTITUTION_REVIEWER")
    )
    if not (is_admin or has_cap):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You lack the required capability (SUBSTITUTION_COORDINATOR or SUBSTITUTION_REVIEWER) to reject substitutions.",
        )

    sub = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
        )
        .filter(FacultySubstitution.id == substitution_id)
        .first()
    )
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Substitution request not found.",
        )

    if sub.version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Concurrency conflict: Substitution request was modified by another reviewer (version {sub.version} != expected {expected_version}). Please refresh.",
        )

    if sub.status not in ("REQUESTED", "PROPOSED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject substitution request with current status: {sub.status}.",
        )

    old_status = sub.status
    sub.status = "REJECTED"
    sub.rejection_reason = clean_reason
    sub.reviewed_by_id = reviewer_user.id
    sub.reviewed_at = utc_now()
    sub.version += 1

    # Audit log
    db.add(
        AuditLog(
            user_id=reviewer_user.id,
            action="SUBSTITUTION_REJECTED",
            entity_type="FacultySubstitution",
            entity_id=sub.id,
            old_value={"status": old_status, "version": expected_version},
            new_value={
                "status": "REJECTED",
                "rejection_reason": clean_reason,
                "reviewed_by_id": reviewer_user.id,
                "version": sub.version,
            },
        )
    )

    # Notify requesting faculty
    if sub.original_faculty and sub.original_faculty.user_id:
        course_name = sub.timetable_entry.course.course_code if (sub.timetable_entry and sub.timetable_entry.course) else "Class"
        create_notification(
            db=db,
            user_id=sub.original_faculty.user_id,
            title="Substitution Request Rejected",
            message=f"Your substitution request for {course_name} on {sub.substitution_date} was rejected. Reason: {clean_reason}",
            type="SUBSTITUTION_REJECTED",
            link="/faculty/substitutions",
        )

    db.commit()
    db.refresh(sub)
    return sub


# ---------------------------------------------------------------------------
# 6. Cancellation Workflow
# ---------------------------------------------------------------------------

def cancel_substitution_request(
    db: Session,
    current_user: User,
    substitution_id: int,
) -> FacultySubstitution:
    """
    Cancels an existing substitution request.
    Can be performed by the requesting faculty member or an administrator.
    """
    sub = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.timetable_entry).joinedload(TimetableEntry.course),
            joinedload(FacultySubstitution.substitute_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
        )
        .filter(FacultySubstitution.id == substitution_id)
        .first()
    )
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Substitution request not found.",
        )

    fac = db.query(Faculty).filter(Faculty.user_id == current_user.id).first()
    is_owner = fac and fac.id == sub.original_faculty_id
    is_admin = current_user.role == "ADMIN"
    if not (is_owner or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only cancel your own substitution requests.",
        )

    if sub.status in ("REJECTED", "CANCELLED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Substitution is already {sub.status}.",
        )

    old_status = sub.status
    sub.status = "CANCELLED"
    sub.version += 1

    # Audit log
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="SUBSTITUTION_CANCELLED",
            entity_type="FacultySubstitution",
            entity_id=sub.id,
            old_value={"status": old_status},
            new_value={"status": "CANCELLED", "version": sub.version},
        )
    )

    # If it was approved, notify substitute faculty of cancellation
    if old_status == "APPROVED" and sub.substitute_faculty and sub.substitute_faculty.user_id:
        course_name = sub.timetable_entry.course.course_code if (sub.timetable_entry and sub.timetable_entry.course) else "Class"
        create_notification(
            db=db,
            user_id=sub.substitute_faculty.user_id,
            title="Substitution Assignment Cancelled",
            message=f"The substitution coverage for {course_name} on {sub.substitution_date} has been cancelled.",
            type="SUBSTITUTION_CANCELLED",
            link="/faculty/substitutions",
        )

    db.commit()
    db.refresh(sub)
    return sub


# ---------------------------------------------------------------------------
# 7. Multi-Party Targeted Notifications (with Privacy Barriers)
# ---------------------------------------------------------------------------

def _notify_reviewers_new_request(
    db: Session, sub: FacultySubstitution, entry: TimetableEntry
) -> None:
    """Notifies Admins and Reviewers that a new substitution request has arrived."""
    admin_users = db.query(User).filter(User.role == "ADMIN", User.is_active == True).all()  # noqa: E712
    coords = (
        db.query(CoordinatorCapability.user_id)
        .filter(
            CoordinatorCapability.capability.in_(["SUBSTITUTION_COORDINATOR", "SUBSTITUTION_REVIEWER"]),
            CoordinatorCapability.is_active == True,  # noqa: E712
        )
        .all()
    )
    coord_user_ids = {c[0] for c in coords}
    recipient_ids = {u.id for u in admin_users} | coord_user_ids

    course_code = entry.course.course_code if entry.course else "Class"
    slot_time = ""
    if entry.slot and entry.slot.start_time:
        slot_time = f" at {entry.slot.start_time.strftime('%H:%M')}"

    notifs = [
        Notification(
            user_id=uid,
            title=f"New Substitution Request: {course_code}",
            message=f"A substitution request has been submitted for {course_code} on {sub.substitution_date}{slot_time}.",
            type="SUBSTITUTION_REQUESTED",
            link="/admin/substitutions",
        )
        for uid in recipient_ids
    ]
    if notifs:
        create_bulk_notifications(db=db, notifications=notifs)


def _notify_parties_substitution_approved(
    db: Session,
    sub: FacultySubstitution,
    entry: TimetableEntry,
    substitute_faculty: Faculty,
) -> None:
    """
    Dispatches notifications upon approval:
      1. Original Faculty (confirmation of coverage)
      2. Substitute Faculty (assignment details)
      3. Affected Students (clear schedule update WITHOUT revealing faculty private reason)
    """
    sub_name = substitute_faculty.user.name if substitute_faculty.user else "Faculty"
    orig_name = sub.original_faculty.user.name if (sub.original_faculty and sub.original_faculty.user) else "Regular Faculty"
    course_code = entry.course.course_code if entry.course else "Course"
    course_name = entry.course.course_name if entry.course else ""
    room_name = entry.room.room_number if entry.room else "Assigned Room"
    time_str = ""
    if entry.slot and entry.slot.start_time:
        time_str = f" at {entry.slot.start_time.strftime('%H:%M')}"

    # 1. Original Faculty
    if sub.original_faculty and sub.original_faculty.user_id:
        create_notification(
            db=db,
            user_id=sub.original_faculty.user_id,
            title=f"Substitution Approved: {course_code}",
            message=f"{sub_name} has been assigned to cover your {course_code} class on {sub.substitution_date}{time_str}.",
            type="SUBSTITUTION_APPROVED",
            link="/faculty/substitutions",
        )

    # 2. Substitute Faculty
    if substitute_faculty.user_id:
        create_notification(
            db=db,
            user_id=substitute_faculty.user_id,
            title=f"Substitution Assignment: {course_code}",
            message=f"You have been assigned to cover {course_code} ({course_name}) on {sub.substitution_date}{time_str} in Room {room_name}.",
            type="SUBSTITUTION_ASSIGNED",
            link="/faculty/substitutions",
        )

    # 3. Affected Students (Enrolled in section and optional batch)
    # PRIVACY BARRIER: Under no circumstances is sub.reason included here!
    student_query = db.query(Student).filter(Student.section_id == entry.section_id)
    if entry.batch_id:
        student_query = student_query.filter(Student.batch_id == entry.batch_id)

    students = student_query.all()
    student_notifs = []
    for s in students:
        if s.user_id:
            student_notifs.append(
                Notification(
                    user_id=s.user_id,
                    title=f"Faculty Substitution: {course_code}",
                    message=f"Please note that {sub_name} will be conducting your {course_code} - {course_name} class on {sub.substitution_date}{time_str} in Room {room_name}.",
                    type="SUBSTITUTION_UPDATE",
                    link="/student/timetable",
                )
            )

    if student_notifs:
        create_bulk_notifications(db=db, notifications=student_notifs)


# ---------------------------------------------------------------------------
# 8. Date-Specific Substitution Lookups for Schedules
# ---------------------------------------------------------------------------

def get_active_substitutions_for_date(
    db: Session,
    date: datetime.date,
) -> Dict[int, FacultySubstitution]:
    """
    Returns a dictionary of timetable_entry_id -> FacultySubstitution for all APPROVED
    substitutions occurring on `date`.
    Used by student, faculty, and live-status views to non-destructively overlay date occurrences.
    """
    subs = (
        db.query(FacultySubstitution)
        .options(
            joinedload(FacultySubstitution.substitute_faculty).joinedload(Faculty.user),
            joinedload(FacultySubstitution.original_faculty).joinedload(Faculty.user),
        )
        .filter(
            FacultySubstitution.substitution_date == date,
            FacultySubstitution.status == "APPROVED",
        )
        .all()
    )
    return {s.timetable_entry_id: s for s in subs}


def format_substitution_response(
    sub: FacultySubstitution,
    current_user_role: str,
) -> FacultySubstitutionResponse:
    """
    Serializes a FacultySubstitution ORM object, enforcing privacy by masking
    the private unavailability reason for student users.
    """
    orig_name = sub.original_faculty.user.name if (sub.original_faculty and sub.original_faculty.user) else "Unknown"
    sub_name = (
        sub.substitute_faculty.user.name
        if (sub.substitute_faculty and sub.substitute_faculty.user)
        else None
    )
    rev_name = sub.reviewer.name if sub.reviewer else None

    entry = sub.timetable_entry
    course_code = entry.course.course_code if (entry and entry.course) else None
    course_name = entry.course.course_name if (entry and entry.course) else None
    room_num = entry.room.room_number if (entry and entry.room) else None
    bldg_name = entry.room.building.name if (entry and entry.room and entry.room.building) else None
    day_str = entry.slot.day if (entry and entry.slot) else None
    start_str = entry.slot.start_time.strftime("%H:%M") if (entry and entry.slot and entry.slot.start_time) else None
    end_str = entry.slot.end_time.strftime("%H:%M") if (entry and entry.slot and entry.slot.end_time) else None
    sec_name = entry.section.section_name if (entry and entry.section) else None
    bat_name = entry.batch.batch_name if (entry and entry.batch) else None
    dept_name = entry.department.name if (entry and entry.department) else None

    # Privacy filter: Students cannot see the personal unavailability reason
    reason_exposed = None if current_user_role == "STUDENT" else sub.reason

    return FacultySubstitutionResponse(
        id=sub.id,
        timetable_entry_id=sub.timetable_entry_id,
        substitution_date=sub.substitution_date,
        original_faculty_id=sub.original_faculty_id,
        original_faculty_name=orig_name,
        substitute_faculty_id=sub.substitute_faculty_id,
        substitute_faculty_name=sub_name,
        course_code=course_code,
        course_name=course_name,
        room_number=room_num,
        building_name=bldg_name,
        slot_day=day_str,
        start_time=start_str,
        end_time=end_str,
        section_name=sec_name,
        batch_name=bat_name,
        department_name=dept_name,
        status=sub.status,
        reason=reason_exposed,
        rejection_reason=sub.rejection_reason,
        created_by_id=sub.created_by_id,
        reviewed_by_id=sub.reviewed_by_id,
        reviewed_by_name=rev_name,
        reviewed_at=sub.reviewed_at,
        version=sub.version,
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )
