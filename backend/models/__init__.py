"""
backend/models/__init__.py
--------------------------
Imports all ORM models so that:
  1. Alembic's env.py can import `target_metadata` and see every table.
  2. Application code can do `from backend.models import User, Faculty, ...`

Import order matters: Base → identity/academic (circular FK pair) → rest.
"""

from .base import Base  # noqa: F401

# Identity first — users table referenced by almost everything
from .identity import User  # noqa: F401

# Academic structure — departments references users (use_alter FK)
from .academic import (  # noqa: F401
    AcademicYear,
    Batch,
    Department,
    Faculty,
    Program,
    Section,
    Semester,
    Student,
)

# Courses
from .courses import (  # noqa: F401
    Course,
    CourseAssignment,
    ElectiveGroup,
    ElectiveGroupCourse,
)

# Space & time
from .space_time import (  # noqa: F401
    AcademicCalendar,
    Building,
    FacultyAvailability,
    Lab,
    Room,
    TimeSlot,
)

# Timetable (includes composite indexes via __table_args__)
from .timetable import TimetableEntry, TimetableVersion  # noqa: F401

# Resources
from .resources import Resource, ResourceBooking  # noqa: F401

# Authentication security
from .auth_security import LoginRateLimit, RefreshSession  # noqa: F401

# Workflow
from .workflow import AgentProposal, AuditLog, ChangeRequest, Notification, NotificationOutbox  # noqa: F401

# AI Assistant Chat Persistence
from .chat import ChatConversation, ChatMessage  # noqa: F401

# Campus Events, Club & Activity Coordination
from .events import CoordinatorCapability, Club, CampusEvent  # noqa: F401

# CDC Placement Management
from .placements import PlacementDrive, PlacementSchedule, StudentAcademicRecord  # noqa: F401

# Expose the metadata object Alembic needs
metadata = Base.metadata

__all__ = [
    "Base",
    "metadata",
    "User",
    "Department",
    "Program",
    "AcademicYear",
    "Semester",
    "Section",
    "Batch",
    "Student",
    "Faculty",
    "Course",
    "CourseAssignment",
    "ElectiveGroup",
    "ElectiveGroupCourse",
    "Building",
    "Room",
    "Lab",
    "TimeSlot",
    "FacultyAvailability",
    "AcademicCalendar",
    "TimetableVersion",
    "TimetableEntry",
    "Resource",
    "ResourceBooking",
    "ChangeRequest",
    "Notification",
    "AuditLog",
    "AgentProposal",
    "RefreshSession",
    "LoginRateLimit",
    "NotificationOutbox",
    "ChatConversation",
    "ChatMessage",
    "CoordinatorCapability",
    "Club",
    "CampusEvent",
    "PlacementDrive",
    "PlacementSchedule",
    "StudentAcademicRecord",
]
