"""
agents/tools package
--------------------
Unified tool registry for Query Agent with strict authorization and typed schemas.
All 12 prioritized read-only campus tools are registered with server-side RBAC.
"""

from typing import Any, Callable, Dict, List
from sqlalchemy.orm import Session

from backend.models.identity import User
from agents.tools.student_tools import (
    get_student_timetable_data,
    get_my_timetable_data,
    get_class_status_data,
)
from agents.tools.faculty_tools import (
    get_faculty_schedule_data,
    get_faculty_timetable_data,
    get_faculty_profile_data,
    get_faculty_information_data,
    get_available_faculty_data,
)
from agents.tools.campus_tools import (
    get_course_details_data,
    get_course_information_data,
    get_room_or_lab_details_data,
    get_room_availability_data,
    get_lab_availability_data,
    get_academic_calendar_data,
    get_campus_room_inventory_data,
    get_published_timetable_status_data,
    get_recent_timetable_changes_data,
    get_relevant_announcements_data,
)
from agents.tools.department_tools import get_department_timetable_data
from agents.tools.resource_tools import (
    get_user_bookings_data,
    get_booking_details_data,
    get_resource_booking_status_data,
    discover_resources_data,
    check_resource_availability_data,
    execute_create_booking_data,
    execute_cancel_booking_data,
)
from agents.tools.event_tools import (
    list_visible_events_data,
    get_published_event_details_data,
    get_ongoing_events_data,
    get_upcoming_events_data,
    validate_event_data,
    create_event_draft_data,
    update_event_draft_data,
    submit_event_for_approval_data,
    approve_event_data,
    reject_event_data,
    publish_event_data,
    cancel_event_data,
    list_my_clubs_data,
    list_club_activities_data,
    create_club_activity_data,
    update_club_activity_data,
)
from agents.tools.substitution_tools import (
    list_my_substitution_requests_data,
    list_my_substitution_assignments_data,
    list_pending_substitutions_data,
    get_date_substitutions_data,
)
from agents.tools.placement_tools import (
    create_placement_drive_draft_data,
    validate_placement_drive_data,
    publish_placement_drive_data,
    update_placement_drive_data,
    cancel_placement_drive_data,
    list_published_placement_drives_data,
    get_placement_drive_details_data,
    get_drive_deadlines_and_schedule_data,
    get_student_drive_eligibility_data,
    list_my_eligible_drives_data,
)

