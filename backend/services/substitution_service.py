"""
backend/services/substitution_service.py
----------------------------------------
Business logic for Faculty Substitution:
1. Faculty occurrence querying (inspecting upcoming scheduled classes).
2. Unavailability request lifecycle (creation, duplicate prevention, ownership validation).
3. Deterministic candidate ranking engine:
   - Mandatory Hard Qualification (verified CourseAssignment or active published TimetableEntry)
   - Timetable clash detection at slot in master timetable
   - Availability check (FacultyAvailability preferences)
   - Existing approved substitution conflicts
   - Accurate weekly workload limit bounds (current weekly hours + 1 <= max_weekly_load)
   - Strict self-exclusion
   - Deterministic ranking & transparent ELIGIBLE / NO_ELIGIBLE_CANDIDATE / CANNOT_DETERMINE semantics
4. Reviewer workflow (approve / reject with optimistic locking, scoped capabilities, and candidate validation).
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
# 3. Reviewer Scoped Authority & Candidate Recommendation Engine
# ---------------------------------------------------------------------------

def check_reviewer_authority(
    db: Session,
    reviewer_user: User,
    department_id: Optional[int] = None,
) -> bool:
    """
    Validates whether the reviewer holds active capability to review/approve/reject
    substitutions, strictly honoring department scoping.
    - Administrators automatically satisfy administrative capabilities across all departments.
    - Non-administrators must possess an active, non-expired SUBSTITUTION_COORDINATOR or
      SUBSTITUTION_REVIEWER capability.
    - If the capability is DEPARTMENT-scoped, department_id must match scope_id.
    """
    if reviewer_user.role == "ADMIN":
        return True

    now = utc_now()
    caps = (
        db.query(CoordinatorCapability)
        .filter(
            CoordinatorCapability.user_id == reviewer_user.id,
            CoordinatorCapability.capability.in_(["SUBSTITUTION_COORDINATOR", "SUBSTITUTION_REVIEWER"]),
            CoordinatorCapability.is_active == True,  # noqa: E712
            or_(
                CoordinatorCapability.starts_at.is_(None),
                CoordinatorCapability.starts_at <= now,
            ),
            or_(
                CoordinatorCapability.expires_at.is_(None),
                CoordinatorCapability.expires_at > now,
            ),
        )
        .all()
    )
    if not caps:
        return False

    for c in caps:
        if c.scope_type == "GLOBAL":
            return True
        if c.scope_type == "DEPARTMENT":
            if department_id is not None and c.scope_id == department_id:
                return True

    return False


def find_and_rank_substitute_candidates(
    db: Session,
    substitution_id: int,
) -> CandidateRecommendationResponse:
    """
    Identifies and deterministically ranks available and qualified substitute faculty
    for a given substitution request.
    Evaluates:
      1. Mandatory Hard Qualification (verified CourseAssignment or active published TimetableEntry)
      2. Active User Account (non-revoked, is_active == True)
      3. Timetable clash at slot on this day in master schedule
      4. Explicit FacultyAvailability constraints (UNAVAILABLE excludes candidate)
      5. Conflicting approved substitutions on this date
      6. Weekly workload limit compliance in the target week (current + 1 <= max_weekly_load)
      7. Strict self-exclusion
    Fails closed with CANNOT_DETERMINE if essential timetable, curriculum, or qualification records are missing.
    Distinguishes ELIGIBLE, NO_ELIGIBLE_CANDIDATE, and CANNOT_DETERMINE semantics.
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
            evaluation_status="CANNOT_DETERMINE",
            cannot_determine=True,
            cannot_determine_reason="Underlying timetable entry or time slot information is missing.",
            candidates=[],
        )

    target_slot_id = entry.slot_id
    target_slot = entry.slot
    target_course_id = entry.course_id
    target_dept_id = entry.department_id
    target_date = sub.substitution_date

    if target_course_id is None:
        return CandidateRecommendationResponse(
            substitution_id=sub.id,
            timetable_entry_id=entry.id,
            substitution_date=target_date,
            original_faculty_id=sub.original_faculty_id,
            original_faculty_name=sub.original_faculty.user.name if (sub.original_faculty and sub.original_faculty.user) else "Unknown",
            evaluation_status="CANNOT_DETERMINE",
            cannot_determine=True,
            cannot_determine_reason="Class occurrence has no associated course reference.",
            candidates=[],
        )

    # 1. Fetch trusted evidence of qualification for target_course_id
    # Source A: Course assignments for target_course_id
    course_assignments = (
        db.query(CourseAssignment.faculty_id)
        .filter(CourseAssignment.course_id == target_course_id)
        .all()
    )
    ca_fac_ids: Set[int] = {ca[0] for ca in course_assignments if ca[0] is not None}

    # Source B: Active published timetable entries teaching this course
    teaching_assignments = (
        db.query(TimetableEntry.faculty_id)
        .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
        .filter(
            TimetableVersion.status == "PUBLISHED",
            TimetableEntry.course_id == target_course_id,
            TimetableEntry.status != "CANCELLED",
        )
        .all()
    )
    te_fac_ids: Set[int] = {te[0] for te in teaching_assignments if te[0] is not None}
    qualified_faculty_ids: Set[int] = ca_fac_ids | te_fac_ids

    # Fail closed with CANNOT_DETERMINE if no trusted qualification records exist anywhere for this course
    # Fail closed with CANNOT_DETERMINE if no trusted curriculum qualification records exist
    if not ca_fac_ids and not (te_fac_ids - {sub.original_faculty_id}):
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
            evaluation_status="CANNOT_DETERMINE",
            cannot_determine=True,
            cannot_determine_reason=f"No trusted faculty qualification or course assignment records exist for {entry.course.course_code if entry.course else 'this course'} in the database.",
            candidates=[],
        )

    # Fetch all faculty members excluding original faculty
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
            evaluation_status="CANNOT_DETERMINE",
            cannot_determine=True,
            cannot_determine_reason="No other faculty profiles exist in the system to consider.",
            candidates=[],
        )

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

    # 5. Pre-calculate weekly workload for all candidates in the specific week of target_date
    start_of_week = target_date - datetime.timedelta(days=target_date.weekday())
    end_of_week = start_of_week + datetime.timedelta(days=6)

    # Base recurring classes in published timetable
    base_workload_query = (
        db.query(TimetableEntry.faculty_id)
        .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
        .filter(
            TimetableVersion.status == "PUBLISHED",
            TimetableEntry.status != "CANCELLED",
        )
        .all()
    )
    base_workload_counts: Dict[int, int] = {}
    for w in base_workload_query:
        if w[0] is not None:
            base_workload_counts[w[0]] = base_workload_counts.get(w[0], 0) + 1

    # Approved absences during that week
    week_absences = (
        db.query(FacultySubstitution.original_faculty_id)
        .filter(
            FacultySubstitution.status == "APPROVED",
            FacultySubstitution.substitution_date >= start_of_week,
            FacultySubstitution.substitution_date <= end_of_week,
        )
        .all()
    )
    week_absences_counts: Dict[int, int] = {}
    for a in week_absences:
        if a[0] is not None:
            week_absences_counts[a[0]] = week_absences_counts.get(a[0], 0) + 1

    # Approved substitution duties during that week
    week_coverages = (
        db.query(FacultySubstitution.substitute_faculty_id)
        .filter(
            FacultySubstitution.status == "APPROVED",
            FacultySubstitution.substitution_date >= start_of_week,
            FacultySubstitution.substitution_date <= end_of_week,
        )
        .all()
    )
    week_coverages_counts: Dict[int, int] = {}
    for c in week_coverages:
        if c[0] is not None:
            week_coverages_counts[c[0]] = week_coverages_counts.get(c[0], 0) + 1

    candidate_recommendations: List[SubstituteCandidateRecommendation] = []

    for fac in all_faculty:
        fac_name = fac.user.name if fac.user else f"Faculty #{fac.id}"
        dept_name = fac.department.name if fac.department else None
        max_load = fac.max_weekly_load or 16

        base_load = base_workload_counts.get(fac.id, 0)
        absences = week_absences_counts.get(fac.id, 0)
        coverages = week_coverages_counts.get(fac.id, 0)
        effective_load = max(0, base_load - absences + coverages)
        load_pct = round((effective_load / max_load) * 100.0, 1) if max_load > 0 else 100.0

        breakdown: List[CandidateEligibilityReason] = []
        ineligibility_reasons: List[str] = []

        # 0. Active User Account Check
        if not fac.user or not fac.user.is_active:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="ACTIVE_STATUS",
                    status="FAIL",
                    detail="Faculty user account is inactive or revoked.",
                )
            )
            ineligibility_reasons.append("Inactive or revoked user account")
        else:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="ACTIVE_STATUS",
                    status="PASS",
                    detail="Faculty user account is active.",
                )
            )

        # A. Hard Qualification Gate
        # Every proposed substitute must have trusted evidence of qualification or authorized teaching assignment
        # A faculty member from the same department must NOT automatically qualify!
        is_qualified = fac.id in qualified_faculty_ids
        if not is_qualified:
            tier = "UNQUALIFIED"
            qual_score = 0.0
            breakdown.append(
                CandidateEligibilityReason(
                    factor="QUALIFICATION",
                    status="FAIL",
                    detail=f"Not qualified to teach {entry.course.course_code if entry.course else 'this course'}: no verified course assignment or published teaching record exists for this faculty.",
                )
            )
            ineligibility_reasons.append(f"Lacks verified qualification/assignment for course {entry.course.course_code if entry.course else ''}".strip())
        else:
            tier = "VERIFIED_QUALIFICATION"
            qual_score = 100.0
            breakdown.append(
                CandidateEligibilityReason(
                    factor="QUALIFICATION",
                    status="PASS",
                    detail=f"Holds verified teaching assignment/qualification for {entry.course.course_code if entry.course else 'this course'}.",
                )
            )

        # Department Affinity (Ranking bonus only after qualification passes)
        dept_bonus = 0.0
        if is_qualified and target_dept_id is not None and fac.department_id == target_dept_id:
            dept_bonus = 30.0

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
                    detail="Available (no negative availability constraints recorded).",
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
            ineligibility_reasons.append("Already assigned as substitute during this slot on this date")
        elif fac.id in unavailable_as_original_ids:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="EXISTING_SUBSTITUTION",
                    status="FAIL",
                    detail=f"Has an approved absence/substitution for their own class on {target_date} during this time slot.",
                )
            )
            ineligibility_reasons.append("Has approved absence during this slot on this date")
        else:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="EXISTING_SUBSTITUTION",
                    status="PASS",
                    detail="No existing substitution commitments on this date.",
                )
            )

        # E. Workload Limit Check
        if effective_load + 1 > max_load:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="WORKLOAD_LIMIT",
                    status="FAIL",
                    detail=f"Adding this class ({effective_load + 1} hrs) would exceed maximum load of {max_load} hrs/week.",
                )
            )
            ineligibility_reasons.append(f"Workload limit exceeded ({effective_load + 1}/{max_load} hrs)")
        else:
            breakdown.append(
                CandidateEligibilityReason(
                    factor="WORKLOAD_LIMIT",
                    status="PASS",
                    detail=f"Within workload limits ({effective_load + 1}/{max_load} hrs).",
                )
            )

        is_eligible = len(ineligibility_reasons) == 0

        # Load balancing score: More available headroom gets higher score (up to 20 pts)
        load_score = max(0.0, min(20.0, 20.0 * (1.0 - (effective_load / max_load)))) if max_load > 0 else 0.0

        total_score = qual_score + dept_bonus + pref_score + load_score if is_eligible else 0.0

        candidate_recommendations.append(
            SubstituteCandidateRecommendation(
                faculty_id=fac.id,
                faculty_code=fac.faculty_id,
                faculty_name=fac_name,
                department_id=fac.department_id,
                department_name=dept_name,
                designation=fac.designation,
                qualification_tier=tier,
                current_weekly_load=effective_load,
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

    has_eligible = any(c.is_eligible for c in candidate_recommendations)
    if has_eligible:
        eval_status = "ELIGIBLE"
        cannot_det = False
        cannot_det_reason = None
    else:
        eval_status = "NO_ELIGIBLE_CANDIDATE"
        cannot_det = False
        cannot_det_reason = "Evaluation completed: no candidates satisfy all mandatory eligibility criteria (qualification, slot availability, and workload limits)."

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
        evaluation_status=eval_status,
        cannot_determine=cannot_det,
        cannot_determine_reason=cannot_det_reason,
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
    Verifies reviewer authority (ADMIN or scoped SUBSTITUTION_COORDINATOR / SUBSTITUTION_REVIEWER),
    optimistic locking version, candidate eligibility, and dispatches multi-party notifications.
    Strictly preserves the canonical master timetable unchanged.
    """
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

    entry = sub.timetable_entry
    if not entry or not entry.slot:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Associated timetable entry is missing or invalid.",
        )

    # Check reviewer authority with department scoping
    dept_id = entry.department_id
    if not check_reviewer_authority(db, reviewer_user, dept_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You lack the required capability (SUBSTITUTION_COORDINATOR or SUBSTITUTION_REVIEWER) for this department to approve substitutions.",
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

    # Check active user account
    if not sub_fac.user or not sub_fac.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected substitute faculty account is inactive or revoked.",
        )

    # HARD QUALIFICATION CHECK AT APPROVAL TIME
    target_course_id = entry.course_id
    has_ca = (
        db.query(CourseAssignment)
        .filter(CourseAssignment.course_id == target_course_id, CourseAssignment.faculty_id == substitute_faculty_id)
        .first()
    )
    has_te = (
        db.query(TimetableEntry)
        .join(TimetableVersion, TimetableEntry.version_id == TimetableVersion.id)
        .filter(
            TimetableVersion.status == "PUBLISHED",
            TimetableEntry.course_id == target_course_id,
            TimetableEntry.faculty_id == substitute_faculty_id,
            TimetableEntry.status != "CANCELLED",
        )
        .first()
    )
    if not (has_ca or has_te):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Selected faculty ({sub_fac.user.name if sub_fac.user else 'Faculty'}) does not hold verified qualification/assignment for course {entry.course.course_code if entry.course else ''}.",
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

    sub = (
        db.query(FacultySubstitution)
        .options(
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
    dept_id = entry.department_id if entry else None
    if not check_reviewer_authority(db, reviewer_user, dept_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You lack the required capability (SUBSTITUTION_COORDINATOR or SUBSTITUTION_REVIEWER) for this department to reject substitutions.",
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
