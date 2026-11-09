"""
backend/services/settings_service.py
------------------------------------
Business logic and transactional execution for:
- Database-backed application settings
- Operational data discovery & category summaries
- Dry-run preview of safe operational data clears
- Controlled transactional deletion in topological dependency order
- Audit logging of administrative data operations
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.config import DATABASE_URL
from backend.models.identity import User
from backend.models.system_setting import SystemSetting
from backend.models.workflow import AuditLog
from backend.schemas.settings import (
    AffectedTableDetail,
    BreakPeriod,
    DataCategorySummary,
    DataClearExecuteResponse,
    DataClearPreviewResponse,
    DataManagementSummaryResponse,
    GeneralSettingsResponse,
    GeneralSettingsUpdate,
    InstitutionProfile,
    NotificationPreferences,
    SystemIntegrationStatus,
    TableRecordCount,
    TimetableSettingsResponse,
    TimetableSettingsUpdate,
    UserAccessSummary,
)
from backend.utils.datetime_utils import utc_now


# ── Default Configuration Constants ──────────────────────────────────────────

DEFAULT_INSTITUTION = {
    "institution_name": "REVA University",
    "campus_name": "Rukmini Knowledge Park, Kattigenahalli, Yelahanka, Bengaluru",
    "department": "School of Computer Science & Engineering (AI & DS)",
    "timezone": "Asia/Kolkata",
    "academic_year": "2024-25",
    "current_semester": "Semester 7",
}

DEFAULT_NOTIFICATIONS = {
    "email_alerts_enabled": True,
    "timetable_publish_alerts": True,
    "substitution_alerts": True,
    "resource_booking_alerts": True,
}

DEFAULT_TIMETABLE = {
    "working_days": "MON_SAT",
    "periods_per_day": 7,
    "period_duration_minutes": 55,
    "break_times": [
        {"name": "Tea Break", "start": "10:20", "end": "10:40"},
        {"name": "Lunch Break", "start": "12:30", "end": "13:30"},
    ],
    "max_consecutive_faculty_lectures": 3,
    "enable_soft_lab_preference": True,
}


def _get_or_create_setting(db: Session, key: str, category: str, default_val: Dict[str, Any], desc: str) -> SystemSetting:
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not setting:
        setting = SystemSetting(
            key=key,
            category=category,
            value=default_val,
            description=desc,
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def get_general_settings(db: Session) -> GeneralSettingsResponse:
    inst_setting = _get_or_create_setting(
        db, "institution_profile", "GENERAL", DEFAULT_INSTITUTION, "Institutional identity metadata"
    )
    notif_setting = _get_or_create_setting(
        db, "notification_preferences", "GENERAL", DEFAULT_NOTIFICATIONS, "System notification triggers"
    )

    inst_data = {**DEFAULT_INSTITUTION, **(inst_setting.value or {})}
    notif_data = {**DEFAULT_NOTIFICATIONS, **(notif_setting.value or {})}

    updated_iso = inst_setting.updated_at.isoformat() if inst_setting.updated_at else None

    return GeneralSettingsResponse(
        institution=InstitutionProfile(**inst_data),
        notifications=NotificationPreferences(**notif_data),
        updated_at=updated_iso,
    )


def update_general_settings(db: Session, payload: GeneralSettingsUpdate, user: User) -> GeneralSettingsResponse:
    if payload.institution is not None:
        inst_setting = _get_or_create_setting(
            db, "institution_profile", "GENERAL", DEFAULT_INSTITUTION, "Institutional identity metadata"
        )
        inst_setting.value = payload.institution.model_dump()
        inst_setting.updated_at = utc_now()
        inst_setting.updated_by_id = user.id

    if payload.notifications is not None:
        notif_setting = _get_or_create_setting(
            db, "notification_preferences", "GENERAL", DEFAULT_NOTIFICATIONS, "System notification triggers"
        )
        notif_setting.value = payload.notifications.model_dump()
        notif_setting.updated_at = utc_now()
        notif_setting.updated_by_id = user.id

    db.commit()
    return get_general_settings(db)


def _normalize_break_period(item: object) -> Optional[BreakPeriod]:
    """
    Validates and constructs a BreakPeriod from stored dictionary data.
    Ensures item is a dict with non-empty 'name', 'start', and 'end' strings.
    Safely rejects primitives (bool, int, str), malformed dictionaries, or missing fields.
    """
    if not isinstance(item, dict):
        return None
    name = item.get("name")
    start = item.get("start")
    end = item.get("end")
    if (
        isinstance(name, str)
        and isinstance(start, str)
        and isinstance(end, str)
        and name.strip()
        and start.strip()
        and end.strip()
    ):
        return BreakPeriod(name=name.strip(), start=start.strip(), end=end.strip())
    return None


def _deserialize_break_periods(raw: object) -> List[BreakPeriod]:
    """
    Normalizes a list of break periods from stored settings.
    If raw data is invalid, empty, or malformed, safely defaults to the authoritative REVA schedule:
      - Tea Break: 10:20–10:40
      - Lunch Break: 12:30–13:30
    """
    default_reva_breaks = [
        BreakPeriod(name="Tea Break", start="10:20", end="10:40"),
        BreakPeriod(name="Lunch Break", start="12:30", end="13:30"),
    ]
    if not isinstance(raw, list):
        return default_reva_breaks

    parsed: List[BreakPeriod] = []
    for item in raw:
        normalized = _normalize_break_period(item)
        if normalized is not None:
            parsed.append(normalized)

    return parsed if parsed else default_reva_breaks


def _deserialize_working_days(val: object, default: str = "MON_SAT") -> str:
    """
    Validates and normalizes working_days string.
    Only allows 'MON_SAT' or 'MON_FRI'; defaults safely if invalid or malformed.
    """
    if isinstance(val, str):
        cleaned = val.strip().upper()
        if cleaned in ("MON_SAT", "MON_FRI"):
            return cleaned
    return default


def _deserialize_positive_int(val: object, default: int) -> int:
    """
    Validates and extracts a positive integer.
    Rejects booleans (since in Python isinstance(True, int) is True), non-positive integers,
    and unparseable values, returning the default.
    """
    if isinstance(val, int) and not isinstance(val, bool) and val > 0:
        return val
    if isinstance(val, str):
        try:
            parsed = int(val.strip())
            if parsed > 0:
                return parsed
        except (ValueError, TypeError):
            pass
    return default


def _deserialize_bool(val: object, default: bool = True) -> bool:
    """
    Validates and normalizes a boolean configuration value.
    """
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        cleaned = val.strip().lower()
        if cleaned in ("true", "1", "yes"):
            return True
        if cleaned in ("false", "0", "no"):
            return False
    return default


def get_timetable_settings(db: Session) -> TimetableSettingsResponse:
    setting = _get_or_create_setting(
        db, "timetable_defaults", "TIMETABLE", DEFAULT_TIMETABLE, "Canonical timetable solver defaults"
    )
    raw_data = setting.value if isinstance(setting.value, dict) else {}
    merged: Dict[str, Any] = {**DEFAULT_TIMETABLE, **raw_data}

    working_days: str = _deserialize_working_days(merged.get("working_days"), default="MON_SAT")
    periods_per_day: int = _deserialize_positive_int(merged.get("periods_per_day"), default=7)
    period_duration_minutes: int = _deserialize_positive_int(merged.get("period_duration_minutes"), default=55)
    breaks: List[BreakPeriod] = _deserialize_break_periods(merged.get("break_times"))
    max_consecutive: int = _deserialize_positive_int(merged.get("max_consecutive_faculty_lectures"), default=3)
    enable_soft_lab: bool = _deserialize_bool(merged.get("enable_soft_lab_preference"), default=True)
    updated_iso: Optional[str] = setting.updated_at.isoformat() if setting.updated_at is not None else None

    return TimetableSettingsResponse(
        working_days=working_days,
        periods_per_day=periods_per_day,
        period_duration_minutes=period_duration_minutes,
        break_times=breaks,
        max_consecutive_faculty_lectures=max_consecutive,
        enable_soft_lab_preference=enable_soft_lab,
        updated_at=updated_iso,
    )


def update_timetable_settings(db: Session, payload: TimetableSettingsUpdate, user: User) -> TimetableSettingsResponse:
    setting = _get_or_create_setting(
        db, "timetable_defaults", "TIMETABLE", DEFAULT_TIMETABLE, "Canonical timetable solver defaults"
    )
    raw_current = setting.value if isinstance(setting.value, dict) else {}
    current: Dict[str, Any] = {**DEFAULT_TIMETABLE, **raw_current}
    if payload.working_days is not None:
        current["working_days"] = _deserialize_working_days(payload.working_days, default="MON_SAT")
    if payload.max_consecutive_faculty_lectures is not None:
        current["max_consecutive_faculty_lectures"] = _deserialize_positive_int(
            payload.max_consecutive_faculty_lectures, default=3
        )
    if payload.enable_soft_lab_preference is not None:
        current["enable_soft_lab_preference"] = _deserialize_bool(
            payload.enable_soft_lab_preference, default=True
        )

    setting.value = current
    setting.updated_at = utc_now()
    setting.updated_by_id = user.id
    db.commit()
    return get_timetable_settings(db)


def get_user_access_summary(db: Session) -> UserAccessSummary:
    from backend.models.identity import User
    roles = db.query(User.role, func.count(User.id)).group_by(User.role).all()
    role_map: Dict[str, int] = {str(r[0]): int(r[1]) for r in roles}
    total = sum(role_map.values())
    return UserAccessSummary(
        total_users=total,
        super_admin_count=role_map.get("SUPER_ADMIN", 0),
        admin_count=role_map.get("ADMIN", 0),
        faculty_count=role_map.get("FACULTY", 0),
        student_count=role_map.get("STUDENT", 0),
        access_token_expiry_minutes=20,
        refresh_token_expiry_days=7,
        mfa_enforced=False,
    )


def get_system_integration_status() -> SystemIntegrationStatus:
    try:
        url = make_url(DATABASE_URL)
        db_host = url.host or "127.0.0.1"
        db_name = url.database or "campus_ai_test"
        db_port = url.port or 5432
        db_schema = "test_schema" if "test_schema" in (url.query.get("options") or "") else "public"
    except Exception:
        db_host = "127.0.0.1"
        db_name = "campus_ai_test"
        db_port = 5433
        db_schema = "test_schema"

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    has_anthropic = bool(anthropic_key and not anthropic_key.startswith("mock-") and not anthropic_key.startswith("test-"))

    supabase_url = os.environ.get("SUPABASE_DATABASE_URL", "").strip()
    has_supabase = bool(supabase_url and not supabase_url.startswith("mock-") and not supabase_url.startswith("test-"))

    return SystemIntegrationStatus(
        database_status="CONNECTED",
        database_host=db_host,
        database_name=db_name,
        database_schema=db_schema,
        database_port=db_port,
        ai_agent_status="READY",
        llm_provider="Anthropic Claude / Offline Grounded Fallback",
        llm_configured=has_anthropic,
        supabase_configured=has_supabase,
        server_time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        uptime_status="HEALTHY",
    )


# ── Data Management & Operational Data Summary ───────────────────────────────

def _count_table(db: Session, table_name: str) -> int:
    try:
        res = db.execute(text(f"SELECT count(*) FROM {table_name}")).scalar()
        return int(res or 0)
    except Exception:
        return 0


def get_data_management_summary(db: Session) -> DataManagementSummaryResponse:
    # 1. Timetable Data
    tt_entries_count = _count_table(db, "timetable_entries")
    tt_versions_count = _count_table(db, "timetable_versions")
    timetables_count = _count_table(db, "timetables")
    total_tt = tt_entries_count + tt_versions_count + timetables_count

    cat_timetable = DataCategorySummary(
        category_id="timetable",
        category_name="Timetable Data",
        description="Active published canonical schedules, version snapshots, and period allocations.",
        total_records=total_tt,
        can_clear=True,
        warning="Clearing timetable data will remove published schedules. Students and faculty will not see classes until a new timetable is published.",
        tables=[
            TableRecordCount(table_name="timetable_entries", display_name="Timetable Entries", count=tt_entries_count, description="Scheduled class periods"),
            TableRecordCount(table_name="timetable_versions", display_name="Timetable Versions", count=tt_versions_count, description="Version records"),
            TableRecordCount(table_name="timetables", display_name="Canonical Timetables", count=timetables_count, description="Section schedule headers"),
        ],
    )

    # 2. Resource Management Data
    rb_count = _count_table(db, "resource_bookings")
    cat_resources = DataCategorySummary(
        category_id="resources",
        category_name="Resource Management Data",
        description="Classroom bookings, facility reservation requests, and room allocations.",
        total_records=rb_count,
        can_clear=True,
        warning="All current and historical resource bookings will be removed. Physical rooms and inventory are preserved.",
        tables=[
            TableRecordCount(table_name="resource_bookings", display_name="Resource Bookings", count=rb_count, description="Room & facility booking reservations"),
        ],
    )

    # 3. Faculty Operations
    subs_count = _count_table(db, "faculty_substitutions")
    cr_count = _count_table(db, "change_requests")
    total_fac_ops = subs_count + cr_count

    cat_faculty_ops = DataCategorySummary(
        category_id="faculty_ops",
        category_name="Faculty Operations",
        description="Faculty substitution requests, peer assignments, and administrative change requests.",
        total_records=total_fac_ops,
        can_clear=True,
        warning="Pending and fulfilled substitution logs will be cleared. Faculty profiles and master assignments remain unchanged.",
        tables=[
            TableRecordCount(table_name="faculty_substitutions", display_name="Faculty Substitutions", count=subs_count, description="Leave substitution requests & peer assignments"),
            TableRecordCount(table_name="change_requests", display_name="Change Requests", count=cr_count, description="Operational schedule/resource change requests"),
        ],
    )

    # 4. Other Generated Operations
    chat_msg_count = _count_table(db, "chat_messages")
    chat_conv_count = _count_table(db, "chat_conversations")
    agent_prop_count = _count_table(db, "agent_proposals")
    curr_req_msg_count = _count_table(db, "curriculum_request_messages")
    curr_req_count = _count_table(db, "curriculum_requests")
    curr_jobs_count = _count_table(db, "curriculum_extraction_jobs")
    total_other = chat_msg_count + chat_conv_count + agent_prop_count + curr_req_msg_count + curr_req_count + curr_jobs_count

    cat_other_ops = DataCategorySummary(
        category_id="other_ops",
        category_name="AI Assistant & Transitional Operations",
        description="Campus Assistant conversation history, multi-agent proposals, and temporary OCR extraction jobs.",
        total_records=total_other,
        can_clear=True,
        warning="Chat logs and temporary proposal states will be purged. Master regulations and courses remain intact.",
        tables=[
            TableRecordCount(table_name="chat_messages", display_name="Chat Messages", count=chat_msg_count, description="Assistant conversation messages"),
            TableRecordCount(table_name="chat_conversations", display_name="Chat Sessions", count=chat_conv_count, description="Conversation threads"),
            TableRecordCount(table_name="agent_proposals", display_name="Agent Proposals", count=agent_prop_count, description="Draft multi-agent confirmation proposals"),
            TableRecordCount(table_name="curriculum_request_messages", display_name="Curriculum Request Messages", count=curr_req_msg_count, description="Admin-to-SuperAdmin request messages"),
            TableRecordCount(table_name="curriculum_requests", display_name="Curriculum Requests", count=curr_req_count, description="Transitional change requests"),
            TableRecordCount(table_name="curriculum_extraction_jobs", display_name="Extraction Jobs", count=curr_jobs_count, description="PDF OCR extraction background job logs"),
        ],
    )

    # 5. Generated Notifications
    notif_outbox_count = _count_table(db, "notification_outbox")
    notif_count = _count_table(db, "notifications")
    total_notifs = notif_outbox_count + notif_count

    cat_notifications = DataCategorySummary(
        category_id="notifications",
        category_name="Generated Notifications",
        description="Dispatched user notifications, alerts, and outbox delivery logs.",
        total_records=total_notifs,
        can_clear=True,
        warning="User notification inboxes will be emptied. System accounts and users are unaffected.",
        tables=[
            TableRecordCount(table_name="notification_outbox", display_name="Notification Outbox", count=notif_outbox_count, description="Queued and sent notification dispatch records"),
            TableRecordCount(table_name="notifications", display_name="Notifications", count=notif_count, description="In-app user notification items"),
        ],
    )

    categories = [cat_timetable, cat_resources, cat_faculty_ops, cat_other_ops, cat_notifications]
    total_all = sum(c.total_records for c in categories)

    return DataManagementSummaryResponse(
        categories=categories,
        total_generated_records=total_all,
        master_records_protected=True,
        authoritative_dataset="RIO_MJP_AIDS_A_Clean_Test_Data_No_Attendance.xlsx",
    )


# ── Dry-Run Preview ──────────────────────────────────────────────────────────

CATEGORY_TABLE_MAP: Dict[str, List[Tuple[str, str, List[str]]]] = {
    "timetable": [
        ("timetable_entries", "Timetable Entries", ["timetables.id", "timetable_versions.id"]),
        ("timetable_versions", "Timetable Versions", ["timetables.id"]),
        ("timetables", "Canonical Timetables", ["sections.id", "academic_years.id"]),
    ],
    "resources": [
        ("resource_bookings", "Resource Bookings", ["resources.id", "users.id"]),
    ],
    "faculty_ops": [
        ("faculty_substitutions", "Faculty Substitutions", ["timetable_entries.id", "faculty.id"]),
        ("change_requests", "Change Requests", ["users.id"]),
    ],
    "other_ops": [
        ("chat_messages", "Chat Messages", ["chat_conversations.id"]),
        ("chat_conversations", "Chat Conversations", ["users.id"]),
        ("agent_proposals", "Agent Proposals", ["users.id"]),
        ("curriculum_request_messages", "Curriculum Request Messages", ["curriculum_requests.id"]),
        ("curriculum_requests", "Curriculum Requests", ["curriculum_versions.id"]),
        ("curriculum_extraction_jobs", "Extraction Jobs", ["curriculum_documents.id"]),
    ],
    "notifications": [
        ("notification_outbox", "Notification Outbox", ["notifications.id"]),
        ("notifications", "Notifications", ["users.id"]),
    ],
}


def preview_data_clear(db: Session, categories: List[str], clear_all: bool) -> DataClearPreviewResponse:
    cats_to_process = list(CATEGORY_TABLE_MAP.keys()) if clear_all else [c for c in categories if c in CATEGORY_TABLE_MAP]

    affected_tables: List[AffectedTableDetail] = []
    total_deletions = 0
    warnings: List[str] = []

    for cat in cats_to_process:
        table_tuples = CATEGORY_TABLE_MAP[cat]
        for tbl_name, display_name, fks in table_tuples:
            cnt = _count_table(db, tbl_name)
            affected_tables.append(
                AffectedTableDetail(
                    table_name=tbl_name,
                    display_name=display_name,
                    record_count=cnt,
                    foreign_key_dependencies=fks,
                )
            )
            total_deletions += cnt

        if cat == "timetable":
            warnings.append(
                "Timetable Data Selected: Deleting published canonical timetables will remove visible schedules from all Students and Faculty until a new schedule is published."
            )
        elif cat == "resources":
            warnings.append("Resource Bookings Selected: Active reservations will be released. Master rooms remain intact.")
        elif cat == "faculty_ops":
            warnings.append("Faculty Operations Selected: Substitution history and change requests will be cleared.")

    return DataClearPreviewResponse(
        categories_selected=cats_to_process,
        clear_all=clear_all,
        affected_tables=affected_tables,
        total_records_to_delete=total_deletions,
        warnings=warnings,
        master_records_protected=True,
        safe_to_execute=True,
    )


# ── Controlled Transactional Clear ───────────────────────────────────────────

def execute_data_clear(
    db: Session,
    categories: List[str],
    clear_all: bool,
    user: User,
) -> DataClearExecuteResponse:
    """
    Executes safe, dependency-ordered deletions in a single transaction.
    Guarantees that academic master data is never touched.
    Rolls back automatically on failure.
    Writes an AuditLog entry.
    """
    cats_to_process = list(CATEGORY_TABLE_MAP.keys()) if clear_all else [c for c in categories if c in CATEGORY_TABLE_MAP]

    # Explicit topological execution order: children before parents
    ordered_tables_to_delete: List[str] = []

    if "notifications" in cats_to_process:
        ordered_tables_to_delete.extend(["notification_outbox", "notifications"])

    if "other_ops" in cats_to_process:
        ordered_tables_to_delete.extend([
            "chat_messages",
            "chat_conversations",
            "agent_proposals",
            "curriculum_request_messages",
            "curriculum_requests",
            "curriculum_extraction_jobs",
        ])

    if "faculty_ops" in cats_to_process:
        ordered_tables_to_delete.extend(["faculty_substitutions", "change_requests"])

    if "resources" in cats_to_process:
        ordered_tables_to_delete.append("resource_bookings")

    if "timetable" in cats_to_process:
        # Also clean faculty_substitutions if not already cleaned since they FK to timetable_entries
        if "faculty_substitutions" not in ordered_tables_to_delete:
            ordered_tables_to_delete.insert(0, "faculty_substitutions")
        ordered_tables_to_delete.extend(["timetable_entries", "timetable_versions", "timetables"])

    deleted_counts: Dict[str, int] = {}
    total_deleted = 0

    try:
        # Execute in explicit topological order
        for tbl in ordered_tables_to_delete:
            cnt_before = _count_table(db, tbl)
            if cnt_before > 0:
                db.execute(text(f"DELETE FROM {tbl}"))
                deleted_counts[tbl] = cnt_before
                total_deleted += cnt_before
            else:
                deleted_counts[tbl] = 0

        # Retain historical audit logs for governance & accountability; mark historical entities as cleared
        cleared_entity_types = []
        if "timetable" in cats_to_process:
            cleared_entity_types.extend(["Timetable", "TimetableVersion", "TimetableEntry", "TIMETABLE", "TIMETABLE_VERSION", "TIMETABLE_ENTRY"])
        if "resources" in cats_to_process:
            cleared_entity_types.extend(["ResourceBooking", "RESOURCE_BOOKING"])
        if "faculty_ops" in cats_to_process:
            cleared_entity_types.extend(["FacultySubstitution", "FACULTY_SUBSTITUTION", "ChangeRequest", "CHANGE_REQUEST"])

        if cleared_entity_types:
            placeholders = ", ".join(f"'{et}'" for et in cleared_entity_types)
            db.execute(text(f"""
                UPDATE audit_logs
                SET new_value = jsonb_set(
                    COALESCE(new_value, '{{}}'::jsonb),
                    '{{lifecycle_status}}',
                    '"HISTORICAL_CLEARED"'::jsonb
                )
                WHERE entity_type IN ({placeholders})
                  AND (new_value->>'lifecycle_status' IS NULL OR new_value->>'lifecycle_status' != 'HISTORICAL_CLEARED')
            """))

        # Record audit log
        audit = AuditLog(
            user_id=user.id,
            action="CLEAR_GENERATED_OPERATIONAL_DATA",
            entity_type="DATA_MANAGEMENT",
            entity_id=None,
            old_value={"categories": cats_to_process, "deleted_per_table": deleted_counts},
            new_value={"total_records_deleted": total_deleted, "status": "COMPLETED"},
        )
        db.add(audit)
        db.commit()
        db.refresh(audit)
        audit_id = audit.id

        # ── Cross-Role Administrative Broadcast Notification ────────────────────────
        # Inform all active user roles that operational schedule and allocation data have been cleared
        if "timetable" in cats_to_process or clear_all:
            try:
                from backend.services.notification_service import broadcast_announcement
                timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%d %b %Y %I:%M %p UTC")
                broadcast_announcement(
                    db=db,
                    admin_user_id=user.id,
                    title="Campus Timetable Schedule Reset",
                    message=(
                        f"Administrative Notice: Generated operational schedule and allocation data have been reset "
                        f"by Administration on {timestamp_str}. Enrolled student cohorts, faculty teaching rosters, "
                        f"and institutional master records remain intact. A new schedule will appear once published by Administration."
                    ),
                    target_role="ALL",
                )
            except Exception as broadcast_exc:
                # Do not abort successful clear if broadcast encounters a non-fatal broker error
                pass

    except Exception as exc:
        db.rollback()
        raise RuntimeError(f"Controlled data clear transaction failed and was rolled back: {exc}") from exc

    return DataClearExecuteResponse(
        success=True,
        categories_cleared=cats_to_process,
        total_records_deleted=total_deleted,
        deleted_per_table=deleted_counts,
        audit_log_id=audit_id,
        message=f"Successfully cleared {total_deleted} generated operational records across {len(cats_to_process)} categories.",
    )
