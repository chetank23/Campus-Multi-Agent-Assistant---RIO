from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from backend.database import get_db
from backend.models.space_time import AcademicCalendar
from backend.models.identity import User
from backend.schemas.academic_calendar import AcademicCalendarCreate, AcademicCalendarUpdate, AcademicCalendarResponse
from backend.dependencies import get_current_user

router = APIRouter(prefix="/academic-calendar", tags=["Academic Calendar"])

@router.get("", response_model=List[AcademicCalendarResponse])
@router.get("/", response_model=List[AcademicCalendarResponse], include_in_schema=False)
def get_academic_calendars(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(AcademicCalendar).order_by(AcademicCalendar.date.asc()).all()

@router.get("/{ac_id}", response_model=AcademicCalendarResponse)
def get_academic_calendar(
    ac_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ac = db.query(AcademicCalendar).filter(AcademicCalendar.id == ac_id).first()
    if not ac:
        raise HTTPException(status_code=404, detail="Academic calendar event not found")
    return ac

@router.post("", response_model=AcademicCalendarResponse)
@router.post("/", response_model=AcademicCalendarResponse, include_in_schema=False)
def create_academic_calendar(
    ac: AcademicCalendarCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_ac = AcademicCalendar(**ac.model_dump())
    db.add(db_ac)
    db.commit()
    db.refresh(db_ac)

    # Broadcast notification to campus
    from backend.services.notification_service import broadcast_announcement
    event_label = db_ac.description or db_ac.event_type or "Academic Event"
    broadcast_announcement(
        db=db,
        admin_user_id=current_user.id,
        title=f"Academic Calendar: {event_label}",
        message=f"New academic calendar event on {db_ac.date}: {event_label} ({db_ac.event_type}).",
        target_role="ALL",
    )

    return db_ac

@router.put("/{ac_id}", response_model=AcademicCalendarResponse)
def update_academic_calendar(
    ac_id: int,
    ac: AcademicCalendarUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_ac = db.query(AcademicCalendar).filter(AcademicCalendar.id == ac_id).first()
    if not db_ac:
        raise HTTPException(status_code=404, detail="Academic calendar event not found")
    for key, value in ac.model_dump(exclude_unset=True).items():
        setattr(db_ac, key, value)
    db.commit()
    db.refresh(db_ac)
    return db_ac

@router.delete("/{ac_id}")
def delete_academic_calendar(
    ac_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_ac = db.query(AcademicCalendar).filter(AcademicCalendar.id == ac_id).first()
    if not db_ac:
        raise HTTPException(status_code=404, detail="Academic calendar event not found")
    db.delete(db_ac)
    db.commit()
    return {"ok": True}
