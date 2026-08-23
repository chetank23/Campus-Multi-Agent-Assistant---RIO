-- =============================================================================
-- campus_ai  —  Plain-SQL Reference Schema
-- Multi-Agent Campus Assistant & Automated Timetable Engine
-- =============================================================================
-- This file is the human-readable reference matching the SQLAlchemy 2.0 ORM
-- models in backend/models/. The Alembic migration in database/migrations/ is
-- the authoritative source of truth for DDL applied to the live database.
--
-- To recreate the schema from scratch on a clean database:
--   1. Create the database and user (see README.md §Stage 1)
--   2. Run:  alembic upgrade head
--
-- Stage 1 — no seed data. See database/seed.sql (Stage 2).
-- =============================================================================

-- ── USERS & IDENTITY ─────────────────────────────────────────────────────────
-- Note: departments is just a standard table. Circular FKs were removed in the
--       3-role model.

CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(150)    NOT NULL,
    email           VARCHAR(150)    UNIQUE NOT NULL,
    password_hash   TEXT            NOT NULL,
    role            VARCHAR(30)     NOT NULL
                        CHECK (role IN (
                            'STUDENT','FACULTY','ADMIN'
                        )),
    department_id   INTEGER         REFERENCES departments(id),   -- FK added below
    is_active       BOOLEAN         DEFAULT TRUE,
    created_at      TIMESTAMP       DEFAULT now()
);

-- ── ACADEMIC STRUCTURE ───────────────────────────────────────────────────────

CREATE TABLE departments (
    id                  SERIAL PRIMARY KEY,
    department_code     VARCHAR(20)     UNIQUE NOT NULL,
    name                VARCHAR(150)    NOT NULL
);

-- FK users.department_id → departments.id (added now that departments exists)
ALTER TABLE users
    ADD CONSTRAINT fk_users_department_id
    FOREIGN KEY (department_id) REFERENCES departments(id);

CREATE TABLE programs (
    id              SERIAL PRIMARY KEY,
    department_id   INTEGER     REFERENCES departments(id),
    program_name    VARCHAR(150),
    degree          VARCHAR(50),
    duration        INTEGER
);

CREATE TABLE academic_years (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(20),
    start_date  DATE,
    end_date    DATE
);

CREATE TABLE semesters (
    id                  SERIAL PRIMARY KEY,
    academic_year_id    INTEGER     REFERENCES academic_years(id),
    semester_number     INTEGER,
    start_date          DATE,
    end_date            DATE
);

CREATE TABLE sections (
    id              SERIAL PRIMARY KEY,
    department_id   INTEGER     REFERENCES departments(id),
    program_id      INTEGER     REFERENCES programs(id),
    semester_id     INTEGER     REFERENCES semesters(id),
    section_name    VARCHAR(10),
    student_count   INTEGER
);

CREATE TABLE batches (
    id              SERIAL PRIMARY KEY,
    section_id      INTEGER     REFERENCES sections(id),
    batch_name      VARCHAR(10),
    student_count   INTEGER
);

CREATE TABLE students (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER     REFERENCES users(id),
    student_id      VARCHAR(30) UNIQUE,
    department_id   INTEGER     REFERENCES departments(id),
    program_id      INTEGER     REFERENCES programs(id),
    semester_id     INTEGER     REFERENCES semesters(id),
    section_id      INTEGER     REFERENCES sections(id),
    batch_id        INTEGER     REFERENCES batches(id)
);

CREATE TABLE faculty (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER     REFERENCES users(id),
    faculty_id      VARCHAR(30) UNIQUE,
    department_id   INTEGER     REFERENCES departments(id),
    designation     VARCHAR(50),
    max_weekly_load INTEGER     DEFAULT 16
);

-- ── COURSES & ASSIGNMENTS ────────────────────────────────────────────────────

