from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List

from backend.database import get_db
from backend.models.academic import Section, Faculty
from backend.models.identity import User
from backend.schemas.section import SectionCreate, SectionUpdate, SectionResponse, ClassTeacherSummary
from backend.dependencies import get_current_user, require_role, require_department_scope

router = APIRouter(prefix="/sections", tags=["Sections"])


def _to_response(sec: Section) -> SectionResponse:
    resp = SectionResponse.model_validate(sec)
    if sec.class_teacher:
        ct_summary = ClassTeacherSummary.model_validate(sec.class_teacher)
        if sec.class_teacher.user:
            ct_summary.name = sec.class_teacher.user.name
        resp.class_teacher = ct_summary
    return resp


@router.get("", include_in_schema=False)
@router.get("/", response_model=List[SectionResponse])
def get_sections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Section).options(
        joinedload(Section.class_teacher).joinedload(Faculty.user)
    )
    if current_user.role in ("ADMIN", "SUPER_ADMIN"):
        sections = query.all()
    elif current_user.role == "FACULTY":
        sections = query.filter(Section.department_id == current_user.department_id).all()
    else:  # STUDENT
        return []
    return [_to_response(s) for s in sections]


@router.get("/{section_id}", response_model=SectionResponse)
def get_section(
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sec = db.query(Section).options(
        joinedload(Section.class_teacher).joinedload(Faculty.user)
    ).filter(Section.id == section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found")
    if current_user.role in ("ADMIN", "SUPER_ADMIN"):
        return _to_response(sec)
    elif current_user.role == "FACULTY":
        if sec.department_id != current_user.department_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Out of department scope")
        return _to_response(sec)
    else:  # STUDENT
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


@router.post("/", response_model=SectionResponse)
def create_section(
    section: SectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    if section.class_teacher_id is not None:

        fac = db.query(Faculty).filter(Faculty.id == section.class_teacher_id).first()
        if not fac:
            raise HTTPException(status_code=400, detail="Assigned class teacher faculty not found")
        if fac.department_id != section.department_id:
            raise HTTPException(status_code=400, detail="Class teacher must belong to the section department")

    db_sec = Section(**section.model_dump())
    db.add(db_sec)
    db.commit()
    db.refresh(db_sec)
    sec_rel = db.query(Section).options(
        joinedload(Section.class_teacher).joinedload(Faculty.user)
    ).filter(Section.id == db_sec.id).first()
    return _to_response(sec_rel or db_sec)


@router.put("/{section_id}", response_model=SectionResponse)
def update_section(
    section_id: int,
    section: SectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_sec = db.query(Section).filter(Section.id == section_id).first()
    if not db_sec:
        raise HTTPException(status_code=404, detail="Section not found")

    dump = section.model_dump(exclude_unset=True)
    target_ct_id = dump.get("class_teacher_id", db_sec.class_teacher_id)
    target_dept_id = dump.get("department_id", db_sec.department_id)

    if target_ct_id is not None:
        fac = db.query(Faculty).filter(Faculty.id == target_ct_id).first()
        if not fac:
            raise HTTPException(status_code=400, detail="Assigned class teacher faculty not found")
        if target_dept_id and fac.department_id != target_dept_id:
            raise HTTPException(status_code=400, detail="Class teacher must belong to the section department")

    for key, value in dump.items():
        setattr(db_sec, key, value)
    db.commit()
    sec_rel = db.query(Section).options(
        joinedload(Section.class_teacher).joinedload(Faculty.user)
    ).filter(Section.id == section_id).first()
    return _to_response(sec_rel or db_sec)


@router.delete("/{section_id}")
def delete_section(
    section_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("ADMIN", "SUPER_ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    db_sec = db.query(Section).filter(Section.id == section_id).first()
    if not db_sec:
        raise HTTPException(status_code=404, detail="Section not found")
    db.delete(db_sec)
    db.commit()
    return {"ok": True}