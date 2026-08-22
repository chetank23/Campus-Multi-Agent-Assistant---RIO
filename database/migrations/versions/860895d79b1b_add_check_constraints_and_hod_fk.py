"""
Migration: add_check_constraints_and_hod_fk
---------------------------------------------
Adds all domain-value CHECK constraints (role IN, course_type IN, etc.)
and the circular FK departments.hod_id → users.id that Alembic autogenerate
did not emit in the initial migration.
"""

from alembic import op

revision = '860895d79b1b'
down_revision = 'abe81e2a81bc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Circular FK: departments.hod_id → users.id ──────────────────────────
    op.create_foreign_key(
        'fk_departments_hod_id',
        'departments', 'users',
        ['hod_id'], ['id'],
    )

    # ── CHECK: users.role ────────────────────────────────────────────────────
    op.create_check_constraint(
        'ck_users_role',
        'users',
        "role IN ('STUDENT','FACULTY','HOD','TIMETABLE_COORDINATOR','ADMIN')",
    )

    # ── CHECK: courses.course_type ───────────────────────────────────────────
    op.create_check_constraint(
        'ck_courses_course_type',
        'courses',
        "course_type IN ('THEORY','LAB','TUTORIAL','PROJECT','ELECTIVE')",
    )

    # ── CHECK: rooms.room_type ───────────────────────────────────────────────
    op.create_check_constraint(
        'ck_rooms_room_type',
        'rooms',
        "room_type IN ('CLASSROOM','LAB','SEMINAR_HALL','AUDITORIUM','MEETING_ROOM')",
    )

    # ── CHECK: time_slots.slot_type ──────────────────────────────────────────
    op.create_check_constraint(
        'ck_time_slots_slot_type',
        'time_slots',
        "slot_type IN ('CLASS','BREAK','LUNCH')",
    )

    # ── CHECK: faculty_availability.availability ─────────────────────────────
    op.create_check_constraint(
        'ck_fa_availability',
        'faculty_availability',
        "availability IN ('AVAILABLE','UNAVAILABLE','PREFERRED')",
    )

    # ── CHECK: academic_calendar.event_type ──────────────────────────────────
    op.create_check_constraint(
        'ck_ac_event_type',
        'academic_calendar',
        "event_type IN ('HOLIDAY','WORKING_DAY','EXAM','EVENT','VACATION')",
    )

    # ── CHECK: timetable_version.status ──────────────────────────────────────
    op.create_check_constraint(
        'ck_tv_status',
        'timetable_version',
        "status IN ('DRAFT','GENERATED','HOD_REVIEW','HOD_APPROVED',"
        "'COORDINATOR_REVIEW','ADMIN_REVIEW','APPROVED','PUBLISHED',"
        "'REJECTED','ARCHIVED')",
    )

    # ── CHECK: resources.resource_type ───────────────────────────────────────
    op.create_check_constraint(
        'ck_resources_resource_type',
        'resources',
        "resource_type IN ('LAB','SEMINAR_HALL','PROJECTOR','AUDITORIUM','EQUIPMENT')",
    )

    # ── CHECK: resource_bookings.status ──────────────────────────────────────
    op.create_check_constraint(
        'ck_rb_status',
        'resource_bookings',
        "status IN ('PENDING','APPROVED','REJECTED','CANCELLED')",
    )

    # ── CHECK: change_requests.request_type ──────────────────────────────────
    op.create_check_constraint(
        'ck_cr_request_type',
        'change_requests',
        "request_type IN ('TIMETABLE_CHANGE','RESOURCE_REQUEST',"
        "'FACULTY_AVAILABILITY_CHANGE','ROOM_CHANGE')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_cr_request_type',      'change_requests',    type_='check')
    op.drop_constraint('ck_rb_status',             'resource_bookings',  type_='check')
    op.drop_constraint('ck_resources_resource_type','resources',         type_='check')
    op.drop_constraint('ck_tv_status',             'timetable_version',  type_='check')
    op.drop_constraint('ck_ac_event_type',         'academic_calendar',  type_='check')
    op.drop_constraint('ck_fa_availability',       'faculty_availability',type_='check')
    op.drop_constraint('ck_time_slots_slot_type',  'time_slots',         type_='check')
    op.drop_constraint('ck_rooms_room_type',       'rooms',              type_='check')
    op.drop_constraint('ck_courses_course_type',   'courses',            type_='check')
    op.drop_constraint('ck_users_role',            'users',              type_='check')
    op.drop_constraint('fk_departments_hod_id',    'departments',        type_='foreignkey')
