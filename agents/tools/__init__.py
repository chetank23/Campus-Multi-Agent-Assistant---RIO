"""
agents/tools package
--------------------
Unified tool registry for Query Agent with strict authorization and typed schemas.
"""

from typing import Any, Callable, Dict, List
from sqlalchemy.orm import Session

from backend.models.identity import User
from agents.tools.student_tools import get_student_timetable_data, get_class_status_data
from agents.tools.faculty_tools import get_faculty_schedule_data, get_faculty_profile_data
from agents.tools.campus_tools import (
    get_course_details_data,
    get_room_or_lab_details_data,
    get_academic_calendar_data,
    get_campus_room_inventory_data,
)
from agents.tools.department_tools import get_department_timetable_data

# Tool registry with documentation for LLM tool binding
QUERY_TOOL_DEFINITIONS = [
    {
        "name": "get_student_timetable",
        "description": "Retrieves the official published timetable for the authenticated student, with course codes, timings, rooms, and faculty names.",
        "parameters": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "description": "Optional day of the week to filter (e.g., MONDAY, TUESDAY). If omitted, returns the full week schedule.",
                }
            },
        },
        "allowed_roles": ["STUDENT", "ADMIN"],
    },
    {
        "name": "get_class_status",
        "description": "Evaluates real-time class status (UPCOMING, ONGOING, COMPLETED, CANCELLED, RESCHEDULED) based on current time and published schedule.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_faculty_schedule",
        "description": "Retrieves the published teaching schedule for the authenticated faculty member.",
        "parameters": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "description": "Optional day of the week to filter (e.g., MONDAY).",
                }
            },
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "get_faculty_profile",
        "description": "Looks up academic directory profile information (department, designation, specialization) for faculty members.",
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
        "name": "get_course_details",
        "description": "Looks up course catalog information, credits, and department by course code or title.",
        "parameters": {
            "type": "object",
            "properties": {
                "query_str": {
                    "type": "string",
                    "description": "Course code (e.g., 'CS101') or course title.",
                }
            },
            "required": ["query_str"],
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_room_or_lab_details",
        "description": "Looks up physical room or laboratory capacity, room type, and building location.",
        "parameters": {
            "type": "object",
            "properties": {
                "room_query": {
                    "type": "string",
                    "description": "Room number (e.g. '101', 'LAB-A') or facility name.",
                }
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
                "event_type": {
                    "type": "string",
                    "description": "Optional event type: 'HOLIDAY', 'EXAM', 'EVENT', 'WORKING_DAY', 'VACATION'.",
                }
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_department_timetable",
        "description": "Retrieves published schedule for an academic department. Restricted to ADMIN and assigned FACULTY.",
        "parameters": {
            "type": "object",
            "properties": {
                "day": {
                    "type": "string",
                    "description": "Optional day of the week to filter.",
                }
            },
        },
        "allowed_roles": ["FACULTY", "ADMIN"],
    },
    {
        "name": "get_campus_room_inventory",
        "description": (
            "Returns the total count of active campus rooms (classrooms, labs, seminar halls) "
            "broken down by room type. Use this when the user asks 'how many classrooms are there?', "
            "'how many labs does the campus have?', or similar inventory-count questions. "
            "NOTE: This does NOT determine which rooms are currently free or unoccupied — "
            "real-time availability requires a specific date/time query against the timetable."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "room_type": {
                    "type": "string",
                    "description": "Optional room type to filter: 'CLASSROOM', 'LAB', or 'SEMINAR_HALL'.",
                }
            },
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "resolve_academic_scope",
        "description": "Resolves natural-language text into a validated academic scope (Department, Program, Semester, Academic Year, Sections).",
        "parameters": {
            "type": "object",
            "properties": {
                "query_text": {
                    "type": "string",
                    "description": "The user's query text containing department, semester, or program references.",
                }
            },
            "required": ["query_text"],
        },
        "allowed_roles": ["ADMIN"],
    },
    {
        "name": "analyze_scheduling_readiness",
        "description": "Performs pre-flight data readiness analysis for a resolved academic scope before timetable generation.",
        "parameters": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "object",
                    "description": "The resolved generation scope dictionary.",
                }
            },
            "required": ["scope"],
        },
        "allowed_roles": ["ADMIN"],
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
        "parameters": {
            "type": "object",
            "properties": {},
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "get_booking_details",
        "description": "Retrieves details of a specific resource booking request with role privacy masking.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "integer"},
            },
            "required": ["booking_id"],
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "confirm_resource_proposal",
        "description": "Confirms an existing single-use resource booking proposal token and creates a PENDING reservation.",
        "parameters": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string"},
            },
            "required": ["proposal_id"],
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
    },
    {
        "name": "execute_cancel_booking",
        "description": "Cancels a resource booking request owned by the user or as Administrator.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "integer"},
            },
            "required": ["booking_id"],
        },
        "allowed_roles": ["STUDENT", "FACULTY", "ADMIN"],
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
        if tool_name == "get_student_timetable":
            return get_student_timetable_data(db=db, user=user, day=tool_args.get("day"))

        elif tool_name == "get_class_status":
            return get_class_status_data(db=db, user=user)

        elif tool_name == "get_faculty_schedule":
            return get_faculty_schedule_data(db=db, user=user, day=tool_args.get("day"))

        elif tool_name == "get_faculty_profile":
            return get_faculty_profile_data(
                db=db,
                viewer=user,
                search_query=tool_args.get("search_query", ""),
            )

        elif tool_name == "get_course_details":
            return get_course_details_data(
                db=db,
                query_str=tool_args.get("query_str", ""),
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

        elif tool_name == "get_department_timetable":
            return get_department_timetable_data(
                db=db,
                user=user,
                department_id=tool_args.get("department_id"),
                day=tool_args.get("day"),
            )

        elif tool_name == "get_campus_room_inventory":
            return get_campus_room_inventory_data(
                db=db,
                room_type=tool_args.get("room_type"),
            )

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

        elif tool_name == "discover_resources":
            from agents.tools.resource_tools import discover_resources_data
            return discover_resources_data(
                db=db,
                resource_type=tool_args.get("resource_type"),
                min_capacity=tool_args.get("min_capacity"),
                location_query=tool_args.get("location_query"),
                search_query=tool_args.get("search_query"),
            )

        elif tool_name == "check_resource_availability":
            from agents.tools.resource_tools import check_resource_availability_data
            import datetime
            d = datetime.date.fromisoformat(tool_args["date"]) if isinstance(tool_args.get("date"), str) else tool_args.get("date")
            st = datetime.time.fromisoformat(tool_args["start_time"]) if isinstance(tool_args.get("start_time"), str) else tool_args.get("start_time")
            et = datetime.time.fromisoformat(tool_args["end_time"]) if isinstance(tool_args.get("end_time"), str) else tool_args.get("end_time")
            return check_resource_availability_data(
                db=db,
                resource_id=tool_args["resource_id"],
                date=d,
                start_time=st,
                end_time=et,
            )

        elif tool_name == "get_user_bookings":
            from agents.tools.resource_tools import get_user_bookings_data
            return get_user_bookings_data(db=db, user=user)

        elif tool_name == "get_booking_details":
            from agents.tools.resource_tools import get_booking_details_data
            return get_booking_details_data(db=db, booking_id=tool_args["booking_id"], user=user)

        elif tool_name == "execute_cancel_booking":
            from agents.tools.resource_tools import execute_cancel_booking_data
            return execute_cancel_booking_data(db=db, booking_id=tool_args["booking_id"], user=user)

        else:
            return {"error": f"No implementation for tool '{tool_name}'."}

    except Exception as exc:
        return {"error": f"Tool execution failed: {str(exc)}"}
