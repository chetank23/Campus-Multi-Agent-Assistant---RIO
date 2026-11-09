"""
backend/schemas/settings.py
---------------------------
Pydantic schemas for Admin Settings & Safe Operational Data Management.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── General Settings ─────────────────────────────────────────────────────────

class InstitutionProfile(BaseModel):
    institution_name: str = "REVA University"
    campus_name: str = "Rukmini Knowledge Park, Kattigenahalli, Yelahanka, Bengaluru"
    department: str = "School of Computer Science & Engineering (AI & DS)"
    timezone: str = "Asia/Kolkata"
    academic_year: str = "2024-25"
    current_semester: str = "Semester 7"


class NotificationPreferences(BaseModel):
    email_alerts_enabled: bool = True
    timetable_publish_alerts: bool = True
    substitution_alerts: bool = True
    resource_booking_alerts: bool = True


class GeneralSettingsResponse(BaseModel):
    institution: InstitutionProfile
    notifications: NotificationPreferences
    updated_at: Optional[str] = None


class GeneralSettingsUpdate(BaseModel):
    institution: Optional[InstitutionProfile] = None
    notifications: Optional[NotificationPreferences] = None


# ── Timetable Settings ───────────────────────────────────────────────────────

class BreakPeriod(BaseModel):
    name: str
    start: str
    end: str


class TimetableSettingsResponse(BaseModel):
    working_days: str = "MON_SAT"  # MON_SAT | MON_FRI
    periods_per_day: int = 7
    period_duration_minutes: int = 55
    break_times: List[BreakPeriod] = Field(default_factory=list)
    max_consecutive_faculty_lectures: int = 3
    enable_soft_lab_preference: bool = True
    updated_at: Optional[str] = None


class TimetableSettingsUpdate(BaseModel):
    working_days: Optional[str] = None
    max_consecutive_faculty_lectures: Optional[int] = None
    enable_soft_lab_preference: Optional[bool] = None


# ── User & Access Settings ───────────────────────────────────────────────────

class UserAccessSummary(BaseModel):
    total_users: int
    super_admin_count: int
    admin_count: int
    faculty_count: int
    student_count: int
    access_token_expiry_minutes: int = 20
    refresh_token_expiry_days: int = 7
    mfa_enforced: bool = False


# ── System & Integration Status ──────────────────────────────────────────────

class SystemIntegrationStatus(BaseModel):
    database_status: str = "CONNECTED"
    database_host: str
    database_name: str
    database_schema: str
    database_port: int
    ai_agent_status: str = "READY"
    llm_provider: str
    llm_configured: bool
    supabase_configured: bool
    server_time: str
    uptime_status: str = "HEALTHY"


# ── Data Management (Safe Operational Reset) ──────────────────────────────────

class TableRecordCount(BaseModel):
    table_name: str
    display_name: str
    count: int
    description: str


class DataCategorySummary(BaseModel):
    category_id: str  # 'timetable', 'resources', 'faculty_ops', 'other_ops', 'notifications'
    category_name: str
    description: str
    total_records: int
    can_clear: bool = True
    warning: Optional[str] = None
    tables: List[TableRecordCount]


class DataManagementSummaryResponse(BaseModel):
    categories: List[DataCategorySummary]
    total_generated_records: int
    master_records_protected: bool = True
    authoritative_dataset: str = "RIO_MJP_AIDS_A_Clean_Test_Data_No_Attendance.xlsx"


class DataClearPreviewRequest(BaseModel):
    categories: List[str]  # list of category_ids, e.g. ['timetable', 'resources']
    clear_all: bool = False


class AffectedTableDetail(BaseModel):
    table_name: str
    display_name: str
    record_count: int
    foreign_key_dependencies: List[str]


class DataClearPreviewResponse(BaseModel):
    categories_selected: List[str]
    clear_all: bool
    affected_tables: List[AffectedTableDetail]
    total_records_to_delete: int
    warnings: List[str]
    master_records_protected: bool = True
    safe_to_execute: bool = True


class DataClearExecuteRequest(BaseModel):
    categories: List[str]
    clear_all: bool = False
    confirmation: bool = False  # Must be explicitly True


class DataClearExecuteResponse(BaseModel):
    success: bool
    categories_cleared: List[str]
    total_records_deleted: int
    deleted_per_table: Dict[str, int]
    audit_log_id: int
    message: str


# ── Comprehensive Settings Overview ──────────────────────────────────────────

class FullSettingsResponse(BaseModel):
    general: GeneralSettingsResponse
    timetable: TimetableSettingsResponse
    access: UserAccessSummary
    system: SystemIntegrationStatus