# Tool registry with documentation for LLM tool binding
QUERY_TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    # 1. get_my_timetable
    {
        "name": "get_my_timetable",
        "description": "Retrieves the official published timetable for the authenticated user (student section classes or faculty teaching slots).",
        "parameters": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "description": "Optional day of the week to filter (e.g. 'TODAY', 'TOMORROW', 'MONDAY'). If omitted, returns all scheduled days.",
                }
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    # 2. get_student_timetable
    {
        "name": "get_student_timetable",
        "description": "Retrieves the official published timetable for a student. Non-admin students can only query their own timetable.",
        "parameters": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "description": "Optional day of the week to filter (e.g. 'MONDAY').",
                },
                "target_student_id": {
                    "type": "integer",
                    "description": "Specific student ID (Admin-only). Non-admin students attempting to query other student IDs are rejected.",
                },
            },
        },
        "allowed_roles": ["STUDENT", "ADMIN"],
    },
    # 3. get_faculty_timetable
    {
        "name": "get_faculty_timetable",
        "description": "Retrieves the published teaching schedule for faculty. Faculty may only view their own schedule; Admins may view any faculty member.",
        "parameters": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "description": "Optional day of the week to filter.",
                },
                "target_faculty_id": {
                    "type": "integer",
                    "description": "Target faculty ID (Admin-authorized).",
                },
                "target_faculty_name": {
                    "type": "string",
                    "description": "Target faculty name to search (Admin-authorized).",
                },
            },
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    # Also support alias get_faculty_schedule for backwards compatibility
    {
        "name": "get_faculty_schedule",
        "description": "Retrieves the published teaching schedule for the authenticated faculty member.",
        "parameters": {
            "type": "object",
            "properties": {
                "day": {"type": "string", "description": "Optional day of the week to filter."},
                "target_faculty_id": {"type": "integer", "description": "Optional target faculty ID."},
            },
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    # 4. get_department_timetable
    {
        "name": "get_department_timetable",
        "description": "Retrieves the published schedule for an academic department. Restricted to ADMIN and assigned department FACULTY. Students forbidden.",
        "parameters": {
            "type": "object",
            "properties": {
                "department_id": {"type": "integer", "description": "Optional department ID."},
                "day": {"type": "string", "description": "Optional day of the week to filter."},
            },
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    # 5. get_course_information
    {
        "name": "get_course_information",
        "description": "Looks up course catalog information, credits, department, course type, and assigned faculty instructors by code or name.",
        "parameters": {
            "type": "object",
            "properties": {
                "query_str": {
                    "type": "string",
                    "description": "Course code (e.g. 'CS101', 'EE614') or course title.",
                }
            },
            "required": ["query_str"],
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_course_details",
        "description": "Looks up course catalog information, credits, and department by course code or title.",
        "parameters": {
            "type": "object",
            "properties": {
                "query_str": {"type": "string", "description": "Course code or title."}
            },
            "required": ["query_str"],
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    # 6. get_faculty_information
    {
        "name": "get_faculty_information",
        "description": "Looks up academic directory profile information, department, designation, specialization, and courses taught for faculty members.",
        "parameters": {
            "type": "object",
            "properties": {
                "search_query": {
                    "type": "string",
                    "description": "Faculty name, ID, or research specialization to search for.",
                }
            },
            "required": ["search_query"],
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_faculty_profile",
        "description": "Looks up faculty profile information by name or specialization.",
        "parameters": {
            "type": "object",
            "properties": {
                "search_query": {"type": "string", "description": "Faculty name or specialization."}
            },
            "required": ["search_query"],
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    # 7. get_room_availability
    {
        "name": "get_room_availability",
        "description": "Checks classroom or facility availability for a given day/date and time slot against published timetable entries and active bookings.",
        "parameters": {
            "type": "object",
            "properties": {
                "day": {"type": "string", "description": "Day of week (e.g. 'MONDAY', 'TODAY')."},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format."},
                "start_time": {"type": "string", "description": "Start time in HH:MM format."},
                "end_time": {"type": "string", "description": "End time in HH:MM format."},
                "room_query": {"type": "string", "description": "Room number or name to check specifically."},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    # 8. get_lab_availability
    {
        "name": "get_lab_availability",
        "description": "Checks laboratory availability specifically for a given day/date and time slot.",
        "parameters": {
            "type": "object",
            "properties": {
                "day": {"type": "string", "description": "Day of week (e.g. 'MONDAY', 'TODAY')."},
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format."},
                "start_time": {"type": "string", "description": "Start time in HH:MM format."},
                "end_time": {"type": "string", "description": "End time in HH:MM format."},
                "lab_query": {"type": "string", "description": "Lab name or number to check."},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    # 9. get_resource_booking_status
    {
        "name": "get_resource_booking_status",
        "description": "Retrieves the status of campus resource or lab bookings (own bookings for students/faculty; all for admin).",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "integer", "description": "Optional specific booking ID."},
                "status_filter": {"type": "string", "description": "Optional status filter ('PENDING', 'APPROVED', 'CANCELLED')."},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    # 10. get_published_timetable_status
    {
        "name": "get_published_timetable_status",
        "description": "Checks the active published timetable version, publication date, and class count. Hides draft versions from non-admins.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    # 11. get_recent_timetable_changes
    {
        "name": "get_recent_timetable_changes",
        "description": "Retrieves recent timetable changes, rescheduling notices, disruptions, or room adjustments for the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of recent changes to return."},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    # 12. get_relevant_announcements
    {
        "name": "get_relevant_announcements",
        "description": "Retrieves official campus announcements, broadcast notices, and upcoming academic calendar events.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximum number of announcements to return."},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    # Additional existing tools
    {
        "name": "get_class_status",
        "description": "Evaluates real-time class status (UPCOMING, ONGOING, COMPLETED, CANCELLED, RESCHEDULED) based on current time and published schedule.",
        "parameters": {"type": "object", "properties": {}},
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_room_or_lab_details",
        "description": "Looks up physical room or laboratory capacity, room type, and building location.",
        "parameters": {
            "type": "object",
            "properties": {
                "room_query": {"type": "string", "description": "Room number or facility name."}
            },
            "required": ["room_query"],
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_academic_calendar",
        "description": "Retrieves scheduled university events, holidays, and academic calendar dates.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_type": {"type": "string", "description": "Optional event type: 'HOLIDAY', 'EXAM', 'EVENT'."}
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_campus_room_inventory",
        "description": "Returns total count of registered active rooms by room type.",
        "parameters": {
            "type": "object",
            "properties": {
                "room_type": {"type": "string", "description": "Optional room type filter."}
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_available_faculty",
        "description": "Identifies active faculty members available during a given date and time interval.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Target date in YYYY-MM-DD format"},
                "start_time": {"type": "string", "description": "Start time in HH:MM format"},
                "end_time": {"type": "string", "description": "End time in HH:MM format"},
                "department_id": {"type": "integer", "description": "Optional department filter"},
            },
            "required": ["date", "start_time", "end_time"],
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "discover_resources",
        "description": "Searches campus facilities, seminar halls, and labs by type, capacity, and location.",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_type": {"type": "string"},
                "min_capacity": {"type": "integer"},
                "search_query": {"type": "string"},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "check_resource_availability",
        "description": "Checks authoritative interval conflicts against approved bookings and published timetables.",
        "parameters": {
            "type": "object",
            "properties": {
                "resource_id": {"type": "integer"},
                "date": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
            },
            "required": ["resource_id", "date", "start_time", "end_time"],
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_user_bookings",
        "description": "Retrieves the authenticated user's submitted resource bookings.",
        "parameters": {"type": "object", "properties": {}},
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_booking_details",
        "description": "Retrieves details of a specific resource booking request with role privacy masking.",
        "parameters": {
            "type": "object",
            "properties": {"booking_id": {"type": "integer"}},
            "required": ["booking_id"],
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "execute_cancel_booking",
        "description": "Cancels a resource booking request owned by the user or as Administrator.",
        "parameters": {
            "type": "object",
            "properties": {"booking_id": {"type": "integer"}},
            "required": ["booking_id"],
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "resolve_academic_scope",
        "description": "Resolves natural-language text into a validated academic scope.",
        "parameters": {
            "type": "object",
            "properties": {"query_text": {"type": "string"}},
            "required": ["query_text"],
        },
        "allowed_roles": ["ADMIN"],
    },
    {
        "name": "analyze_scheduling_readiness",
        "description": "Performs pre-flight data readiness analysis for a resolved academic scope.",
        "parameters": {
            "type": "object",
            "properties": {"scope": {"type": "object"}},
            "required": ["scope"],
        },
        "allowed_roles": ["ADMIN"],
    },
    # Campus Events & Club Coordination Tools
    {
        "name": "list_visible_events",
        "description": "Lists published campus events and activities visible to the current user with optional category or time filters.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Optional category filter: SEMINAR, WORKSHOP, GUEST_LECTURE, COMPETITION, HACKATHON, CULTURAL, SPORTS, etc."},
                "time_filter": {"type": "string", "description": "TODAY, ONGOING, THIS_WEEK, UPCOMING, COMPLETED"},
                "search": {"type": "string", "description": "Optional search term for event title/description"},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_published_event_details",
        "description": "Retrieves comprehensive information about a specific published event.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer", "description": "ID of the event"},
                "title": {"type": "string", "description": "Title of the event"},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_ongoing_events",
        "description": "Lists all events that are currently active and happening right now.",
        "parameters": {"type": "object", "properties": {}},
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_upcoming_events",
        "description": "Lists upcoming scheduled campus events and workshops.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Optional category filter"},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "create_event_draft",
        "description": "Creates a draft for a new campus event. Requires EVENT_COORDINATOR or ADMIN role.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "category": {"type": "string"},
                "start_time": {"type": "string", "description": "ISO datetime or 'YYYY-MM-DD HH:MM'"},
                "end_time": {"type": "string", "description": "ISO datetime or 'YYYY-MM-DD HH:MM'"},
                "room_id": {"type": "integer"},
                "venue_name": {"type": "string"},
                "description": {"type": "string"},
                "target_audience": {"type": "string", "description": "ALL, STUDENT, FACULTY, DEPARTMENT_ONLY"},
                "requires_approval": {"type": "boolean", "default": True},
            },
            "required": ["title", "category", "start_time", "end_time"],
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "update_event_draft",
        "description": "Updates details of an event draft or permits updating event timings/venue.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "room_id": {"type": "integer"},
                "venue_name": {"type": "string"},
            },
            "required": ["event_id"],
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "validate_event",
        "description": "Verifies whether a proposed venue and time window is conflict-free across timetable classes, resource bookings, and other events.",
        "parameters": {
            "type": "object",
            "properties": {
                "room_id": {"type": "integer"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "exclude_event_id": {"type": "integer"},
            },
            "required": ["room_id", "start_time", "end_time"],
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "submit_event_for_approval",
        "description": "Submits a draft event for administrator review.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
            },
            "required": ["event_id"],
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "approve_event",
        "description": "Approves and publishes a pending event. Administrator only.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "notes": {"type": "string"},
            },
            "required": ["event_id"],
        },
        "allowed_roles": ["ADMIN"],
    },
    {
        "name": "reject_event",
        "description": "Rejects a pending event submission with a reason. Administrator only.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["event_id", "reason"],
        },
        "allowed_roles": ["ADMIN"],
    },
    {
        "name": "publish_event",
        "description": "Directly publishes an event (permitted for Admin or coordinators with EVENT_DIRECT_PUBLISH).",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
            },
            "required": ["event_id"],
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "cancel_event",
        "description": "Cancels a scheduled or published event with cancellation notification.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["event_id"],
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "list_my_clubs",
        "description": "Lists the clubs assigned to the current faculty member via CLUB_COORDINATOR capability (or all clubs for Admin).",
        "parameters": {"type": "object", "properties": {}},
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "list_club_activities",
        "description": "Lists published or permitted activities and workshops organized by a campus club.",
        "parameters": {
            "type": "object",
            "properties": {
                "club_id": {"type": "integer"},
                "club_name": {"type": "string"},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "create_club_activity",
        "description": "Creates an activity draft under an assigned club. Requires CLUB_COORDINATOR capability for that club.",
        "parameters": {
            "type": "object",
            "properties": {
                "club_id": {"type": "integer"},
                "title": {"type": "string"},
                "category": {"type": "string", "default": "CLUB_ACTIVITY"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "room_id": {"type": "integer"},
                "venue_name": {"type": "string"},
                "description": {"type": "string"},
                "requires_approval": {"type": "boolean", "default": True},
            },
            "required": ["club_id", "title", "start_time", "end_time"],
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "update_club_activity",
        "description": "Updates a club activity draft.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "room_id": {"type": "integer"},
                "venue_name": {"type": "string"},
            },
            "required": ["event_id"],
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    # -----------------------------------------------------------------------
    # Faculty Substitution Tools
    # -----------------------------------------------------------------------
    {
        "name": "list_my_substitution_requests",
        "description": "Lists substitution requests submitted by or concerning the authenticated faculty member.",
        "parameters": {"type": "object", "properties": {}},
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "list_my_substitution_assignments",
        "description": "Lists classes where authenticated faculty is covering as substitute teacher.",
        "parameters": {"type": "object", "properties": {}},
        "allowed_roles": ["FACULTY"],
    },
    {
        "name": "list_pending_substitutions",
        "description": "Lists pending substitution requests awaiting approval for Admins and Coordinators.",
        "parameters": {"type": "object", "properties": {}},
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "get_date_substitutions",
        "description": "Checks active faculty substitutions for a given date (e.g. today or tomorrow).",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date to query (YYYY-MM-DD or today/tomorrow)"},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    # -----------------------------------------------------------------------
    # CDC Placement Management Tools
    # -----------------------------------------------------------------------
    {
        "name": "list_published_placement_drives",
        "description": "Lists active, published campus placement drives with compensation and role details.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_type": {"type": "string", "description": "FULL_TIME, INTERNSHIP, INTERN_PLUS_FULL_TIME"},
                "tier": {"type": "string", "description": "TIER_1, DREAM, SUPER_DREAM, CORE"},
                "search": {"type": "string", "description": "Search keyword for company or job role"},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "list_my_eligible_drives",
        "description": "Lists placement drives where authenticated student meets all deterministic criteria (branch, CGPA, backlogs, graduation year).",
        "parameters": {"type": "object", "properties": {}},
        "allowed_roles": ["STUDENT"],
    },
    {
        "name": "get_placement_drive_details",
        "description": "Retrieves comprehensive details of a placement drive including company, role, packages, criteria, and selection rounds.",
        "parameters": {
            "type": "object",
            "properties": {
                "drive_id": {"type": "integer"},
                "company_name": {"type": "string"},
                "title": {"type": "string"},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_drive_deadlines_and_schedule",
        "description": "Retrieves registration deadlines, assessment dates, and interview schedules for placement drives.",
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_student_drive_eligibility",
        "description": "Performs deterministic eligibility evaluation for student against a company placement drive.",
        "parameters": {
            "type": "object",
            "properties": {
                "drive_id": {"type": "integer"},
                "company_name": {"type": "string"},
            },
        },
        "allowed_roles": ["STUDENT"],
    },
    {
        "name": "create_placement_drive_draft",
        "description": "Creates a placement drive draft (CDC Coordinator / Admin only).",
        "parameters": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "title": {"type": "string"},
                "job_role": {"type": "string"},
                "application_deadline": {"type": "string"},
                "job_type": {"type": "string", "default": "FULL_TIME"},
                "work_location": {"type": "string"},
                "compensation_details": {"type": "string"},
                "min_cgpa": {"type": "number"},
                "graduation_year": {"type": "integer"},
                "max_active_backlogs": {"type": "integer"},
            },
            "required": ["company_name", "title", "job_role", "application_deadline"],
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "validate_placement_drive",
        "description": "Performs pre-flight validation on drive dates, criteria, and duplicate detection.",
        "parameters": {
            "type": "object",
            "properties": {
                "drive_id": {"type": "integer"},
            },
            "required": ["drive_id"],
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "publish_placement_drive",
        "description": "Publishes a validated placement drive to the student portal and dispatches notifications.",
        "parameters": {
            "type": "object",
            "properties": {
                "drive_id": {"type": "integer"},
            },
            "required": ["drive_id"],
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "update_placement_drive",
        "description": "Updates placement drive fields with optimistic version control.",
        "parameters": {
            "type": "object",
            "properties": {
                "drive_id": {"type": "integer"},
                "compensation_details": {"type": "string"},
                "application_deadline": {"type": "string"},
                "work_location": {"type": "string"},
                "additional_criteria": {"type": "string"},
                "version": {"type": "integer"},
            },
            "required": ["drive_id"],
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "cancel_placement_drive",
        "description": "Cancels a placement drive with reason and notifies eligible candidates.",
        "parameters": {
            "type": "object",
            "properties": {
                "drive_id": {"type": "integer"},
                "reason": {"type": "string"},
            },
            "required": ["drive_id", "reason"],
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
]


def execute_tool(
    tool_name: str,
    tool_args: Dict[str, Any],
    user: User,
    db: Session,
) -> Dict[str, Any]:
    """
    Safely dispatches tool call with backend-enforced role boundary checks.
    """
    # 1. Verify tool exists
    definition = next((t for t in QUERY_TOOL_DEFINITIONS if t["name"] == tool_name), None)
    if not definition:
        return {"error": f"Tool '{tool_name}' is not recognized or permitted."}

    # 2. Server-side role check (never trust LLM authorization decisions)
    if user.role not in definition["allowed_roles"]:
        return {
            "error": f"Role '{user.role}' is not authorized to use tool '{tool_name}'."
        }

    # 3. Dispatch to implementation
    try:
        # Tool 1: get_my_timetable
        if tool_name == "get_my_timetable":
            return get_my_timetable_data(db=db, user=user, day=tool_args.get("day"))

        # Tool 2: get_student_timetable
        elif tool_name == "get_student_timetable":
            target_sid = tool_args.get("target_student_id") or tool_args.get("student_id")
            return get_student_timetable_data(
                db=db,
                user=user,
                day=tool_args.get("day"),
                target_student_id=target_sid,
            )

        # Tool 3: get_faculty_timetable / get_faculty_schedule
        elif tool_name in ("get_faculty_timetable", "get_faculty_schedule"):
            target_fid = tool_args.get("target_faculty_id") or tool_args.get("faculty_id")
            return get_faculty_timetable_data(
                db=db,
                user=user,
                day=tool_args.get("day"),
                target_faculty_id=target_fid,
                target_faculty_name=tool_args.get("target_faculty_name") or tool_args.get("faculty_name"),
            )

        # Tool 4: get_department_timetable
        elif tool_name == "get_department_timetable":
            return get_department_timetable_data(
                db=db,
                user=user,
                department_id=tool_args.get("department_id"),
                day=tool_args.get("day"),
            )

        # Tool 5: get_course_information / get_course_details
        elif tool_name in ("get_course_information", "get_course_details"):
            q = (
                tool_args.get("query_str")
                or tool_args.get("course_code")
                or tool_args.get("code")
                or tool_args.get("query")
                or ""
            )
            return get_course_information_data(db=db, query_str=str(q))

        # Tool 6: get_faculty_information / get_faculty_profile
        elif tool_name in ("get_faculty_information", "get_faculty_profile"):
            sq = (
                tool_args.get("search_query")
                or tool_args.get("name")
                or tool_args.get("name_or_dept")
                or tool_args.get("query")
                or ""
            )
            return get_faculty_information_data(db=db, viewer=user, search_query=str(sq))

        # Tool 7: get_room_availability
        elif tool_name == "get_room_availability":
            return get_room_availability_data(
                db=db,
                day=tool_args.get("day"),
                date_str=tool_args.get("date"),
                start_time=tool_args.get("start_time"),
                end_time=tool_args.get("end_time"),
                room_query=tool_args.get("room_query") or tool_args.get("room_number"),
                room_type=tool_args.get("room_type"),
            )

        # Tool 8: get_lab_availability
        elif tool_name == "get_lab_availability":
            return get_lab_availability_data(
                db=db,
                day=tool_args.get("day"),
                date_str=tool_args.get("date"),
                start_time=tool_args.get("start_time"),
                end_time=tool_args.get("end_time"),
                lab_query=tool_args.get("lab_query") or tool_args.get("room_query"),
            )

        # Tool 9: get_resource_booking_status / get_user_bookings
        elif tool_name in ("get_resource_booking_status", "get_user_bookings"):
            return get_resource_booking_status_data(
                db=db,
                user=user,
                booking_id=tool_args.get("booking_id"),
                status_filter=tool_args.get("status_filter"),
            )

        # Tool 10: get_published_timetable_status
        elif tool_name == "get_published_timetable_status":
            return get_published_timetable_status_data(db=db, user=user)

        # Tool 11: get_recent_timetable_changes
        elif tool_name == "get_recent_timetable_changes":
            lim = int(tool_args.get("limit", 10))
            return get_recent_timetable_changes_data(db=db, user=user, limit=lim)

        # Tool 12: get_relevant_announcements
        elif tool_name == "get_relevant_announcements":
            lim = int(tool_args.get("limit", 10))
            return get_relevant_announcements_data(db=db, user=user, limit=lim)

        # Additional existing tools
        elif tool_name == "get_class_status":
            return get_class_status_data(db=db, user=user)

        elif tool_name == "get_available_faculty":
            return get_available_faculty_data(
                db=db,
                date=tool_args["date"],
                start_time=tool_args["start_time"],
                end_time=tool_args["end_time"],
                department_id=tool_args.get("department_id"),
            )

        elif tool_name == "get_room_or_lab_details":
            return get_room_or_lab_details_data(
                db=db,
                room_query=tool_args.get("room_query", ""),
            )

        elif tool_name == "get_academic_calendar":
            return get_academic_calendar_data(
                db=db,
                event_type=tool_args.get("event_type"),
            )

        elif tool_name == "get_campus_room_inventory":
            return get_campus_room_inventory_data(
                db=db,
                room_type=tool_args.get("room_type"),
            )

        elif tool_name == "discover_resources":
            return discover_resources_data(
                db=db,
                resource_type=tool_args.get("resource_type"),
                min_capacity=tool_args.get("min_capacity"),
                location_query=tool_args.get("location_query"),
                search_query=tool_args.get("search_query"),
            )

        elif tool_name == "check_resource_availability":
            import datetime
            raw_date = tool_args.get("date")
            raw_st = tool_args.get("start_time")
            raw_et = tool_args.get("end_time")
            if not raw_date or not raw_st or not raw_et:
                return {"error": "Missing required date or time interval."}
            try:
                d = datetime.date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date
                st = datetime.time.fromisoformat(raw_st) if isinstance(raw_st, str) else raw_st
                et = datetime.time.fromisoformat(raw_et) if isinstance(raw_et, str) else raw_et
            except (ValueError, TypeError) as parse_err:
                return {"error": f"Invalid date or time format: {parse_err}"}

            if not isinstance(d, datetime.date) or not isinstance(st, datetime.time) or not isinstance(et, datetime.time):
                return {"error": "Invalid date or time parameters."}

            return check_resource_availability_data(
                db=db,
                resource_id=int(tool_args["resource_id"]),
                date=d,
                start_time=st,
                end_time=et,
            )

        elif tool_name == "get_booking_details":
            return get_booking_details_data(db=db, booking_id=tool_args["booking_id"], user=user)

        elif tool_name == "execute_cancel_booking":
            return execute_cancel_booking_data(db=db, booking_id=tool_args["booking_id"], user=user)

        elif tool_name == "resolve_academic_scope":
            from agents.tools.scheduling_tools import resolve_academic_scope_data
            return resolve_academic_scope_data(
                db=db,
                query_text=tool_args.get("query_text", ""),
                department_id=tool_args.get("department_id"),
                program_id=tool_args.get("program_id"),
                semester_id=tool_args.get("semester_id"),
                academic_year_id=tool_args.get("academic_year_id"),
            )

        elif tool_name == "analyze_scheduling_readiness":
            from agents.tools.scheduling_tools import analyze_scheduling_readiness_data
            return analyze_scheduling_readiness_data(
                db=db,
                scope_dict=tool_args.get("scope", {}),
            )

        # Campus Events & Club Activity Tools
        elif tool_name == "list_visible_events":
            return list_visible_events_data(
                db=db,
                user=user,
                category=tool_args.get("category"),
                time_filter=tool_args.get("time_filter"),
                search=tool_args.get("search"),
            )

        elif tool_name == "get_published_event_details":
            return get_published_event_details_data(
                db=db,
                user=user,
                event_id=tool_args.get("event_id"),
                title=tool_args.get("title"),
            )

        elif tool_name == "get_ongoing_events":
            return get_ongoing_events_data(db=db, user=user)

        elif tool_name == "get_upcoming_events":
            return get_upcoming_events_data(
                db=db,
                user=user,
                category=tool_args.get("category"),
            )

        elif tool_name == "create_event_draft":
            return create_event_draft_data(
                db=db,
                user=user,
                title=tool_args["title"],
                category=tool_args["category"],
                start_time=tool_args["start_time"],
                end_time=tool_args["end_time"],
                room_id=tool_args.get("room_id"),
                building_id=tool_args.get("building_id"),
                venue_name=tool_args.get("venue_name"),
                description=tool_args.get("description"),
                target_audience=tool_args.get("target_audience", "ALL"),
                requires_approval=tool_args.get("requires_approval", True),
                club_id=tool_args.get("club_id"),
            )

        elif tool_name == "update_event_draft":
            return update_event_draft_data(
                db=db,
                user=user,
                event_id=tool_args["event_id"],
                title=tool_args.get("title"),
                description=tool_args.get("description"),
                start_time=tool_args.get("start_time"),
                end_time=tool_args.get("end_time"),
                room_id=tool_args.get("room_id"),
                venue_name=tool_args.get("venue_name"),
            )

        elif tool_name == "validate_event":
            return validate_event_data(
                db=db,
                user=user,
                room_id=tool_args["room_id"],
                start_time=tool_args["start_time"],
                end_time=tool_args["end_time"],
                exclude_event_id=tool_args.get("exclude_event_id"),
            )

        elif tool_name == "submit_event_for_approval":
            return submit_event_for_approval_data(
                db=db,
                user=user,
                event_id=tool_args["event_id"],
            )

        elif tool_name == "approve_event":
            return approve_event_data(
                db=db,
                user=user,
                event_id=tool_args["event_id"],
                notes=tool_args.get("notes"),
            )

        elif tool_name == "reject_event":
            return reject_event_data(
                db=db,
                user=user,
                event_id=tool_args["event_id"],
                reason=tool_args.get("reason"),
            )

        elif tool_name == "publish_event":
            return publish_event_data(
                db=db,
                user=user,
                event_id=tool_args["event_id"],
            )

        elif tool_name == "cancel_event":
            return cancel_event_data(
                db=db,
                user=user,
                event_id=tool_args["event_id"],
                reason=tool_args.get("reason"),
            )

        elif tool_name == "list_my_clubs":
            return list_my_clubs_data(db=db, user=user)

        elif tool_name == "list_club_activities":
            return list_club_activities_data(
                db=db,
                user=user,
                club_id=tool_args.get("club_id"),
                club_name=tool_args.get("club_name"),
            )

        elif tool_name == "create_club_activity":
            return create_club_activity_data(
                db=db,
                user=user,
                club_id=tool_args["club_id"],
                title=tool_args["title"],
                category=tool_args.get("category", "CLUB_ACTIVITY"),
                start_time=tool_args["start_time"],
                end_time=tool_args["end_time"],
                room_id=tool_args.get("room_id"),
                venue_name=tool_args.get("venue_name"),
                description=tool_args.get("description"),
                requires_approval=tool_args.get("requires_approval", True),
            )

        elif tool_name == "update_club_activity":
            return update_club_activity_data(
                db=db,
                user=user,
                event_id=tool_args["event_id"],
                title=tool_args.get("title"),
                description=tool_args.get("description"),
                start_time=tool_args.get("start_time"),
                end_time=tool_args.get("end_time"),
                room_id=tool_args.get("room_id"),
                venue_name=tool_args.get("venue_name"),
            )

        # -------------------------------------------------------------------
        # Faculty Substitution Tools Dispatch
        # -------------------------------------------------------------------
        elif tool_name == "list_my_substitution_requests":
            return list_my_substitution_requests_data(db=db, user=user)

        elif tool_name == "list_my_substitution_assignments":
            return list_my_substitution_assignments_data(db=db, user=user)

        elif tool_name == "list_pending_substitutions":
            return list_pending_substitutions_data(db=db, user=user)

        elif tool_name == "get_date_substitutions":
            return get_date_substitutions_data(
                db=db,
                user=user,
                date=tool_args.get("date"),
            )

        # -------------------------------------------------------------------
        # CDC Placement Tools Dispatch
        # -------------------------------------------------------------------
        elif tool_name == "list_published_placement_drives":
            return list_published_placement_drives_data(
                db=db,
                user=user,
                job_type=tool_args.get("job_type"),
                tier=tool_args.get("tier"),
                search=tool_args.get("search"),
            )

        elif tool_name == "list_my_eligible_drives":
            return list_my_eligible_drives_data(db=db, user=user)

        elif tool_name == "get_placement_drive_details":
            return get_placement_drive_details_data(
                db=db,
                user=user,
                drive_id=tool_args.get("drive_id"),
                company_name=tool_args.get("company_name"),
                title=tool_args.get("title"),
            )

        elif tool_name == "get_drive_deadlines_and_schedule":
            return get_drive_deadlines_and_schedule_data(
                db=db,
                user=user,
                company_name=tool_args.get("company_name"),
            )

        elif tool_name == "get_student_drive_eligibility":
            return get_student_drive_eligibility_data(
                db=db,
                user=user,
                drive_id=tool_args.get("drive_id"),
                company_name=tool_args.get("company_name"),
            )

        elif tool_name == "create_placement_drive_draft":
            return create_placement_drive_draft_data(
                db=db,
                user=user,
                company_name=tool_args["company_name"],
                title=tool_args["title"],
                job_role=tool_args["job_role"],
                application_deadline=tool_args["application_deadline"],
                job_type=tool_args.get("job_type", "FULL_TIME"),
                work_location=tool_args.get("work_location"),
                compensation_details=tool_args.get("compensation_details"),
                min_cgpa=tool_args.get("min_cgpa"),
                graduation_year=tool_args.get("graduation_year"),
                max_active_backlogs=tool_args.get("max_active_backlogs"),
                eligible_department_ids=tool_args.get("eligible_department_ids"),
                additional_criteria=tool_args.get("additional_criteria"),
            )

        elif tool_name == "validate_placement_drive":
            return validate_placement_drive_data(
                db=db,
                user=user,
                drive_id=tool_args["drive_id"],
            )

        elif tool_name == "publish_placement_drive":
            return publish_placement_drive_data(
                db=db,
                user=user,
                drive_id=tool_args["drive_id"],
            )

        elif tool_name == "update_placement_drive":
            return update_placement_drive_data(
                db=db,
                user=user,
                drive_id=tool_args["drive_id"],
                compensation_details=tool_args.get("compensation_details"),
                application_deadline=tool_args.get("application_deadline"),
                work_location=tool_args.get("work_location"),
                additional_criteria=tool_args.get("additional_criteria"),
                version=tool_args.get("version"),
            )

        elif tool_name == "cancel_placement_drive":
            return cancel_placement_drive_data(
                db=db,
                user=user,
                drive_id=tool_args["drive_id"],
                reason=tool_args["reason"],
            )

        else:
            return {"error": f"No implementation for tool '{tool_name}'."}

    except Exception as exc:
        return {"error": f"Tool execution failed: {str(exc)}"}
