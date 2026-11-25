from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional
from datetime import datetime

class TimetableEntryUpdate(BaseModel):
    room_id: Optional[int] = None
    slot_id: Optional[int] = None
    faculty_id: Optional[int] = None

class TimetableEntryResponse(BaseModel):
    id: int
    timetable_id: Optional[int] = None
    version_id: Optional[int] = None
    department_id: Optional[int] = None
    program_id: Optional[int] = None
    semester_id: Optional[int] = None
    section_id: Optional[int] = None
    batch_id: Optional[int] = None
    course_id: Optional[int] = None
    faculty_id: Optional[int] = None
    room_id: Optional[int] = None
    slot_id: Optional[int] = None
    course_assignment_id: Optional[int] = None
    hour_type: Optional[str] = None
    block_group_id: Optional[str] = None
    status: str

    model_config = ConfigDict(from_attributes=True)

class TimetableEntryDetailResponse(TimetableEntryResponse):
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    course_type: Optional[str] = None
    faculty_name: Optional[str] = None
    faculty_designation: Optional[str] = None
    faculty_contact: Optional[str] = None
    room_number: Optional[str] = None
    building_name: Optional[str] = None
    day: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    slot_type: Optional[str] = None
    section_name: Optional[str] = None

class TimetableVersionResponse(BaseModel):
    id: int
    academic_year_id: Optional[int] = None
    version_number: Optional[str] = None
    status: Optional[str] = None
    created_by: Optional[int] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    approved_revision: Optional[int] = None
    created_at: datetime
    published_at: Optional[datetime] = None
    reason: Optional[str] = None
    revision: int = 1
    validated_revision: Optional[int] = None
    last_saved_at: Optional[datetime] = None
    last_saved_by: Optional[int] = None
    finalized_by: Optional[int] = None
    finalized_at: Optional[datetime] = None
    working_days: Optional[str] = "MON_SAT"
    score_summary: Optional[Dict[str, Any]] = None
    department_id: Optional[int] = None
    program_id: Optional[int] = None
    semester_id: Optional[int] = None
    department_name: Optional[str] = None
    program_name: Optional[str] = None
    academic_year_name: Optional[str] = None
    semester_number: Optional[int] = None
    created_by_name: Optional[str] = None
    approved_by_name: Optional[str] = None
    entry_count: int = 0
    section_names: List[str] = []

    model_config = ConfigDict(from_attributes=True)

class TimetableVersionDetailResponse(TimetableVersionResponse):
    department_name: Optional[str] = None
    program_name: Optional[str] = None
    academic_year_name: Optional[str] = None
    semester_number: Optional[int] = None
    section_name: Optional[str] = None
    class_teacher_name: Optional[str] = None
    class_teacher_designation: Optional[str] = None
    class_teacher_contact: Optional[str] = None
    created_by_name: Optional[str] = None
    total_sections: int = 0
    available_periods: int = 0
    timetable_entries: List[TimetableEntryDetailResponse] = []


class PersonalTimetableEntry(BaseModel):
    id: int
    version_id: Optional[int] = None
    version_number: Optional[str] = None
    academic_year_name: Optional[str] = None
    semester_number: Optional[int] = None
    department_name: Optional[str] = None
    program_name: Optional[str] = None
    section_name: Optional[str] = None
    batch_name: Optional[str] = None
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    course_type: Optional[str] = None
    faculty_name: Optional[str] = None
    faculty_designation: Optional[str] = None
    room_number: Optional[str] = None
    building_name: Optional[str] = None
    day: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    slot_type: Optional[str] = None
    status: str
    is_substituted: bool = False
    substitute_faculty_id: Optional[int] = None
    substitute_faculty_name: Optional[str] = None
    original_faculty_name: Optional[str] = None
    substitution_id: Optional[int] = None
    substitution_status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class FacultyTimetableResponse(BaseModel):
    faculty_id: Optional[int] = None
    faculty_code: Optional[str] = None
    faculty_name: Optional[str] = None
    designation: Optional[str] = None
    department_name: Optional[str] = None
    total_teaching_hours: int = 0
    working_days: Optional[str] = "MON_SAT"
    sections_as_class_teacher: List[str] = []
    entries: List[PersonalTimetableEntry] = []

    model_config = ConfigDict(from_attributes=True)


class StudentTimetableResponse(BaseModel):
    student_id: Optional[int] = None
    student_code: Optional[str] = None
    student_name: Optional[str] = None
    department_name: Optional[str] = None
    program_name: Optional[str] = None
    semester_number: Optional[int] = None
    section_name: Optional[str] = None
    batch_name: Optional[str] = None
    academic_year_name: Optional[str] = None
    admission_batch: Optional[str] = None
    class_teacher_name: Optional[str] = None
    class_teacher_designation: Optional[str] = None
    class_teacher_contact: Optional[str] = None
    total_class_hours: int = 0
    working_days: Optional[str] = "MON_SAT"
    entries: List[PersonalTimetableEntry] = []

    model_config = ConfigDict(from_attributes=True)


class DepartmentTimetableResponse(BaseModel):
    department_id: int
    department_name: str
    department_code: str
    total_entries: int
    entries: List[PersonalTimetableEntry] = []

    model_config = ConfigDict(from_attributes=True)


# ── Canonical Timetable Schemas (Single Timetable per AY + Sem + Section) ──

