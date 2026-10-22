"""
agents/action_registry/registry.py
-----------------------------------
Authoritative action registry for RIO Campus Assistant.
Enforces typed discoverability, permitted role validation, backend service attribution,
and explicit confirmation contracts.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple
from agents.action_registry.schemas import ActionDefinition, ActionParameter


class ActionRegistry:
    """
    Central repository of all operations the RIO Campus Assistant is authorized to execute.
    The assistant must NEVER execute an operation not registered here.
    """

    def __init__(self) -> None:
        self._actions: Dict[str, ActionDefinition] = {}
        self._register_default_actions()

    def register(self, action: ActionDefinition) -> None:
        self._actions[action.name] = action

    def get_action(self, name: str) -> Optional[ActionDefinition]:
        return self._actions.get(name)

    def get_actions(self) -> List[ActionDefinition]:
        return list(self._actions.values())

    def is_supported(self, name: str) -> bool:
        return name in self._actions

    def list_actions(
        self,
        role: Optional[str] = None,
        category: Optional[Literal["READ", "WRITE"]] = None,
    ) -> List[ActionDefinition]:
        results: List[ActionDefinition] = []
        for a in self._actions.values():
            if role and role not in a.permitted_roles:
                continue
            if category and a.category != category:
                continue
            results.append(a)
        return results

    def get_actions_for_role(self, role: str) -> List[ActionDefinition]:
        return self.list_actions(role=role)

    def validate_action_call(
        self,
        name: str,
        role: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates whether the requested action is registered, authorized for the given role,
        and has all required parameters present.
        """
        action = self._actions.get(name)
        if not action:
            return False, f"Action '{name}' is not recognized or supported by the Campus Assistant."

        if role not in action.permitted_roles:
            return (
                False,
                f"Access denied: Action '{name}' requires privilege level ({', '.join(action.permitted_roles)}). "
                f"Your current role is '{role}'.",
            )

        if params is not None:
            for p in action.parameters:
                if p.required and p.name not in params:
                    return False, f"Action '{name}' is missing mandatory parameter '{p.name}' ({p.description})."

        return True, None

    def _register_default_actions(self) -> None:
        # ──────────────────────────────────────────────────────────────────────
        # READ ACTIONS (Information Retrieval - No Confirmation Required)
        # ──────────────────────────────────────────────────────────────────────
        self.register(
            ActionDefinition(
                name="GET_STUDENT_TIMETABLE",
                category="READ",
                purpose="Retrieve official published timetable for authenticated student, including course codes, timings, rooms, and faculty names.",
                parameters=[
                    ActionParameter(name="day", param_type="str", description="Optional day of week filter (e.g. MONDAY)", required=False),
                ],
                permitted_roles=["STUDENT", "ADMIN"],
                authoritative_service="agents.tools.student_tools.get_student_timetable_data",
                validation_rules=["User must be authenticated student or admin", "Day must be valid weekday if provided"],
                requires_confirmation=False,
                expected_result="List of timetable entries grouped by day or for specific day.",
                failure_conditions=["Student enrollment not found", "No published timetable active for student section"],
            )
        )

        self.register(
            ActionDefinition(
                name="GET_FACULTY_SCHEDULE",
                category="READ",
                purpose="Retrieve published teaching schedule for authenticated faculty member.",
                parameters=[
                    ActionParameter(name="day", param_type="str", description="Optional day of week filter (e.g. MONDAY)", required=False),
                ],
                permitted_roles=["FACULTY", "ADMIN"],
                authoritative_service="agents.tools.faculty_tools.get_faculty_schedule_data",
                validation_rules=["User must be authenticated faculty or admin"],
                requires_confirmation=False,
                expected_result="List of assigned teaching slots, sections, and rooms.",
                failure_conditions=["Faculty profile not found", "No published timetable active"],
            )
        )

        self.register(
            ActionDefinition(
                name="GET_DEPARTMENT_TIMETABLE",
                category="READ",
                purpose="Retrieve published department-wide timetable entries.",
                parameters=[
                    ActionParameter(name="day", param_type="str", description="Optional day of week filter", required=False),
                ],
                permitted_roles=["STUDENT", "FACULTY", "ADMIN"],
                authoritative_service="agents.tools.department_tools.get_department_timetable_data",
                validation_rules=["User must have assigned department or provide department filter"],
                requires_confirmation=False,
                expected_result="Department class schedules with courses and sections.",
                failure_conditions=["Department not found", "No published timetable entries for department"],
            )
        )

        self.register(
            ActionDefinition(
                name="GET_CLASS_STATUS",
                category="READ",
                purpose="Evaluate real-time class status (upcoming, ongoing, completed) based on current clock and published schedule.",
                parameters=[],
                permitted_roles=["STUDENT", "FACULTY", "ADMIN"],
                authoritative_service="agents.tools.student_tools.get_class_status_data",
                validation_rules=["User must be authenticated"],
                requires_confirmation=False,
                expected_result="Current ongoing lecture, countdown to next lecture, and room location.",
                failure_conditions=["No active classes scheduled today"],
            )
        )

        self.register(
            ActionDefinition(
                name="GET_FACULTY_PROFILE",
                category="READ",
                purpose="Lookup academic directory profile for faculty members.",
                parameters=[
                    ActionParameter(name="search_query", param_type="str", description="Faculty name, designation, or specialization", required=True),
                ],
                permitted_roles=["STUDENT", "FACULTY", "ADMIN"],
                authoritative_service="agents.tools.faculty_tools.get_faculty_profile_data",
                validation_rules=["Search query must be non-empty"],
                requires_confirmation=False,
                expected_result="Faculty designation, department, contact, and office details.",
                failure_conditions=["No faculty member matching query"],
            )
        )

        self.register(
            ActionDefinition(
                name="GET_COURSE_DETAILS",
                category="READ",
                purpose="Lookup course catalog information, credits, syllabus, and department.",
                parameters=[
                    ActionParameter(name="query_str", param_type="str", description="Course code or subject title", required=True),
                ],
                permitted_roles=["STUDENT", "FACULTY", "ADMIN"],
                authoritative_service="agents.tools.campus_tools.get_course_details_data",
                validation_rules=["Course query must be non-empty"],
                requires_confirmation=False,
                expected_result="Course code, name, credits, theory hours, lab hours.",
                failure_conditions=["Course code or title not found"],
            )
        )

        self.register(
            ActionDefinition(
                name="GET_ROOM_DETAILS",
                category="READ",
                purpose="Lookup physical room/lab capacity, room type, and building location.",
                parameters=[
                    ActionParameter(name="room_query", param_type="str", description="Room number or facility name", required=True),
                ],
                permitted_roles=["STUDENT", "FACULTY", "ADMIN"],
                authoritative_service="agents.tools.campus_tools.get_room_or_lab_details_data",
                validation_rules=["Room query must be non-empty"],
                requires_confirmation=False,
                expected_result="Room number, building, floor, capacity, and room type.",
                failure_conditions=["Room not found in space inventory"],
            )
        )

        self.register(
            ActionDefinition(
                name="GET_CAMPUS_ROOM_INVENTORY",
                category="READ",
                purpose="Retrieve campus classroom and lab counts by room type.",
                parameters=[
                    ActionParameter(name="room_type", param_type="str", description="Room type filter (CLASSROOM, LAB, SEMINAR_HALL)", required=False),
                ],
                permitted_roles=["STUDENT", "FACULTY", "ADMIN"],
                authoritative_service="agents.tools.campus_tools.get_campus_room_inventory_data",
                validation_rules=["Room type must be valid if specified"],
                requires_confirmation=False,
                expected_result="Count and list of campus rooms grouped by type.",
                failure_conditions=["No active rooms registered"],
            )
        )

        self.register(
            ActionDefinition(
                name="GET_ACADEMIC_CALENDAR",
                category="READ",
                purpose="Retrieve university academic calendar events, holidays, and exam schedules.",
                parameters=[
                    ActionParameter(name="event_type", param_type="str", description="Optional filter (HOLIDAY, EXAM, EVENT)", required=False),
                ],
                permitted_roles=["STUDENT", "FACULTY", "ADMIN"],
                authoritative_service="agents.tools.campus_tools.get_academic_calendar_data",
                validation_rules=["User must be authenticated"],
                requires_confirmation=False,
                expected_result="Chronological list of university academic calendar milestones.",
                failure_conditions=["No calendar events recorded"],
            )
        )

        self.register(
            ActionDefinition(
                name="DISCOVER_RESOURCES",
                category="READ",
                purpose="Search campus facilities and equipment with capacity and active lock indicators.",
                parameters=[
                    ActionParameter(name="resource_type", param_type="str", description="Resource type (LAB, SEMINAR_HALL, AUDITORIUM, EQUIPMENT)", required=False),
                    ActionParameter(name="min_capacity", param_type="int", description="Minimum seating capacity", required=False),
                    ActionParameter(name="search_query", param_type="str", description="Search term for name or location", required=False),
                ],
                permitted_roles=["STUDENT", "FACULTY", "ADMIN"],
                authoritative_service="agents.tools.resource_tools.discover_resources_data",
                validation_rules=["User must be authenticated"],
                requires_confirmation=False,
                expected_result="Matching facilities with location, capacity, and lock status.",
                failure_conditions=["No matching resources found"],
            )
        )

        self.register(
            ActionDefinition(
                name="CHECK_RESOURCE_AVAILABILITY",
                category="READ",
                purpose="Perform authoritative interval conflict detection for a facility against approved bookings and timetable classes.",
                parameters=[
                    ActionParameter(name="resource_id", param_type="int", description="Database identifier of resource", required=True),
                    ActionParameter(name="date", param_type="date", description="Target reservation date", required=True),
                    ActionParameter(name="start_time", param_type="time", description="Slot start time", required=True),
                    ActionParameter(name="end_time", param_type="time", description="Slot end time", required=True),
                ],
                permitted_roles=["STUDENT", "FACULTY", "ADMIN"],
                authoritative_service="backend.services.resource_booking_service.check_resource_conflicts",
                validation_rules=["Resource must exist and be ACTIVE", "Start time must precede end time", "Global lock check"],
                requires_confirmation=False,
                expected_result="Availability confirmation or detailed conflict description with alternatives.",
                failure_conditions=["Resource not found", "Interval invalid"],
            )
        )

        self.register(
            ActionDefinition(
                name="GET_USER_BOOKINGS",
                category="READ",
                purpose="List resource bookings for the user or campus-wide pending bookings for Admin.",
                parameters=[
                    ActionParameter(name="status_filter", param_type="str", description="Optional filter (PENDING, APPROVED, REJECTED, CANCELLED)", required=False),
                ],
                permitted_roles=["STUDENT", "FACULTY", "ADMIN"],
                authoritative_service="agents.tools.resource_tools.get_user_bookings_data",
                validation_rules=["User must be authenticated", "Non-admins may only view their own bookings"],
                requires_confirmation=False,
                expected_result="List of bookings with IDs, dates, timings, and status.",
                failure_conditions=["No bookings found matching filters"],
            )
        )

        self.register(
            ActionDefinition(
                name="GET_BOOKING_DETAILS",
                category="READ",
                purpose="Lookup specific booking details with role-based privacy masking.",
                parameters=[
                    ActionParameter(name="booking_id", param_type="int", description="Booking primary key ID", required=True),
                ],
                permitted_roles=["STUDENT", "FACULTY", "ADMIN"],
                authoritative_service="agents.tools.resource_tools.get_booking_details_data",
                validation_rules=["User must be admin, requester, or booking must be approved"],
                requires_confirmation=False,
                expected_result="Booking dates, times, facility, requester, and approver info.",
                failure_conditions=["Booking not found", "Access denied by privacy guard"],
            )
        )

        self.register(
            ActionDefinition(
                name="CHECK_TIMETABLE_READINESS",
                category="READ",
                purpose="Pre-flight academic scope validation before solver execution without generating proposals or tokens.",
                parameters=[
                    ActionParameter(name="department_id", param_type="int", description="Department ID", required=True),
                    ActionParameter(name="semester_id", param_type="int", description="Semester number", required=True),
                    ActionParameter(name="academic_year_id", param_type="int", description="Academic Year ID", required=True),
                    ActionParameter(name="program_id", param_type="int", description="Degree Program ID", required=True),
                ],
                permitted_roles=["ADMIN"],
                authoritative_service="agents.tools.scheduling_tools.analyze_scheduling_readiness_data",
                validation_rules=["User must have ADMIN role", "Academic scope parameters must resolve to valid database records"],
                requires_confirmation=False,
                expected_result="Readiness status (READY, READY_WITH_WARNINGS, BLOCKED) with detailed prerequisite checks.",
                failure_conditions=["Scope parameters invalid or incomplete", "Access denied for non-admin"],
            )
        )

        self.register(
            ActionDefinition(
                name="COMPARE_SCHEDULING_STRATEGIES",
                category="READ",
                purpose="Advisory comparison of optimization solver strategies (BALANCED, FACULTY_COMFORT, ROOM_EFFICIENCY, LAB_PREFERENCE).",
                parameters=[],
                permitted_roles=["ADMIN"],
                authoritative_service="agents.scheduling_agent.agent.run_scheduling_agent",
                validation_rules=["User must have ADMIN role"],
                requires_confirmation=False,
                expected_result="Breakdown of objective trade-offs and constraint penalty weights.",
                failure_conditions=["Access denied for non-admin"],
            )
        )

        self.register(
            ActionDefinition(
                name="GET_TIMETABLE_VERSIONS",
                category="READ",
                purpose="List generated, validated, finalized, and published timetable versions.",
                parameters=[
                    ActionParameter(name="academic_year_id", param_type="int", description="Optional academic year filter", required=False),
                ],
                permitted_roles=["ADMIN"],
                authoritative_service="backend.routes.timetable.get_versions",
                validation_rules=["User must have ADMIN role"],
                requires_confirmation=False,
                expected_result="List of timetable versions with version number and status.",
                failure_conditions=["Access denied for non-admin"],
            )
        )

        # ──────────────────────────────────────────────────────────────────────
        # WRITE ACTIONS (Mutations - Require Explicit Confirmation)
        # ──────────────────────────────────────────────────────────────────────
        self.register(
            ActionDefinition(
                name="CREATE_RESOURCE_BOOKING",
                category="WRITE",
                purpose="Request a facility or equipment reservation in PENDING status.",
                parameters=[
                    ActionParameter(name="resource_id", param_type="int", description="Resource ID", required=True),
                    ActionParameter(name="date", param_type="date", description="Reservation date", required=True),
                    ActionParameter(name="start_time", param_type="time", description="Start time", required=True),
                    ActionParameter(name="end_time", param_type="time", description="End time", required=True),
                    ActionParameter(name="purpose", param_type="str", description="Purpose of reservation", required=True),
                ],
                permitted_roles=["STUDENT", "FACULTY", "ADMIN"],
                authoritative_service="backend.services.resource_booking_service.create_booking_request",
                validation_rules=[
                    "Resource must be ACTIVE",
                    "Start time must precede end time",
                    "No conflict with approved bookings or published timetables",
                    "No active booking lock",
                ],
                requires_confirmation=True,
                expected_result="ResourceBooking persisted in PENDING status with unique booking ID.",
                failure_conditions=["Conflict detected", "Parent resource row locked", "Database constraint violation"],
            )
        )

        self.register(
            ActionDefinition(
                name="APPROVE_RESOURCE_BOOKING",
                category="WRITE",
                purpose="Approve a PENDING resource booking request and lock the facility.",
                parameters=[
                    ActionParameter(name="booking_id", param_type="int", description="Booking ID to approve", required=True),
                ],
                permitted_roles=["ADMIN"],
                authoritative_service="backend.services.resource_booking_service.approve_booking_request",
                validation_rules=[
                    "Caller must be ADMIN",
                    "Booking must exist and be PENDING",
                    "Atomic re-check of interval conflicts under parent resource lock",
                ],
                requires_confirmation=True,
                expected_result="ResourceBooking status transitioned to APPROVED with approver_id and audit log recorded.",
                failure_conditions=["Booking not found", "Booking not PENDING", "Conflicting reservation confirmed in the interim"],
            )
        )

        self.register(
            ActionDefinition(
                name="REJECT_RESOURCE_BOOKING",
                category="WRITE",
                purpose="Reject a PENDING resource booking request.",
                parameters=[
                    ActionParameter(name="booking_id", param_type="int", description="Booking ID to reject", required=True),
                    ActionParameter(name="reason", param_type="str", description="Rejection rationale", required=False),
                ],
                permitted_roles=["ADMIN"],
                authoritative_service="backend.services.resource_booking_service.reject_booking_request",
                validation_rules=["Caller must be ADMIN", "Booking must exist and be PENDING"],
                requires_confirmation=True,
                expected_result="ResourceBooking status transitioned to REJECTED with audit log recorded.",
                failure_conditions=["Booking not found", "Booking not PENDING"],
            )
        )

        self.register(
            ActionDefinition(
                name="CANCEL_RESOURCE_BOOKING",
                category="WRITE",
                purpose="Cancel an existing resource booking request and release the facility reservation.",
                parameters=[
                    ActionParameter(name="booking_id", param_type="int", description="Booking ID to cancel", required=True),
                    ActionParameter(name="reason", param_type="str", description="Cancellation reason", required=False),
                ],
                permitted_roles=["STUDENT", "FACULTY", "ADMIN"],
                authoritative_service="backend.services.resource_booking_service.cancel_booking_request",
                validation_rules=[
                    "Caller must be original requester or ADMIN",
                    "Booking status must be PENDING or APPROVED",
                ],
                requires_confirmation=True,
                expected_result="ResourceBooking status transitioned to CANCELLED and facility unlocked.",
                failure_conditions=["Booking not found", "Access denied", "Booking already completed or cancelled"],
            )
        )

        self.register(
            ActionDefinition(
                name="GENERATE_TIMETABLE",
                category="WRITE",
                purpose="Run the Google OR-Tools CP-SAT solver to generate and persist a new draft timetable version.",
                parameters=[
                    ActionParameter(name="scope", param_type="dict", description="Academic scope (dept, semester, year, program)", required=True),
                    ActionParameter(name="strategy", param_type="str", description="Strategy profile (BALANCED, FACULTY_COMFORT, etc.)", required=False),
                ],
                permitted_roles=["ADMIN"],
                authoritative_service="backend.services.timetable_service.execute_timetable_generation",
                validation_rules=[
                    "Caller must be ADMIN",
                    "All prerequisite academic records must be ready",
                    "Solver finds feasible solution",
                ],
                requires_confirmation=True,
                expected_result="TimetableVersion created in GENERATED/DRAFT status with persisted entries and quality score.",
                failure_conditions=["Prerequisites blocked", "Solver infeasible", "Scope invalid"],
            )
        )

        self.register(
            ActionDefinition(
                name="FINALIZE_TIMETABLE",
                category="WRITE",
                purpose="Finalize a validated timetable version to lock it against further manual edits.",
                parameters=[
                    ActionParameter(name="version_id", param_type="int", description="TimetableVersion ID", required=True),
                ],
                permitted_roles=["ADMIN"],
                authoritative_service="backend.routes.timetable.finalize_version",
                validation_rules=[
                    "Caller must be ADMIN",
                    "Version must exist",
                    "Version status must be VALIDATED",
                ],
                requires_confirmation=True,
                expected_result="TimetableVersion status transitioned to FINALIZED with audit log.",
                failure_conditions=["Version not found", "Version not VALIDATED", "Database error"],
            )
        )

        self.register(
            ActionDefinition(
                name="PUBLISH_TIMETABLE",
                category="WRITE",
                purpose="Publish a finalized timetable version as the campus-wide official schedule.",
                parameters=[
                    ActionParameter(name="version_id", param_type="int", description="TimetableVersion ID", required=True),
                ],
                permitted_roles=["ADMIN"],
                authoritative_service="backend.routes.timetable.publish_version",
                validation_rules=[
                    "Caller must be ADMIN",
                    "Version must exist",
                    "Version status must be FINALIZED",
                ],
                requires_confirmation=True,
                expected_result="TimetableVersion status transitioned to PUBLISHED with published_at timestamp and audit log.",
                failure_conditions=["Version not found", "Version not FINALIZED", "Database error"],
            )
        )

        self.register(
            ActionDefinition(
                name="UPDATE_ROOM",
                category="WRITE",
                purpose="Update physical room metadata (capacity, room type) in the facilities register.",
                parameters=[
                    ActionParameter(name="room_id", param_type="int", description="Room ID", required=True),
                    ActionParameter(name="capacity", param_type="int", description="New seating capacity", required=False),
                    ActionParameter(name="room_type", param_type="str", description="New room type", required=False),
                ],
                permitted_roles=["ADMIN"],
                authoritative_service="backend.routes.rooms.update_room",
                validation_rules=[
                    "Caller must be ADMIN",
                    "Room must exist",
                    "Capacity must be positive integer",
                ],
                requires_confirmation=True,
                expected_result="Room metadata updated and persisted in space_time register.",
                failure_conditions=["Room not found", "Invalid capacity", "Access denied"],
            )
        )


# Singleton action registry
action_registry = ActionRegistry()
