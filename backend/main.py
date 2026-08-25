from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError

from backend.routes import (
    buildings, rooms, labs, auth, department, program, academic_year, semester, section, batch, student,
    faculty, course, course_assignment, elective_group, elective_group_course,
    time_slot, faculty_availability, academic_calendar
)

app = FastAPI(title="Campus AI System")

@app.exception_handler(IntegrityError)
async def sqlalchemy_integrity_error_handler(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Database integrity error: check constraint or foreign key violation.",
            "error": str(exc.orig) if hasattr(exc, "orig") else str(exc)
        }
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
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
app.include_router(faculty.router)
app.include_router(course.router)
app.include_router(course_assignment.router)
app.include_router(elective_group.router)
app.include_router(elective_group_course.router)
app.include_router(time_slot.router)
app.include_router(faculty_availability.router)
app.include_router(academic_calendar.router)