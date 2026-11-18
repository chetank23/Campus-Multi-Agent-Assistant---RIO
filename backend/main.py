import email_validator
setattr(email_validator, "TEST_ENVIRONMENT", True)
from contextlib import asynccontextmanager
import logging
import os
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger("backend.main")

from backend.routes import (
    academic_calendar,
    academic_year,
    analytics,
    auth,
    audit_logs,
    batch,
    buildings,
    chat,
    change_requests,
    clubs,
    curriculum,
    course,
    course_assignment,
    data_import,
    department,
    disruptions,
    elective_group,
    elective_group_course,
    events,
    faculty,
    faculty_availability,
    labs,
    notifications,
    placements,
    program,
    resources,
    rooms,
    section,
    semester,
    settings,
    student,
    substitutions,
    time_slot,
    timetable,
    users,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing RIO-MJP backend services...")
    try:
        from agents.llm.nvidia_provider import NvidiaNemotronProvider
        NvidiaNemotronProvider.initialize_client()
    except Exception as exc:
        logger.warning("NvidiaNemotronProvider initialization skipped: %s", exc)
    yield
    logger.info("Shutting down RIO-MJP backend services...")
    try:
        from agents.llm.nvidia_provider import NvidiaNemotronProvider
        NvidiaNemotronProvider.close_client()
    except Exception as exc:
        logger.warning("NvidiaNemotronProvider cleanup error: %s", exc)


app = FastAPI(title="Campus AI System", lifespan=lifespan)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    req_id = (
        request.headers.get("X-Request-ID")
        or request.headers.get("X-Correlation-ID")
        or f"req-{uuid.uuid4().hex[:16]}"
    )
    request.state.request_id = req_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


@app.get("/health", tags=["system"])
def health_check():
    """Liveness & readiness probe for cloud hosting and monitoring."""
    return {"status": "ok", "service": "rio-mjp-backend"}


@app.exception_handler(IntegrityError)
async def sqlalchemy_integrity_error_handler(request: Request, exc: IntegrityError):
    req_id = (
        getattr(request.state, "request_id", None)
        or request.headers.get("X-Request-ID")
        or f"req-{uuid.uuid4().hex[:16]}"
    )
    orig_msg = str(exc.orig) if hasattr(exc, "orig") else str(exc)

    # Detailed server-side structured logging for auditing & diagnostics
    logger.error(
        "Database integrity error: request_id=%s method=%s path=%s client=%s exception=%s detail=%s",
        req_id,
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
        type(exc).__name__,
        orig_msg,
        exc_info=True,
    )

    # Client-facing response: strictly sanitized, no driver details, no raw SQL
    return JSONResponse(
        status_code=422,
        headers={"X-Request-ID": req_id},
        content={
            "detail": "Database integrity error: check constraint or foreign key violation.",
            "error_code": "INTEGRITY_ERROR",
            "request_id": req_id,
        },
    )

# Determine CORS allowed origins:
# In staging/production, configure ALLOWED_ORIGINS as comma-separated origins.
# If unconfigured, default to standard local frontend development origins.
_allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "").strip()
if _allowed_origins_env:
    allowed_origins = [origin.strip() for origin in _allowed_origins_env.split(",") if origin.strip()]
else:
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(audit_logs.router)
app.include_router(change_requests.router)
app.include_router(buildings.router)
app.include_router(rooms.router)
app.include_router(labs.router)
app.include_router(department.router)
app.include_router(program.router)
app.include_router(academic_year.router)
app.include_router(semester.router)
app.include_router(section.router)
app.include_router(batch.router)
app.include_router(student.router)
app.include_router(student.student_router)
app.include_router(clubs.router)
app.include_router(events.router)
app.include_router(placements.router)
app.include_router(substitutions.router)
app.include_router(faculty.router)
app.include_router(course.router)
app.include_router(course_assignment.router)
app.include_router(elective_group.router)
app.include_router(elective_group_course.router)
app.include_router(time_slot.router)
app.include_router(faculty_availability.router)
app.include_router(academic_calendar.router)
app.include_router(timetable.router)
app.include_router(resources.router)
app.include_router(chat.router)
app.include_router(notifications.router)
app.include_router(disruptions.router)
app.include_router(users.router)
app.include_router(analytics.router)
app.include_router(data_import.router)
app.include_router(curriculum.router)
app.include_router(curriculum.super_admin_router)
app.include_router(curriculum.admin_curriculum_router)
app.include_router(settings.router)