CREATE TABLE courses (
    id              SERIAL PRIMARY KEY,
    course_code     VARCHAR(20) UNIQUE,
    course_name     VARCHAR(150),
    department_id   INTEGER     REFERENCES departments(id),
    course_type     VARCHAR(20) CHECK (course_type IN (
                        'THEORY','LAB','TUTORIAL','PROJECT','ELECTIVE'
                    )),
    credits             INTEGER,
    lecture_hours       INTEGER,
    tutorial_hours      INTEGER,
    practical_hours     INTEGER,
    requires_lab        BOOLEAN     DEFAULT FALSE
);

CREATE TABLE course_assignments (
    id          SERIAL PRIMARY KEY,
    course_id   INTEGER     REFERENCES courses(id),
    faculty_id  INTEGER     REFERENCES faculty(id),
    section_id  INTEGER     REFERENCES sections(id),
    batch_id    INTEGER     REFERENCES batches(id)
);

CREATE TABLE elective_groups (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100),
    semester_id     INTEGER     REFERENCES semesters(id),
    department_id   INTEGER     REFERENCES departments(id)
);

CREATE TABLE elective_group_courses (
    id          SERIAL PRIMARY KEY,
    group_id    INTEGER     REFERENCES elective_groups(id),
    course_id   INTEGER     REFERENCES courses(id)
);

-- ── SPACE & TIME ─────────────────────────────────────────────────────────────

CREATE TABLE buildings (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(100),
    code                VARCHAR(20),
    location            VARCHAR(150),
    number_of_floors    INTEGER
);

CREATE TABLE rooms (
    id              SERIAL PRIMARY KEY,
    building_id     INTEGER     REFERENCES buildings(id),
    room_number     VARCHAR(20),
    floor_number    INTEGER,
    capacity        INTEGER,
    room_type       VARCHAR(20) CHECK (room_type IN (
                        'CLASSROOM','LAB','SEMINAR_HALL','AUDITORIUM','MEETING_ROOM'
                    )),
    department_id   INTEGER     REFERENCES departments(id),
    has_projector   BOOLEAN     DEFAULT FALSE,
    has_smart_board BOOLEAN     DEFAULT FALSE,
    status          VARCHAR(20) DEFAULT 'ACTIVE'
);

CREATE TABLE labs (
    id              SERIAL PRIMARY KEY,
    room_id         INTEGER     REFERENCES rooms(id),
    lab_name        VARCHAR(100),
    department_id   INTEGER     REFERENCES departments(id),
    computer_count  INTEGER,
    equipment       TEXT,
    software        TEXT
);

CREATE TABLE time_slots (
    id          SERIAL PRIMARY KEY,
    day         VARCHAR(10),
    start_time  TIME,
    end_time    TIME,
    slot_type   VARCHAR(10) CHECK (slot_type IN ('CLASS','BREAK','LUNCH'))
);

CREATE TABLE faculty_availability (
    id              SERIAL PRIMARY KEY,
    faculty_id      INTEGER     REFERENCES faculty(id),
    slot_id         INTEGER     REFERENCES time_slots(id),
    availability    VARCHAR(15) CHECK (availability IN (
                        'AVAILABLE','UNAVAILABLE','PREFERRED'
                    )),
    preference      INTEGER     DEFAULT 0
);

CREATE TABLE academic_calendar (
    id                  SERIAL PRIMARY KEY,
    academic_year_id    INTEGER     REFERENCES academic_years(id),
    date                DATE,
    event_type          VARCHAR(20) CHECK (event_type IN (
                            'HOLIDAY','WORKING_DAY','EXAM','EVENT','VACATION'
                        )),
    description         TEXT
);

-- ── TIMETABLE ────────────────────────────────────────────────────────────────