class CanonicalTimetableResponse(BaseModel):
    id: int
    academic_year_id: int
    semester_id: int
    section_id: int
    academic_year_name: Optional[str] = None
    semester_number: Optional[int] = None
    section_name: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    program_name: Optional[str] = None
    status: str = "PUBLISHED"
    working_days: str = "MON_SAT"
    created_at: datetime
    published_at: Optional[datetime] = None
    class_teacher_name: Optional[str] = None
    class_teacher_designation: Optional[str] = None
    class_teacher_contact: Optional[str] = None
    entries: List[TimetableEntryDetailResponse] = []

    model_config = ConfigDict(from_attributes=True)


class TimetablePreviewEntry(BaseModel):
    section_id: int
    section_name: str
    course_assignment_id: int
    course_id: int
    course_code: str
    course_name: str
    course_type: str = "CORE"
    faculty_id: int
    faculty_name: str
    faculty_designation: Optional[str] = None
    faculty_contact: Optional[str] = None
    room_id: int
    room_number: str
    building_name: Optional[str] = None
    slot_id: int
    day: str
    start_time: str
    end_time: str
    slot_type: str = "CLASS"
    hour_type: str = "THEORY"


class TimetablePreviewResponse(BaseModel):
    academic_year_id: int
    semester_id: int
    department_id: int
    academic_year_name: str
    semester_number: int
    department_name: str
    status: str
    is_valid: bool
    can_publish: bool
    blocker_count: int = 0
    warning_count: int = 0
    violations: List[dict] = []
    sections: List[dict] = []
    entries: List[TimetablePreviewEntry] = []
    solve_time_seconds: float = 0.0
    score: Optional[dict] = None
    existing_published: bool = False
    working_days: str = "MON_SAT"


class PublishTimetableRequest(BaseModel):
    academic_year_id: int
    semester_id: int
    department_id: int
    working_days: Optional[str] = "MON_SAT"
    entries: List[TimetablePreviewEntry]


class PublishTimetableResponse(BaseModel):
    success: bool
    message: str
    published_timetables: List[CanonicalTimetableResponse] = []
    total_entries_published: int = 0


class CoordinatorRecipientItem(BaseModel):
    id: int
    user_id: Optional[int] = None
    name: str
    email: Optional[str] = None
    role_or_designation: str
    scope_type: str
    scope_description: str
    department_name: Optional[str] = None
    section_name: Optional[str] = None


class PublishPreflightResponse(BaseModel):
    version_id: int
    academic_year_id: Optional[int] = None
    academic_year_name: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    semester_id: Optional[int] = None
    semester_number: Optional[int] = None
    section_names: List[str] = []
    status: str
    revision: int
    approved_revision: Optional[int] = None
    can_publish: bool
    coordinators: List[CoordinatorRecipientItem] = []
    coordinator_count: int = 0
    blocking_reasons: List[str] = []


class TimetableVersionsSummaryResponse(BaseModel):
    total_generated: int = 0
    awaiting_review: int = 0
    approved: int = 0
    published: int = 0
    archived: int = 0


# ── Smart Timetable Editor & Arrangement Schemas ──────────────────────────

class AlternativeRoomOption(BaseModel):
    room_id: int
    room_number: str
    building_name: Optional[str] = None
    capacity: Optional[int] = None
    room_type: Optional[str] = None


class MoveOptionSlot(BaseModel):
    slot_id: int
    day: str
    start_time: str
    end_time: str
    slot_type: str
    can_move: bool
    blocked_reason: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    alternative_rooms: List[AlternativeRoomOption] = Field(default_factory=list)


class MoveOptionsResponse(BaseModel):
    version_id: int
    entry_id: int
    block_entry_ids: List[int] = Field(default_factory=list)
    revision: int
    options: List[MoveOptionSlot] = Field(default_factory=list)


class ProposedMoveItem(BaseModel):
    entry_id: int
    target_slot_id: int
    target_room_id: Optional[int] = None
    target_faculty_id: Optional[int] = None


class ArrangementValidateRequest(BaseModel):
    expected_revision: Optional[int] = None
    moves: List[ProposedMoveItem] = Field(..., min_length=1)


class MoveOutcomeItem(BaseModel):
    entry_id: int
    target_slot_id: int
    valid: bool
    reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    affected_entry_ids: List[int] = Field(default_factory=list)


class ArrangementValidateResponse(BaseModel):
    valid: bool
    can_save: bool
    current_revision: int
    outcomes: List[MoveOutcomeItem] = Field(default_factory=list)
    conflicts: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ArrangementSaveRequest(BaseModel):
    expected_revision: int
    moves: List[ProposedMoveItem] = Field(..., min_length=1)
    reason: Optional[str] = None


class ArrangementSaveResponse(BaseModel):
    success: bool
    version_id: int
    revision: int
    status: str
    last_saved_at: datetime
    saved_count: int
    version_detail: TimetableVersionDetailResponse


class TimetableChangeHistoryItem(BaseModel):
    id: int
    version_id: int
    revision: int
    entry_id: Optional[int] = None
    admin_id: int
    admin_name: Optional[str] = None
    previous_slot_id: Optional[int] = None
    new_slot_id: Optional[int] = None
    previous_room_id: Optional[int] = None
    new_room_id: Optional[int] = None
    previous_faculty_id: Optional[int] = None
    new_faculty_id: Optional[int] = None
    previous_day: Optional[str] = None
    new_day: Optional[str] = None
    validation_outcome: str
    reason: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