CREATE TABLE timetable_versions (
    id                  SERIAL PRIMARY KEY,
    academic_year_id    INTEGER     REFERENCES academic_years(id),
    version_number      VARCHAR(10),
    status              VARCHAR(20) CHECK (status IN (
                            'DRAFT','GENERATED','REVIEWED','VALIDATED',
                            'FINALIZED','PUBLISHED','REJECTED','ARCHIVED'
                        )),
    created_by          INTEGER     REFERENCES users(id),
    approved_by         INTEGER     REFERENCES users(id),
    created_at          TIMESTAMP   DEFAULT now(),
    published_at        TIMESTAMP,
    reason              TEXT
);

CREATE TABLE timetable_entries (
    id              SERIAL PRIMARY KEY,
    version_id      INTEGER     REFERENCES timetable_versions(id),
    department_id   INTEGER     REFERENCES departments(id),
    program_id      INTEGER     REFERENCES programs(id),
    semester_id     INTEGER     REFERENCES semesters(id),
    section_id      INTEGER     REFERENCES sections(id),
    batch_id        INTEGER     REFERENCES batches(id),
    course_id       INTEGER     REFERENCES courses(id),
    faculty_id      INTEGER     REFERENCES faculty(id),
    room_id         INTEGER     REFERENCES rooms(id),
    slot_id         INTEGER     REFERENCES time_slots(id),
    status          VARCHAR(20) DEFAULT 'DRAFT' CHECK (status IN (
                            'DRAFT','ACTIVE','CANCELLED','RESCHEDULED'
                        ))
);

-- Composite indexes for validator and solver performance (see blueprint §5.2)
CREATE INDEX ix_timetable_entries_faculty_slot  ON timetable_entries (faculty_id,  slot_id);
CREATE INDEX ix_timetable_entries_room_slot     ON timetable_entries (room_id,     slot_id);
CREATE INDEX ix_timetable_entries_section_slot  ON timetable_entries (section_id,  slot_id);

-- ── RESOURCES ────────────────────────────────────────────────────────────────

CREATE TABLE resources (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100),
    resource_type   VARCHAR(30) CHECK (resource_type IN (
                        'LAB','SEMINAR_HALL','PROJECTOR','AUDITORIUM','EQUIPMENT'
                    )),
    location        VARCHAR(150),
    capacity        INTEGER,
    status          VARCHAR(20) DEFAULT 'ACTIVE'
);

CREATE TABLE resource_bookings (
    id              SERIAL PRIMARY KEY,
    resource_id     INTEGER     REFERENCES resources(id),
    requested_by    INTEGER     REFERENCES users(id),
    date            DATE,
    start_time      TIME,
    end_time        TIME,
    purpose         TEXT,
    status          VARCHAR(20) CHECK (status IN (
                        'PENDING','APPROVED','REJECTED','CANCELLED'
                    )),
    approved_by     INTEGER     REFERENCES users(id)
);

-- ── WORKFLOW, NOTIFICATIONS, AUDIT ───────────────────────────────────────────

CREATE TABLE change_requests (
    id                  SERIAL PRIMARY KEY,
    requested_by        INTEGER     REFERENCES users(id),
    request_type        VARCHAR(30) CHECK (request_type IN (
                            'TIMETABLE_CHANGE','RESOURCE_REQUEST',
                            'FACULTY_AVAILABILITY_CHANGE','ROOM_CHANGE'
                        )),
    related_entity_id   INTEGER,
    reason              TEXT,
    status              VARCHAR(20) DEFAULT 'PENDING',
    reviewed_by         INTEGER     REFERENCES users(id),
    created_at          TIMESTAMP   DEFAULT now()
);

CREATE TABLE notifications (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER     REFERENCES users(id),
    title       VARCHAR(150),
    message     TEXT,
    type        VARCHAR(30),
    is_read     BOOLEAN     DEFAULT FALSE,
    created_at  TIMESTAMP   DEFAULT now()
);

CREATE TABLE audit_logs (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER     REFERENCES users(id),
    action          VARCHAR(150),
    entity_type     VARCHAR(50),
    entity_id       INTEGER,
    old_value       JSONB,
    new_value       JSONB,
    timestamp       TIMESTAMP   DEFAULT now()
);

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
