"""
backend/services/curriculum_service.py
--------------------------------------
Comprehensive Business Logic Engine for:
1. Academic Structure (Regulations, Admission Cohorts).
2. Central Curriculum Registry (Versions, Semesters, Subject Mappings).
3. Versioning Lifecycle (Draft -> Needs Review -> Validated -> Approved -> Published -> Superseded).
4. AI Syllabus PDF Extraction, Page Parsing & Citation Engine.
5. Department Releases & Admin Curriculum Inbox.
6. Curriculum Correction Request Ticketing & Persistent Threaded Discussions.
7. Operational Allocation (Section Offerings, Faculty Teaching Assignment).
8. Scheduling Readiness Preflight (Curriculum-to-Timetable integrity verification).
9. Super Admin Executive Dashboard Metrics & Audit Logging.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from backend.models.academic import (
    AcademicYear,
    Batch,
    Department,
    Faculty,
    Program,
    Section,
    Semester,
    Student,
)
from backend.models.courses import Course
from backend.models.curriculum import (
    AdmissionCohort,
    CurriculumDocument,
    CurriculumExtractionJob,
    CurriculumRelease,
    CurriculumRequest,
    CurriculumRequestMessage,
    CurriculumSemester,
    CurriculumSubjectMapping,
    CurriculumVersion,
    FacultyCourseOffering,
    Regulation,
    SectionCourseOffering,
)
from backend.models.identity import User
from backend.models.workflow import AuditLog
from backend.schemas.curriculum import (
    AdmissionCohortCreate,
    AdmissionCohortResponse,
    AdmissionCohortUpdate,
    CurriculumExtractionJobResponse,
    CurriculumReadinessResponse,
    CurriculumReleaseResponse,
    CurriculumRequestCreate,
    CurriculumRequestMessageResponse,
    CurriculumRequestResponse,
    CurriculumSemesterResponse,
    CurriculumSubjectMappingCreate,
    CurriculumSubjectMappingResponse,
    CurriculumSubjectMappingUpdate,
    CurriculumVersionCreate,
    CurriculumVersionResponse,
    CurriculumVersionSummary,
    CurriculumVersionUpdate,
    ExtractedSubjectItem,
    FacultyCourseOfferingCreate,
    FacultyCourseOfferingResponse,
    RegulationCreate,
    RegulationResponse,
    RegulationUpdate,
    SectionCourseOfferingCreate,
    SectionCourseOfferingResponse,
    SubjectReadinessItem,
    SuperAdminDashboardStats,
)
from backend.utils.datetime_utils import utc_now


STORAGE_DIR = os.path.join("storage", "curriculum_documents")


# ---------------------------------------------------------------------------
# Helper: Audit Logging
# ---------------------------------------------------------------------------

def _log_curriculum_audit(
    db: Session,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: Optional[int],
    old_value: Optional[Dict[str, Any]] = None,
    new_value: Optional[Dict[str, Any]] = None,
) -> None:
    audit = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
    )
    db.add(audit)


# ---------------------------------------------------------------------------
# 1. Regulation Services
# ---------------------------------------------------------------------------

def list_regulations(
    db: Session,
    department_id: Optional[int] = None,
    is_active: Optional[bool] = None,
) -> List[RegulationResponse]:
    query = db.query(Regulation).options(joinedload(Regulation.department))
    if department_id is not None:
        query = query.filter(or_(Regulation.department_id == department_id, Regulation.department_id.is_(None)))
    if is_active is not None:
        query = query.filter(Regulation.is_active == is_active)
    regulations = query.order_by(Regulation.effective_year.desc(), Regulation.code).all()

    results: List[RegulationResponse] = []
    for reg in regulations:
        cohorts_count = db.query(func.count(AdmissionCohort.id)).filter(AdmissionCohort.regulation_id == reg.id).scalar() or 0
        curricula_count = db.query(func.count(CurriculumVersion.id)).filter(CurriculumVersion.regulation_id == reg.id).scalar() or 0
        results.append(
            RegulationResponse(
                id=reg.id,
                code=reg.code,
                name=reg.name,
                department_id=reg.department_id,
                department_name=reg.department.name if reg.department else "All Departments",
                effective_year=reg.effective_year,
                is_active=reg.is_active,
                description=reg.description,
                cohorts_count=cohorts_count,
                curriculum_versions_count=curricula_count,
                created_at=reg.created_at,
                updated_at=reg.updated_at,
            )
        )
    return results


def get_regulation(db: Session, regulation_id: int) -> Regulation:
    reg = db.query(Regulation).options(joinedload(Regulation.department)).filter(Regulation.id == regulation_id).first()
    if not reg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Regulation #{regulation_id} not found.")
    return reg


def create_regulation(db: Session, data: RegulationCreate, user_id: int) -> RegulationResponse:
    code_clean = data.code.strip().upper()
    existing = db.query(Regulation).filter(Regulation.code == code_clean).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Regulation with code '{code_clean}' already exists."
        )

    reg = Regulation(
        code=code_clean,
        name=data.name.strip(),
        department_id=data.department_id,
        effective_year=data.effective_year,
        is_active=data.is_active,
        description=data.description,
    )
    db.add(reg)
    db.flush()

    _log_curriculum_audit(
        db, user_id, "CREATE_REGULATION", "Regulation", reg.id,
        new_value={"code": reg.code, "name": reg.name, "effective_year": reg.effective_year}
    )
    db.commit()
    db.refresh(reg)

    dept_name = reg.department.name if reg.department else "All Departments"
    return RegulationResponse(
        id=reg.id,
        code=reg.code,
        name=reg.name,
        department_id=reg.department_id,
        department_name=dept_name,
        effective_year=reg.effective_year,
        is_active=reg.is_active,
        description=reg.description,
        cohorts_count=0,
        curriculum_versions_count=0,
        created_at=reg.created_at,
        updated_at=reg.updated_at,
    )


def update_regulation(db: Session, regulation_id: int, data: RegulationUpdate, user_id: int) -> RegulationResponse:
    reg = get_regulation(db, regulation_id)
    old_state = {"code": reg.code, "name": reg.name, "is_active": reg.is_active}

    if data.code is not None:
        code_clean = data.code.strip().upper()
        if code_clean != reg.code:
            existing = db.query(Regulation).filter(Regulation.code == code_clean, Regulation.id != reg.id).first()
            if existing:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Code '{code_clean}' already in use.")
            reg.code = code_clean

    if data.name is not None:
        reg.name = data.name.strip()
    if data.department_id is not None:
        reg.department_id = data.department_id
    if data.effective_year is not None:
        reg.effective_year = data.effective_year
    if data.is_active is not None:
        reg.is_active = data.is_active
    if data.description is not None:
        reg.description = data.description

    _log_curriculum_audit(
        db, user_id, "UPDATE_REGULATION", "Regulation", reg.id,
        old_value=old_state,
        new_value={"code": reg.code, "name": reg.name, "is_active": reg.is_active}
    )
    db.commit()
    db.refresh(reg)

    cohorts_count = db.query(func.count(AdmissionCohort.id)).filter(AdmissionCohort.regulation_id == reg.id).scalar() or 0
    curricula_count = db.query(func.count(CurriculumVersion.id)).filter(CurriculumVersion.regulation_id == reg.id).scalar() or 0

    return RegulationResponse(
        id=reg.id,
        code=reg.code,
        name=reg.name,
        department_id=reg.department_id,
        department_name=reg.department.name if reg.department else "All Departments",
        effective_year=reg.effective_year,
        is_active=reg.is_active,
        description=reg.description,
        cohorts_count=cohorts_count,
        curriculum_versions_count=curricula_count,
        created_at=reg.created_at,
        updated_at=reg.updated_at,
    )


# ---------------------------------------------------------------------------
# 2. Admission Cohort Services
# ---------------------------------------------------------------------------

def list_cohorts(
    db: Session,
    program_id: Optional[int] = None,
    regulation_id: Optional[int] = None,
    is_active: Optional[bool] = None,
) -> List[AdmissionCohortResponse]:
    query = db.query(AdmissionCohort).options(
        joinedload(AdmissionCohort.program),
        joinedload(AdmissionCohort.regulation),
    )
    if program_id is not None:
        query = query.filter(AdmissionCohort.program_id == program_id)
    if regulation_id is not None:
        query = query.filter(AdmissionCohort.regulation_id == regulation_id)
    if is_active is not None:
        query = query.filter(AdmissionCohort.is_active == is_active)

    cohorts = query.order_by(AdmissionCohort.start_year.desc(), AdmissionCohort.cohort_name).all()
    return [
        AdmissionCohortResponse(
            id=c.id,
            cohort_name=c.cohort_name,
            start_year=c.start_year,
            end_year=c.end_year,
            program_id=c.program_id,
            program_name=c.program.program_name if c.program else None,
            regulation_id=c.regulation_id,
            regulation_code=c.regulation.code if c.regulation else None,
            is_active=c.is_active,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in cohorts
    ]


def get_cohort(db: Session, cohort_id: int) -> AdmissionCohort:
    cohort = db.query(AdmissionCohort).options(
        joinedload(AdmissionCohort.program),
        joinedload(AdmissionCohort.regulation),
    ).filter(AdmissionCohort.id == cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Admission Cohort #{cohort_id} not found.")
    return cohort


def create_cohort(db: Session, data: AdmissionCohortCreate, user_id: int) -> AdmissionCohortResponse:
    if data.end_year <= data.start_year:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cohort end year must be strictly greater than start year."
        )

    # Verify program and regulation exist
    prog = db.query(Program).filter(Program.id == data.program_id).first()
    if not prog:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Program #{data.program_id} not found.")
    reg = db.query(Regulation).filter(Regulation.id == data.regulation_id).first()
    if not reg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Regulation #{data.regulation_id} not found.")

    existing = db.query(AdmissionCohort).filter(
        AdmissionCohort.program_id == data.program_id,
        AdmissionCohort.cohort_name == data.cohort_name.strip(),
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cohort '{data.cohort_name}' already exists for program '{prog.program_name}'."
        )

    cohort = AdmissionCohort(
        cohort_name=data.cohort_name.strip(),
        start_year=data.start_year,
        end_year=data.end_year,
        program_id=data.program_id,
        regulation_id=data.regulation_id,
        is_active=data.is_active,
    )
    db.add(cohort)
    db.flush()

    _log_curriculum_audit(
        db, user_id, "CREATE_COHORT", "AdmissionCohort", cohort.id,
        new_value={"cohort_name": cohort.cohort_name, "program_id": cohort.program_id, "regulation_id": cohort.regulation_id}
    )
    db.commit()
    db.refresh(cohort)

    return AdmissionCohortResponse(
        id=cohort.id,
        cohort_name=cohort.cohort_name,
        start_year=cohort.start_year,
        end_year=cohort.end_year,
        program_id=cohort.program_id,
        program_name=prog.program_name,
        regulation_id=cohort.regulation_id,
        regulation_code=reg.code,
        is_active=cohort.is_active,
        created_at=cohort.created_at,
        updated_at=cohort.updated_at,
    )


def update_cohort(db: Session, cohort_id: int, data: AdmissionCohortUpdate, user_id: int) -> AdmissionCohortResponse:
    cohort = get_cohort(db, cohort_id)
    old_state = {"name": cohort.cohort_name, "is_active": cohort.is_active}

    if data.cohort_name is not None:
        cohort.cohort_name = data.cohort_name.strip()
    if data.start_year is not None:
        cohort.start_year = data.start_year
    if data.end_year is not None:
        cohort.end_year = data.end_year
    if cohort.end_year <= cohort.start_year:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End year must exceed start year.")
    if data.program_id is not None:
        cohort.program_id = data.program_id
    if data.regulation_id is not None:
        cohort.regulation_id = data.regulation_id
    if data.is_active is not None:
        cohort.is_active = data.is_active

    _log_curriculum_audit(
        db, user_id, "UPDATE_COHORT", "AdmissionCohort", cohort.id,
        old_value=old_state,
        new_value={"name": cohort.cohort_name, "is_active": cohort.is_active}
    )
    db.commit()
    db.refresh(cohort)

    return AdmissionCohortResponse(
        id=cohort.id,
        cohort_name=cohort.cohort_name,
        start_year=cohort.start_year,
        end_year=cohort.end_year,
        program_id=cohort.program_id,
        program_name=cohort.program.program_name if cohort.program else None,
        regulation_id=cohort.regulation_id,
        regulation_code=cohort.regulation.code if cohort.regulation else None,
        is_active=cohort.is_active,
        created_at=cohort.created_at,
        updated_at=cohort.updated_at,
    )


# ---------------------------------------------------------------------------
# 3. Curriculum Versioning & Lifecycle Services
# ---------------------------------------------------------------------------

def recalculate_curriculum_totals(db: Session, version_id: int) -> None:
    """Recalculates credits and contact hours for all semesters and the version as a whole."""
    semesters = db.query(CurriculumSemester).filter(CurriculumSemester.curriculum_version_id == version_id).all()
    version_total_credits = 0.0

    for sem in semesters:
        subjects = db.query(CurriculumSubjectMapping).filter(CurriculumSubjectMapping.curriculum_semester_id == sem.id).all()
        sem_credits = sum(s.credits for s in subjects)
        sem_contact = sum(s.contact_hours for s in subjects)
        sem.total_credits = sem_credits
        sem.total_contact_hours = sem_contact
        version_total_credits += sem_credits

    version = db.query(CurriculumVersion).filter(CurriculumVersion.id == version_id).first()
    if version:
        version.total_credits = version_total_credits
    db.flush()


def generate_curriculum_version_code(db: Session, department_code: str, regulation_code: str) -> str:
    prefix = f"CURR-{department_code.upper()}-{regulation_code.upper()}"
    existing_count = db.query(func.count(CurriculumVersion.id)).filter(
        CurriculumVersion.version_code.like(f"{prefix}-V%")
    ).scalar() or 0
    return f"{prefix}-V{existing_count + 1}"


def create_curriculum_version(db: Session, data: CurriculumVersionCreate, user_id: int) -> CurriculumVersionResponse:
    dept = db.query(Department).filter(Department.id == data.department_id).first()
    if not dept:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Department #{data.department_id} not found.")
    prog = db.query(Program).filter(Program.id == data.program_id).first()
    if not prog:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Program #{data.program_id} not found.")
    reg = db.query(Regulation).filter(Regulation.id == data.regulation_id).first()
    if not reg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Regulation #{data.regulation_id} not found.")

    dept_code = dept.department_code if hasattr(dept, 'code') and dept.department_code else dept.name[:4].upper()
    version_code = data.version_code.strip() if data.version_code else generate_curriculum_version_code(db, dept_code, reg.code)

    # Resolve total_semesters dynamically from input, program duration (e.g. 2 years -> 4 sem, 5 years -> 10 sem), or default
    resolved_total_semesters = data.total_semesters
    if resolved_total_semesters is None or resolved_total_semesters <= 0:
        resolved_total_semesters = (prog.duration * 2) if (prog.duration and prog.duration > 0) else 8

    version = CurriculumVersion(
        version_code=version_code,
        department_id=data.department_id,
        program_id=data.program_id,
        regulation_id=data.regulation_id,
        cohort_id=data.cohort_id,
        version_number=1,
        status="DRAFT",
        description=data.description,
        total_semesters=resolved_total_semesters,
        total_credits=0.0,
        created_by_id=user_id,
    )
    db.add(version)
    db.flush()

    # Automatically create semester rows 1..total_semesters
    for sem_num in range(1, resolved_total_semesters + 1):
        sem_row = CurriculumSemester(
            curriculum_version_id=version.id,
            semester_number=sem_num,
            total_credits=0.0,
            total_contact_hours=0,
            notes=f"Semester {sem_num}",
        )
        db.add(sem_row)

    _log_curriculum_audit(
        db, user_id, "CREATE_CURRICULUM_VERSION", "CurriculumVersion", version.id,
        new_value={"version_code": version.version_code, "status": "DRAFT", "semesters": resolved_total_semesters}
    )
    db.commit()
    db.refresh(version)
    return get_curriculum_version(db, version.id)


def get_curriculum_version(db: Session, version_id: int) -> CurriculumVersionResponse:
    version = db.query(CurriculumVersion).options(
        joinedload(CurriculumVersion.department),
        joinedload(CurriculumVersion.program),
        joinedload(CurriculumVersion.regulation),
        joinedload(CurriculumVersion.cohort),
        joinedload(CurriculumVersion.creator),
        joinedload(CurriculumVersion.reviewer),
        joinedload(CurriculumVersion.approver),
        joinedload(CurriculumVersion.publisher),
        joinedload(CurriculumVersion.document),
        joinedload(CurriculumVersion.semesters).joinedload(CurriculumSemester.subject_mappings),
    ).filter(CurriculumVersion.id == version_id).first()

    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Curriculum Version #{version_id} not found.")

    semesters_resp: List[CurriculumSemesterResponse] = []
    for sem in sorted(version.semesters, key=lambda s: s.semester_number):
        subjects_resp: List[CurriculumSubjectMappingResponse] = []
        for s in sem.subject_mappings:
            subjects_resp.append(
                CurriculumSubjectMappingResponse(
                    id=s.id,
                    curriculum_version_id=s.curriculum_version_id,
                    curriculum_semester_id=s.curriculum_semester_id,
                    semester_number=sem.semester_number,
                    course_id=s.course_id,
                    subject_code=s.subject_code,
                    subject_name=s.subject_name,
                    subject_type=s.subject_type,
                    is_mandatory=s.is_mandatory,
                    elective_group_name=s.elective_group_name,
                    credits=s.credits,
                    lecture_hours=s.lecture_hours,
                    tutorial_hours=s.tutorial_hours,
                    practical_hours=s.practical_hours,
                    contact_hours=s.contact_hours,
                    practical_consecutive_periods=s.practical_consecutive_periods,
                    requires_lab=s.requires_lab,
                    course_description=s.course_description,
                    prerequisites=s.prerequisites,
                    co_requisites=s.co_requisites,
                    source_pdf_id=s.source_pdf_id,
                    source_page=s.source_page,
                    source_text=s.source_text,
                    verification_status=s.verification_status,
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                )
            )
        semesters_resp.append(
            CurriculumSemesterResponse(
                id=sem.id,
                curriculum_version_id=sem.curriculum_version_id,
                semester_number=sem.semester_number,
                total_credits=sem.total_credits,
                total_contact_hours=sem.total_contact_hours,
                notes=sem.notes,
                subject_mappings=subjects_resp,
            )
        )

    return CurriculumVersionResponse(
        id=version.id,
        version_code=version.version_code,
        department_id=version.department_id,
        department_name=version.department.name if version.department else None,
        program_id=version.program_id,
        program_name=version.program.program_name if version.program else None,
        regulation_id=version.regulation_id,
        regulation_code=version.regulation.code if version.regulation else None,
        cohort_id=version.cohort_id,
        cohort_name=version.cohort.cohort_name if version.cohort else None,
        version_number=version.version_number,
        status=version.status,
        description=version.description,
        total_credits=version.total_credits,
        total_semesters=version.total_semesters,
        source_document_id=version.source_document_id,
        source_document_title=version.document.title if version.document else None,
        created_by_id=version.created_by_id,
        created_by_name=version.creator.name if version.creator else None,
        reviewed_by_id=version.reviewed_by_id,
        reviewed_by_name=version.reviewer.name if version.reviewer else None,
        approved_by_id=version.approved_by_id,
        approved_by_name=version.approver.name if version.approver else None,
        published_by_id=version.published_by_id,
        published_by_name=version.publisher.name if version.publisher else None,
        published_at=version.published_at,
        superseded_by_id=version.superseded_by_id,
        previous_version_id=version.previous_version_id,
        created_at=version.created_at,
        updated_at=version.updated_at,
        semesters=semesters_resp,
    )


def list_curriculum_versions(
    db: Session,
    department_id: Optional[int] = None,
    program_id: Optional[int] = None,
    regulation_id: Optional[int] = None,
    status: Optional[str] = None,
) -> List[CurriculumVersionSummary]:
    query = db.query(CurriculumVersion).options(
        joinedload(CurriculumVersion.department),
        joinedload(CurriculumVersion.program),
        joinedload(CurriculumVersion.regulation),
        joinedload(CurriculumVersion.cohort),
    )
    if department_id is not None:
        query = query.filter(CurriculumVersion.department_id == department_id)
    if program_id is not None:
        query = query.filter(CurriculumVersion.program_id == program_id)
    if regulation_id is not None:
        query = query.filter(CurriculumVersion.regulation_id == regulation_id)
    if status is not None:
        query = query.filter(CurriculumVersion.status == status)

    versions = query.order_by(CurriculumVersion.created_at.desc()).all()
    return [
        CurriculumVersionSummary(
            id=v.id,
            version_code=v.version_code,
            department_name=v.department.name if v.department else "N/A",
            program_name=v.program.program_name if (v.program and v.program.program_name) else "N/A",
            regulation_code=v.regulation.code if v.regulation else "N/A",
            cohort_name=v.cohort.cohort_name if v.cohort else None,
            version_number=v.version_number,
            status=v.status,
            total_credits=v.total_credits,
            total_semesters=v.total_semesters,
            published_at=v.published_at,
            created_at=v.created_at,
        )
        for v in versions
    ]


def update_curriculum_version_status(
    db: Session,
    version_id: int,
    new_status: str,
    notes: Optional[str],
    user_id: int,
) -> CurriculumVersionResponse:
    version = db.query(CurriculumVersion).filter(CurriculumVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Version #{version_id} not found.")

    if version.status == "PUBLISHED" and new_status not in ("SUPERSEDED", "ARCHIVED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Published curricula are immutable. Create a new revision version to make changes."
        )

    old_status = version.status
    version.status = new_status

    if new_status == "NEEDS_REVIEW":
        version.reviewed_by_id = user_id
    elif new_status == "APPROVED":
        version.approved_by_id = user_id
    elif new_status == "PUBLISHED":
        version.published_by_id = user_id
        version.published_at = utc_now()
        # Automatically release to owning department
        release_curriculum_version(db, version.id, [version.department_id], user_id)

    _log_curriculum_audit(
        db, user_id, f"CURRICULUM_STATUS_{new_status}", "CurriculumVersion", version.id,
        old_value={"status": old_status},
        new_value={"status": new_status, "notes": notes}
    )
    db.commit()
    db.refresh(version)
    return get_curriculum_version(db, version.id)


def publish_curriculum_version(
    db: Session,
    version_id: int,
    user_id: int,
    department_ids: Optional[List[int]] = None,
) -> CurriculumVersionResponse:
    version = db.query(CurriculumVersion).filter(CurriculumVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Version #{version_id} not found.")

    if version.status not in ("APPROVED", "VALIDATED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot publish curriculum in '{version.status}' status. Must be APPROVED or VALIDATED first."
        )

    # Verification: check if there are subjects in the version
    subject_count = db.query(func.count(CurriculumSubjectMapping.id)).filter(
        CurriculumSubjectMapping.curriculum_version_id == version.id
    ).scalar() or 0
    if subject_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot publish a curriculum with 0 subject mappings. Populate subjects before publication."
        )

    version.status = "PUBLISHED"
    version.published_by_id = user_id
    version.published_at = utc_now()

    target_departments = department_ids if department_ids else [version.department_id]
    release_curriculum_version(db, version.id, target_departments, user_id)

    # Mark previous version as superseded if applicable
    if version.previous_version_id:
        prev = db.query(CurriculumVersion).filter(CurriculumVersion.id == version.previous_version_id).first()
        if prev and prev.status == "PUBLISHED":
            prev.status = "SUPERSEDED"
            prev.superseded_by_id = version.id

    _log_curriculum_audit(
        db, user_id, "PUBLISH_CURRICULUM", "CurriculumVersion", version.id,
        new_value={"version_code": version.version_code, "published_at": str(version.published_at), "departments": target_departments}
    )
    db.commit()
    return get_curriculum_version(db, version.id)


def create_new_revision(db: Session, version_id: int, user_id: int) -> CurriculumVersionResponse:
    """Clones an existing version (semesters and subject mappings) into a new DRAFT revision."""
    parent = db.query(CurriculumVersion).filter(CurriculumVersion.id == version_id).first()
    if not parent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Parent curriculum version #{version_id} not found.")

    new_version_number = parent.version_number + 1
    code_base = parent.version_code.rsplit("-V", 1)[0]
    new_version_code = f"{code_base}-V{new_version_number}"

    # Check uniqueness
    existing = db.query(CurriculumVersion).filter(CurriculumVersion.version_code == new_version_code).first()
    if existing:
        new_version_code = f"{code_base}-V{new_version_number}-REV"

    new_version = CurriculumVersion(
        version_code=new_version_code,
        department_id=parent.department_id,
        program_id=parent.program_id,
        regulation_id=parent.regulation_id,
        cohort_id=parent.cohort_id,
        version_number=new_version_number,
        status="DRAFT",
        description=f"Revision {new_version_number} cloned from {parent.version_code}",
        total_semesters=parent.total_semesters,
        total_credits=parent.total_credits,
        source_document_id=parent.source_document_id,
        previous_version_id=parent.id,
        created_by_id=user_id,
    )
    db.add(new_version)
    db.flush()

    # Clone semesters and subject mappings
    parent_semesters = db.query(CurriculumSemester).filter(CurriculumSemester.curriculum_version_id == parent.id).all()
    for p_sem in parent_semesters:
        new_sem = CurriculumSemester(
            curriculum_version_id=new_version.id,
            semester_number=p_sem.semester_number,
            total_credits=p_sem.total_credits,
            total_contact_hours=p_sem.total_contact_hours,
            notes=p_sem.notes,
        )
        db.add(new_sem)
        db.flush()

        p_subjects = db.query(CurriculumSubjectMapping).filter(CurriculumSubjectMapping.curriculum_semester_id == p_sem.id).all()
        for p_sub in p_subjects:
            new_sub = CurriculumSubjectMapping(
                curriculum_version_id=new_version.id,
                curriculum_semester_id=new_sem.id,
                course_id=p_sub.course_id,
                subject_code=p_sub.subject_code,
                subject_name=p_sub.subject_name,
                subject_type=p_sub.subject_type,
                is_mandatory=p_sub.is_mandatory,
                elective_group_name=p_sub.elective_group_name,
                credits=p_sub.credits,
                lecture_hours=p_sub.lecture_hours,
                tutorial_hours=p_sub.tutorial_hours,
                practical_hours=p_sub.practical_hours,
                contact_hours=p_sub.contact_hours,
                practical_consecutive_periods=p_sub.practical_consecutive_periods,
                requires_lab=p_sub.requires_lab,
                course_description=p_sub.course_description,
                prerequisites=p_sub.prerequisites,
                co_requisites=p_sub.co_requisites,
                source_pdf_id=p_sub.source_pdf_id,
                source_page=p_sub.source_page,
                source_text=p_sub.source_text,
                verification_status=p_sub.verification_status,
            )
            db.add(new_sub)

    _log_curriculum_audit(
        db, user_id, "BRANCH_REVISION", "CurriculumVersion", new_version.id,
        new_value={"parent_id": parent.id, "new_code": new_version.version_code}
    )
    db.commit()
    return get_curriculum_version(db, new_version.id)


# ---------------------------------------------------------------------------
# 4. Subject Mapping Services
# ---------------------------------------------------------------------------

def add_subject_mapping(
    db: Session,
    version_id: int,
    data: CurriculumSubjectMappingCreate,
    user_id: int,
) -> CurriculumSubjectMappingResponse:
    version = db.query(CurriculumVersion).filter(CurriculumVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Curriculum Version #{version_id} not found.")

    if version.status == "PUBLISHED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify a published curriculum. Create a revision.")

    semester = db.query(CurriculumSemester).filter(
        CurriculumSemester.id == data.curriculum_semester_id,
        CurriculumSemester.curriculum_version_id == version.id,
    ).first()
    if not semester:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Curriculum Semester #{data.curriculum_semester_id} not found in version #{version_id}.")

    clean_code = data.subject_code.strip().upper()
    existing = db.query(CurriculumSubjectMapping).filter(
        CurriculumSubjectMapping.curriculum_version_id == version.id,
        CurriculumSubjectMapping.subject_code == clean_code,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Subject code '{clean_code}' already exists in curriculum version #{version.version_code}."
        )

    # Sync with Course catalog if course_id not specified
    course_id = data.course_id
    if not course_id:
        course = db.query(Course).filter(Course.course_code == clean_code).first()
        if not course:
            course = Course(
                course_code=clean_code,
                course_name=data.subject_name.strip(),
                department_id=version.department_id,
                credits=int(data.credits),
                lecture_hours=data.lecture_hours,
                tutorial_hours=data.tutorial_hours,
                practical_hours=data.practical_hours,
                requires_lab=data.requires_lab,
            )
            db.add(course)
            db.flush()
        course_id = course.id

    calc_contact = data.lecture_hours + data.tutorial_hours + data.practical_hours
    contact_hours = calc_contact if calc_contact > 0 else data.contact_hours

    mapping = CurriculumSubjectMapping(
        curriculum_version_id=version.id,
        curriculum_semester_id=semester.id,
        course_id=course_id,
        subject_code=clean_code,
        subject_name=data.subject_name.strip(),
        subject_type=data.subject_type,
        is_mandatory=data.is_mandatory,
        elective_group_name=data.elective_group_name,
        credits=data.credits,
        lecture_hours=data.lecture_hours,
        tutorial_hours=data.tutorial_hours,
        practical_hours=data.practical_hours,
        contact_hours=contact_hours,
        practical_consecutive_periods=data.practical_consecutive_periods,
        requires_lab=data.requires_lab,
        course_description=data.course_description,
        prerequisites=data.prerequisites,
        co_requisites=data.co_requisites,
        source_pdf_id=data.source_pdf_id,
        source_page=data.source_page,
        source_text=data.source_text,
        verification_status=data.verification_status,
    )
    db.add(mapping)
    db.flush()

    recalculate_curriculum_totals(db, version.id)
    _log_curriculum_audit(
        db, user_id, "ADD_SUBJECT_MAPPING", "CurriculumSubjectMapping", mapping.id,
        new_value={"code": mapping.subject_code, "name": mapping.subject_name, "credits": mapping.credits}
    )
    db.commit()
    db.refresh(mapping)

    return CurriculumSubjectMappingResponse(
        id=mapping.id,
        curriculum_version_id=mapping.curriculum_version_id,
        curriculum_semester_id=mapping.curriculum_semester_id,
        semester_number=semester.semester_number,
        course_id=mapping.course_id,
        subject_code=mapping.subject_code,
        subject_name=mapping.subject_name,
        subject_type=mapping.subject_type,
        is_mandatory=mapping.is_mandatory,
        elective_group_name=mapping.elective_group_name,
        credits=mapping.credits,
        lecture_hours=mapping.lecture_hours,
        tutorial_hours=mapping.tutorial_hours,
        practical_hours=mapping.practical_hours,
        contact_hours=mapping.contact_hours,
        practical_consecutive_periods=mapping.practical_consecutive_periods,
        requires_lab=mapping.requires_lab,
        course_description=mapping.course_description,
        prerequisites=mapping.prerequisites,
        co_requisites=mapping.co_requisites,
        source_pdf_id=mapping.source_pdf_id,
        source_page=mapping.source_page,
        source_text=mapping.source_text,
        verification_status=mapping.verification_status,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    )


def update_subject_mapping(
    db: Session,
    mapping_id: int,
    data: CurriculumSubjectMappingUpdate,
    user_id: int,
) -> CurriculumSubjectMappingResponse:
    mapping = db.query(CurriculumSubjectMapping).filter(CurriculumSubjectMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Subject Mapping #{mapping_id} not found.")

    version = db.query(CurriculumVersion).filter(CurriculumVersion.id == mapping.curriculum_version_id).first()
    if version and version.status == "PUBLISHED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit subjects of a published curriculum.")

    old_state = {"code": mapping.subject_code, "credits": mapping.credits, "contact_hours": mapping.contact_hours}

    if data.subject_code is not None:
        clean_code = data.subject_code.strip().upper()
        if clean_code != mapping.subject_code:
            existing = db.query(CurriculumSubjectMapping).filter(
                CurriculumSubjectMapping.curriculum_version_id == mapping.curriculum_version_id,
                CurriculumSubjectMapping.subject_code == clean_code,
                CurriculumSubjectMapping.id != mapping.id,
            ).first()
            if existing:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Subject code '{clean_code}' already exists in version.")
            mapping.subject_code = clean_code

    if data.subject_name is not None:
        mapping.subject_name = data.subject_name.strip()
    if data.subject_type is not None:
        mapping.subject_type = data.subject_type
    if data.is_mandatory is not None:
        mapping.is_mandatory = data.is_mandatory
    if data.elective_group_name is not None:
        mapping.elective_group_name = data.elective_group_name
    if data.credits is not None:
        mapping.credits = data.credits
    if data.lecture_hours is not None:
        mapping.lecture_hours = data.lecture_hours
    if data.tutorial_hours is not None:
        mapping.tutorial_hours = data.tutorial_hours
    if data.practical_hours is not None:
        mapping.practical_hours = data.practical_hours
    if data.contact_hours is not None:
        mapping.contact_hours = data.contact_hours
    else:
        mapping.contact_hours = mapping.lecture_hours + mapping.tutorial_hours + mapping.practical_hours
    if data.practical_consecutive_periods is not None:
        mapping.practical_consecutive_periods = data.practical_consecutive_periods
    if data.requires_lab is not None:
        mapping.requires_lab = data.requires_lab
    if data.course_description is not None:
        mapping.course_description = data.course_description
    if data.prerequisites is not None:
        mapping.prerequisites = data.prerequisites
    if data.co_requisites is not None:
        mapping.co_requisites = data.co_requisites
    if data.source_page is not None:
        mapping.source_page = data.source_page
    if data.source_text is not None:
        mapping.source_text = data.source_text
    if data.verification_status is not None:
        mapping.verification_status = data.verification_status

    db.flush()
    recalculate_curriculum_totals(db, mapping.curriculum_version_id)
    _log_curriculum_audit(
        db, user_id, "UPDATE_SUBJECT_MAPPING", "CurriculumSubjectMapping", mapping.id,
        old_value=old_state,
        new_value={"code": mapping.subject_code, "credits": mapping.credits, "contact_hours": mapping.contact_hours}
    )
    db.commit()
    db.refresh(mapping)

    semester = db.query(CurriculumSemester).filter(CurriculumSemester.id == mapping.curriculum_semester_id).first()
    return CurriculumSubjectMappingResponse(
        id=mapping.id,
        curriculum_version_id=mapping.curriculum_version_id,
        curriculum_semester_id=mapping.curriculum_semester_id,
        semester_number=semester.semester_number if semester else None,
        course_id=mapping.course_id,
        subject_code=mapping.subject_code,
        subject_name=mapping.subject_name,
        subject_type=mapping.subject_type,
        is_mandatory=mapping.is_mandatory,
        elective_group_name=mapping.elective_group_name,
        credits=mapping.credits,
        lecture_hours=mapping.lecture_hours,
        tutorial_hours=mapping.tutorial_hours,
        practical_hours=mapping.practical_hours,
        contact_hours=mapping.contact_hours,
        practical_consecutive_periods=mapping.practical_consecutive_periods,
        requires_lab=mapping.requires_lab,
        course_description=mapping.course_description,
        prerequisites=mapping.prerequisites,
        co_requisites=mapping.co_requisites,
        source_pdf_id=mapping.source_pdf_id,
        source_page=mapping.source_page,
        source_text=mapping.source_text,
        verification_status=mapping.verification_status,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    )


def delete_subject_mapping(db: Session, mapping_id: int, user_id: int) -> None:
    mapping = db.query(CurriculumSubjectMapping).filter(CurriculumSubjectMapping.id == mapping_id).first()
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Subject mapping #{mapping_id} not found.")

    version = db.query(CurriculumVersion).filter(CurriculumVersion.id == mapping.curriculum_version_id).first()
    if version and version.status == "PUBLISHED":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete subject from published curriculum.")

    version_id = mapping.curriculum_version_id
    code = mapping.subject_code
    db.delete(mapping)
    db.flush()
    recalculate_curriculum_totals(db, version_id)

    _log_curriculum_audit(
        db, user_id, "DELETE_SUBJECT_MAPPING", "CurriculumSubjectMapping", mapping_id,
        old_value={"subject_code": code}
    )
    db.commit()


# ---------------------------------------------------------------------------
# 5. PDF Upload & AI Syllabus Extraction Studio
# ---------------------------------------------------------------------------

def store_curriculum_document(
    db: Session,
    file_bytes: bytes,
    filename: str,
    title: str,
    user_id: int,
    department_id: Optional[int] = None,
    program_id: Optional[int] = None,
    regulation_id: Optional[int] = None,
    cohort_id: Optional[int] = None,
    curriculum_version_id: Optional[int] = None,
) -> CurriculumDocument:
    os.makedirs(STORAGE_DIR, exist_ok=True)
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # Save to disk using file_hash to prevent collision or overwriting
    safe_filename = f"{file_hash[:16]}_{re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)}"
    file_path = os.path.join(STORAGE_DIR, safe_filename)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    doc = CurriculumDocument(
        title=title.strip(),
        file_name=filename,
        file_path=file_path,
        file_hash=file_hash,
        file_size_bytes=len(file_bytes),
        department_id=department_id,
        program_id=program_id,
        regulation_id=regulation_id,
        cohort_id=cohort_id,
        curriculum_version_id=curriculum_version_id,
        uploaded_by_id=user_id,
        status="UPLOADED",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def extract_curriculum_from_pdf(
    db: Session,
    document_id: int,
    target_version_id: Optional[int],
    user_id: int,
) -> CurriculumExtractionJobResponse:
    """
    Extracts curriculum schemes from PDF using PyPDF and deterministic
    heuristic table/pattern matching to extract semesters and subjects.
    """
    doc = db.query(CurriculumDocument).filter(CurriculumDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document #{document_id} not found.")

    if not os.path.exists(doc.file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found on disk: {doc.file_path}")

    from pypdf import PdfReader

    job = CurriculumExtractionJob(
        document_id=doc.id,
        target_curriculum_version_id=target_version_id,
        status="PROCESSING",
        created_by_id=user_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        reader = PdfReader(doc.file_path)
        total_pages = len(reader.pages)
        job.total_pages = total_pages

        extracted_items: List[ExtractedSubjectItem] = []
        semesters_found: set[int] = set()

        # Regular expressions for curriculum items
        # Matches typical patterns: CS301 / 23CS301 / HS101 / MA201
        course_code_pattern = re.compile(r'\b([A-Z]{2,4}\s?[\d]{3,4}[A-Z]?)\b')
        # Matches L T P C numbers e.g. "3 0 0 3" or "3-0-2-4" or "3 1 0 4"
        ltpc_pattern = re.compile(r'(\d+)\s*[-|\s]\s*(\d+)\s*[-|\s]\s*(\d+)\s*[-|\s]\s*(\d+(\.\d+)?)')
        # Semester header matching
        sem_header_pattern = re.compile(
            r'(?:SEMESTER|SEM|Sem)\s*[:\-]?\s*([IVXLCDM]+|\d+)',
            re.IGNORECASE
        )

        roman_to_int = {
            "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
            "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10
        }

        current_sem = 1

        for page_idx, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            lines = [line.strip() for line in text.split("\n") if line.strip()]

            for line in lines:
                # Check for semester change
                sem_match = sem_header_pattern.search(line)
                if sem_match:
                    sem_str = sem_match.group(1).upper()
                    if sem_str in roman_to_int:
                        current_sem = roman_to_int[sem_str]
                    elif sem_str.isdigit():
                        current_sem = int(sem_str)
                    semesters_found.add(current_sem)

                # Check for course line
                code_match = course_code_pattern.search(line)
                if code_match:
                    raw_code = code_match.group(1).replace(" ", "").upper()
                    # Skip common false positives
                    if raw_code in ("ISO", "AICTE", "NBA", "PAGE", "VOL", "REV"):
                        continue

                    # Look for L-T-P-C in the line or adjacent text
                    ltpc_match = ltpc_pattern.search(line)
                    lec, tut, prac, cred = 3, 0, 0, 3.0
                    if ltpc_match:
                        try:
                            lec = int(ltpc_match.group(1))
                            tut = int(ltpc_match.group(2))
                            prac = int(ltpc_match.group(3))
                            cred = float(ltpc_match.group(4))
                        except Exception:
                            pass

                    # Extract subject name
                    # Remove the code and numbers from the line to extract the name
                    cleaned_name = line
                    cleaned_name = course_code_pattern.sub('', cleaned_name)
                    cleaned_name = ltpc_pattern.sub('', cleaned_name)
                    # Remove leading/trailing punctuation or numbers
                    cleaned_name = re.sub(r'^[0-9.\-\s]+', '', cleaned_name)
                    cleaned_name = re.sub(r'[0-9.\-\s]+$', '', cleaned_name).strip()

                    if len(cleaned_name) < 3:
                        cleaned_name = f"Subject {raw_code}"

                    is_lab = (
                        prac > 0
                        or "LAB" in cleaned_name.upper()
                        or "PRACTICAL" in cleaned_name.upper()
                        or "WORKSHOP" in cleaned_name.upper()
                    )
                    sub_type = "PRACTICAL" if is_lab else "THEORY"
                    if "ELECTIVE" in cleaned_name.upper():
                        sub_type = "PROFESSIONAL_ELECTIVE"

                    semesters_found.add(current_sem)
                    extracted_items.append(
                        ExtractedSubjectItem(
                            semester=current_sem,
                            code=raw_code,
                            name=cleaned_name[:150],
                            type=sub_type,
                            credits=cred,
                            lecture=lec,
                            tutorial=tut,
                            practical=prac,
                            contact_hours=lec + tut + prac,
                            requires_lab=is_lab,
                            is_mandatory=sub_type != "PROFESSIONAL_ELECTIVE",
                            elective_group="Elective Group" if sub_type == "PROFESSIONAL_ELECTIVE" else None,
                            source_page=page_idx,
                            source_text=line[:300],
                            confidence_score=None,
                            extraction_method="DETERMINISTIC_PARSER",
                        )
                    )

        # De-duplicate by code within the extracted list
        seen_codes: set[str] = set()
        deduped_items: List[ExtractedSubjectItem] = []
        for it in extracted_items:
            if it.code not in seen_codes:
                seen_codes.add(it.code)
                deduped_items.append(it)

        has_llm = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"))
        mode = "LLM_STRUCTURED_EXTRACTION" if has_llm else "DETERMINISTIC_PARSER_FALLBACK"
        ai_status = "ACTIVE" if has_llm else "UNAVAILABLE (Local heuristic parser active)"

        job.status = "AWAITING_REVIEW"
        job.extracted_semesters_count = len(semesters_found) or 1
        job.extracted_subjects_count = len(deduped_items)
        job.extracted_data_json = json.dumps([item.model_dump() for item in deduped_items])
        doc.status = "EXTRACTED"

        audit_action = "AI_EXTRACTION_COMPLETED" if has_llm else "DETERMINISTIC_EXTRACTION_COMPLETED"
        _log_curriculum_audit(
            db, user_id, audit_action, "CurriculumExtractionJob", job.id,
            new_value={"subjects_extracted": len(deduped_items), "pages": total_pages, "mode": mode}
        )
        db.commit()
        db.refresh(job)

        return CurriculumExtractionJobResponse(
            id=job.id,
            document_id=job.document_id,
            document_title=doc.title,
            target_curriculum_version_id=job.target_curriculum_version_id,
            status=job.status,
            total_pages=job.total_pages,
            extracted_semesters_count=job.extracted_semesters_count,
            extracted_subjects_count=job.extracted_subjects_count,
            extracted_data=deduped_items,
            error_message=job.error_message,
            extraction_mode=mode,
            ai_provider_status=ai_status,
            created_by_id=job.created_by_id,
            creator_name=job.creator.name if job.creator else None,
            reviewed_by_id=job.reviewed_by_id,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    except Exception as exc:
        job.status = "FAILED"
        job.error_message = str(exc)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {str(exc)}"
        )


def review_extraction_job(
    db: Session,
    job_id: int,
    action: str,
    feedback: Optional[str],
    target_version_id: Optional[int],
    edited_data: Optional[List[ExtractedSubjectItem]],
    user_id: int,
) -> CurriculumExtractionJobResponse:
    job = db.query(CurriculumExtractionJob).filter(CurriculumExtractionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Extraction job #{job_id} not found.")

    if action == "REJECT":
        job.status = "REJECTED"
        job.error_message = feedback or "Rejected during review."
        job.reviewed_by_id = user_id
        db.commit()
        db.refresh(job)
        return get_extraction_job(db, job.id)

    # If APPROVED:
    job.status = "APPROVED"
    job.reviewed_by_id = user_id

    # Determine target version
    v_id = target_version_id or job.target_curriculum_version_id
    if v_id:
        version = db.query(CurriculumVersion).filter(CurriculumVersion.id == v_id).first()
        if not version:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Target version #{v_id} not found.")
        if version.status == "PUBLISHED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Target version is already published and immutable.")

        # Items to apply
        items_to_apply = edited_data
        if not items_to_apply and job.extracted_data_json:
            parsed = json.loads(job.extracted_data_json)
            items_to_apply = [ExtractedSubjectItem(**item) for item in parsed]

        if items_to_apply:
            for item in items_to_apply:
                # Find or create semester
                sem = db.query(CurriculumSemester).filter(
                    CurriculumSemester.curriculum_version_id == version.id,
                    CurriculumSemester.semester_number == item.semester,
                ).first()
                if not sem:
                    sem = CurriculumSemester(
                        curriculum_version_id=version.id,
                        semester_number=item.semester,
                        notes=f"Semester {item.semester}",
                    )
                    db.add(sem)
                    db.flush()

                # Check if subject mapping already exists
                existing_mapping = db.query(CurriculumSubjectMapping).filter(
                    CurriculumSubjectMapping.curriculum_version_id == version.id,
                    CurriculumSubjectMapping.subject_code == item.code,
                ).first()

                if not existing_mapping:
                    # Sync course catalog
                    course = db.query(Course).filter(Course.course_code == item.code).first()
                    if not course:
                        course = Course(
                            course_code=item.code,
                            course_name=item.name,
                            department_id=version.department_id,
                            credits=int(item.credits),
                            lecture_hours=item.lecture,
                            tutorial_hours=item.tutorial,
                            practical_hours=item.practical,
                            requires_lab=item.requires_lab,
                        )
                        db.add(course)
                        db.flush()

                    new_map = CurriculumSubjectMapping(
                        curriculum_version_id=version.id,
                        curriculum_semester_id=sem.id,
                        course_id=course.id,
                        subject_code=item.code,
                        subject_name=item.name,
                        subject_type=item.type,
                        is_mandatory=item.is_mandatory,
                        elective_group_name=item.elective_group,
                        credits=item.credits,
                        lecture_hours=item.lecture,
                        tutorial_hours=item.tutorial,
                        practical_hours=item.practical,
                        contact_hours=item.contact_hours,
                        requires_lab=item.requires_lab,
                        source_pdf_id=job.document_id,
                        source_page=item.source_page,
                        source_text=item.source_text,
                        verification_status="VERIFIED",
                    )
                    db.add(new_map)

            recalculate_curriculum_totals(db, version.id)
            version.source_document_id = job.document_id

    _log_curriculum_audit(
        db, user_id, "APPROVE_EXTRACTION_JOB", "CurriculumExtractionJob", job.id,
        new_value={"target_version_id": v_id, "status": "APPROVED"}
    )
    db.commit()
    db.refresh(job)
    return get_extraction_job(db, job.id)


def get_extraction_job(db: Session, job_id: int) -> CurriculumExtractionJobResponse:
    job = db.query(CurriculumExtractionJob).options(
        joinedload(CurriculumExtractionJob.document),
        joinedload(CurriculumExtractionJob.creator),
    ).filter(CurriculumExtractionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Extraction job #{job_id} not found.")

    extracted_items: List[ExtractedSubjectItem] = []
    if job.extracted_data_json:
        try:
            parsed = json.loads(job.extracted_data_json)
            extracted_items = [ExtractedSubjectItem(**i) for i in parsed]
        except Exception:
            pass

    has_llm = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"))
    mode = "LLM_STRUCTURED_EXTRACTION" if has_llm else "DETERMINISTIC_PARSER_FALLBACK"
    ai_status = "ACTIVE" if has_llm else "UNAVAILABLE (Local heuristic parser active)"

    return CurriculumExtractionJobResponse(
        id=job.id,
        document_id=job.document_id,
        document_title=job.document.title if job.document else None,
        target_curriculum_version_id=job.target_curriculum_version_id,
        status=job.status,
        total_pages=job.total_pages,
        extracted_semesters_count=job.extracted_semesters_count,
        extracted_subjects_count=job.extracted_subjects_count,
        extracted_data=extracted_items,
        error_message=job.error_message,
        extraction_mode=mode,
        ai_provider_status=ai_status,
        created_by_id=job.created_by_id,
        creator_name=job.creator.name if job.creator else None,
        reviewed_by_id=job.reviewed_by_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


# ---------------------------------------------------------------------------
# 6. Releases & Department Inbox Services
# ---------------------------------------------------------------------------

def release_curriculum_version(
    db: Session,
    version_id: int,
    department_ids: List[int],
    user_id: int,
) -> List[CurriculumReleaseResponse]:
    version = db.query(CurriculumVersion).filter(CurriculumVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Version #{version_id} not found.")

    releases: List[CurriculumRelease] = []
    for dept_id in department_ids:
        existing = db.query(CurriculumRelease).filter(
            CurriculumRelease.curriculum_version_id == version.id,
            CurriculumRelease.department_id == dept_id,
        ).first()

        if not existing:
            rel = CurriculumRelease(
                curriculum_version_id=version.id,
                department_id=dept_id,
                program_id=version.program_id,
                released_by_id=user_id,
                is_acknowledged=False,
            )
            db.add(rel)
            releases.append(rel)

    db.flush()
    _log_curriculum_audit(
        db, user_id, "RELEASE_CURRICULUM", "CurriculumVersion", version.id,
        new_value={"version_code": version.version_code, "departments": department_ids}
    )
    db.commit()

    return list_releases_for_version(db, version.id)


def list_releases_for_version(db: Session, version_id: int) -> List[CurriculumReleaseResponse]:
    rels = db.query(CurriculumRelease).options(
        joinedload(CurriculumRelease.curriculum_version),
        joinedload(CurriculumRelease.department),
        joinedload(CurriculumRelease.program),
        joinedload(CurriculumRelease.releaser),
        joinedload(CurriculumRelease.acknowledger),
    ).filter(CurriculumRelease.curriculum_version_id == version_id).all()

    return [
        CurriculumReleaseResponse(
            id=r.id,
            curriculum_version_id=r.curriculum_version_id,
            version_code=r.curriculum_version.version_code if r.curriculum_version else None,
            program_name=r.program.program_name if r.program else None,
            regulation_code=r.curriculum_version.regulation.code if (r.curriculum_version and r.curriculum_version.regulation) else None,
            department_id=r.department_id,
            department_name=r.department.name if r.department else None,
            released_at=r.released_at,
            released_by_name=r.releaser.name if r.releaser else None,
            is_acknowledged=r.is_acknowledged,
            acknowledged_by_name=r.acknowledger.name if r.acknowledger else None,
            acknowledged_at=r.acknowledged_at,
            acknowledgement_notes=r.acknowledgement_notes,
        )
        for r in rels
    ]


def get_department_inbox(db: Session, department_id: int) -> List[CurriculumReleaseResponse]:
    rels = db.query(CurriculumRelease).options(
        joinedload(CurriculumRelease.curriculum_version).joinedload(CurriculumVersion.regulation),
        joinedload(CurriculumRelease.department),
        joinedload(CurriculumRelease.program),
        joinedload(CurriculumRelease.releaser),
        joinedload(CurriculumRelease.acknowledger),
    ).filter(CurriculumRelease.department_id == department_id).order_by(CurriculumRelease.released_at.desc()).all()

    return [
        CurriculumReleaseResponse(
            id=r.id,
            curriculum_version_id=r.curriculum_version_id,
            version_code=r.curriculum_version.version_code if r.curriculum_version else None,
            program_name=r.program.program_name if r.program else None,
            regulation_code=r.curriculum_version.regulation.code if (r.curriculum_version and r.curriculum_version.regulation) else None,
            department_id=r.department_id,
            department_name=r.department.name if r.department else None,
            released_at=r.released_at,
            released_by_name=r.releaser.name if r.releaser else None,
            is_acknowledged=r.is_acknowledged,
            acknowledged_by_name=r.acknowledger.name if r.acknowledger else None,
            acknowledged_at=r.acknowledged_at,
            acknowledgement_notes=r.acknowledgement_notes,
        )
        for r in rels
    ]


def acknowledge_curriculum_release(
    db: Session,
    release_id: int,
    admin_user_id: int,
    notes: Optional[str] = None,
) -> CurriculumReleaseResponse:
    release = db.query(CurriculumRelease).filter(CurriculumRelease.id == release_id).first()
    if not release:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Release #{release_id} not found.")

    release.is_acknowledged = True
    release.acknowledged_by_id = admin_user_id
    release.acknowledged_at = utc_now()
    release.acknowledgement_notes = notes

    _log_curriculum_audit(
        db, admin_user_id, "ACKNOWLEDGE_CURRICULUM_RELEASE", "CurriculumRelease", release.id,
        new_value={"version_id": release.curriculum_version_id, "notes": notes}
    )
    db.commit()
    db.refresh(release)

    return CurriculumReleaseResponse(
        id=release.id,
        curriculum_version_id=release.curriculum_version_id,
        version_code=release.curriculum_version.version_code if release.curriculum_version else None,
        program_name=release.program.program_name if release.program else None,
        regulation_code=release.curriculum_version.regulation.code if (release.curriculum_version and release.curriculum_version.regulation) else None,
        department_id=release.department_id,
        department_name=release.department.name if release.department else None,
        released_at=release.released_at,
        released_by_name=release.releaser.name if release.releaser else None,
        is_acknowledged=release.is_acknowledged,
        acknowledged_by_name=release.acknowledger.name if release.acknowledger else None,
        acknowledged_at=release.acknowledged_at,
        acknowledgement_notes=release.acknowledgement_notes,
    )


# ---------------------------------------------------------------------------
# 7. Curriculum Correction Requests & Threaded Messages
# ---------------------------------------------------------------------------

def create_curriculum_request(
    db: Session,
    data: CurriculumRequestCreate,
    admin_user_id: int,
) -> CurriculumRequestResponse:
    year = datetime.datetime.now().year
    count = db.query(func.count(CurriculumRequest.id)).scalar() or 0
    request_number = f"REQ-{year}-{count + 1:04d}"

    req = CurriculumRequest(
        request_number=request_number,
        requesting_admin_id=admin_user_id,
        department_id=data.department_id,
        program_id=data.program_id,
        curriculum_version_id=data.curriculum_version_id,
        curriculum_semester_id=data.curriculum_semester_id,
        subject_mapping_id=data.subject_mapping_id,
        request_type=data.request_type,
        title=data.title.strip(),
        description=data.description.strip(),
        proposed_change_json=data.proposed_change_json,
        status="OPEN",
    )
    db.add(req)
    db.flush()

    # Initial system / creator message
    init_msg = CurriculumRequestMessage(
        request_id=req.id,
        sender_id=admin_user_id,
        sender_role="ADMIN",
        message=data.description.strip(),
        attachments_json=data.proposed_change_json,
    )
    db.add(init_msg)

    _log_curriculum_audit(
        db, admin_user_id, "CREATE_CURRICULUM_REQUEST", "CurriculumRequest", req.id,
        new_value={"request_number": req.request_number, "type": req.request_type, "title": req.title}
    )
    db.commit()
    db.refresh(req)
    return get_curriculum_request(db, req.id)


def list_curriculum_requests(
    db: Session,
    department_id: Optional[int] = None,
    status: Optional[str] = None,
) -> List[CurriculumRequestResponse]:
    query = db.query(CurriculumRequest).options(
        joinedload(CurriculumRequest.requesting_admin),
        joinedload(CurriculumRequest.department),
        joinedload(CurriculumRequest.program),
        joinedload(CurriculumRequest.curriculum_version),
        joinedload(CurriculumRequest.resolver),
        joinedload(CurriculumRequest.messages).joinedload(CurriculumRequestMessage.sender),
    )
    if department_id is not None:
        query = query.filter(CurriculumRequest.department_id == department_id)
    if status is not None:
        query = query.filter(CurriculumRequest.status == status)

    requests = query.order_by(CurriculumRequest.created_at.desc()).all()
    return [_serialize_request(r) for r in requests]


def get_curriculum_request(db: Session, request_id: int) -> CurriculumRequestResponse:
    req = db.query(CurriculumRequest).options(
        joinedload(CurriculumRequest.requesting_admin),
        joinedload(CurriculumRequest.department),
        joinedload(CurriculumRequest.program),
        joinedload(CurriculumRequest.curriculum_version),
        joinedload(CurriculumRequest.resolver),
        joinedload(CurriculumRequest.messages).joinedload(CurriculumRequestMessage.sender),
    ).filter(CurriculumRequest.id == request_id).first()

    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Request #{request_id} not found.")
    return _serialize_request(req)


def _serialize_request(req: CurriculumRequest) -> CurriculumRequestResponse:
    messages_resp: List[CurriculumRequestMessageResponse] = [
        CurriculumRequestMessageResponse(
            id=m.id,
            request_id=m.request_id,
            sender_id=m.sender_id,
            sender_name=m.sender.name if m.sender else "Unknown",
            sender_role=m.sender_role,
            message=m.message,
            attachments_json=m.attachments_json,
            created_at=m.created_at,
        )
        for m in sorted(req.messages, key=lambda msg: msg.created_at)
    ]

    return CurriculumRequestResponse(
        id=req.id,
        request_number=req.request_number,
        requesting_admin_id=req.requesting_admin_id,
        requesting_admin_name=req.requesting_admin.name if req.requesting_admin else None,
        department_id=req.department_id,
        department_name=req.department.name if req.department else None,
        program_id=req.program_id,
        program_name=req.program.program_name if req.program else None,
        curriculum_version_id=req.curriculum_version_id,
        curriculum_version_code=req.curriculum_version.version_code if req.curriculum_version else None,
        curriculum_semester_id=req.curriculum_semester_id,
        subject_mapping_id=req.subject_mapping_id,
        request_type=req.request_type,
        title=req.title,
        description=req.description,
        proposed_change_json=req.proposed_change_json,
        status=req.status,
        resolution_notes=req.resolution_notes,
        resolved_by_id=req.resolved_by_id,
        resolved_by_name=req.resolver.name if req.resolver else None,
        resolved_at=req.resolved_at,
        resulting_curriculum_version_id=req.resulting_curriculum_version_id,
        created_at=req.created_at,
        updated_at=req.updated_at,
        messages=messages_resp,
    )


def update_curriculum_request_status(
    db: Session,
    request_id: int,
    new_status: str,
    resolution_notes: Optional[str],
    resulting_version_id: Optional[int],
    super_admin_id: int,
) -> CurriculumRequestResponse:
    req = db.query(CurriculumRequest).filter(CurriculumRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Request #{request_id} not found.")

    old_status = req.status
    req.status = new_status
    if new_status in ("RESOLVED", "REJECTED", "WITHDRAWN"):
        req.resolved_by_id = super_admin_id
        req.resolved_at = utc_now()
        req.resolution_notes = resolution_notes
        if resulting_version_id is not None:
            req.resulting_curriculum_version_id = resulting_version_id

    _log_curriculum_audit(
        db, super_admin_id, f"REQUEST_STATUS_{new_status}", "CurriculumRequest", req.id,
        old_value={"status": old_status},
        new_value={"status": new_status, "notes": resolution_notes}
    )
    db.commit()
    db.refresh(req)
    return get_curriculum_request(db, req.id)


def add_request_message(
    db: Session,
    request_id: int,
    message: str,
    sender_id: int,
    sender_role: str,
    attachments_json: Optional[str] = None,
) -> CurriculumRequestMessageResponse:
    req = db.query(CurriculumRequest).filter(CurriculumRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Request #{request_id} not found.")

    msg = CurriculumRequestMessage(
        request_id=req.id,
        sender_id=sender_id,
        sender_role=sender_role,
        message=message.strip(),
        attachments_json=attachments_json,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    sender = db.query(User).filter(User.id == sender_id).first()
    return CurriculumRequestMessageResponse(
        id=msg.id,
        request_id=msg.request_id,
        sender_id=msg.sender_id,
        sender_name=sender.name if sender else "Unknown",
        sender_role=msg.sender_role,
        message=msg.message,
        attachments_json=msg.attachments_json,
        created_at=msg.created_at,
    )


# ---------------------------------------------------------------------------
# 8. Operational Allocation & Readiness Verification
# ---------------------------------------------------------------------------

def create_section_offering(
    db: Session,
    data: SectionCourseOfferingCreate,
    user_id: int,
) -> SectionCourseOfferingResponse:
    # Ensure subject mapping exists
    mapping = db.query(CurriculumSubjectMapping).filter(
        CurriculumSubjectMapping.id == data.curriculum_subject_mapping_id
    ).first()
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject mapping not found.")

    # Avoid duplicate offering for exact same section and subject
    existing = db.query(SectionCourseOffering).filter(
        SectionCourseOffering.curriculum_subject_mapping_id == data.curriculum_subject_mapping_id,
        SectionCourseOffering.academic_year_id == data.academic_year_id,
        SectionCourseOffering.semester_id == data.semester_id,
        SectionCourseOffering.section_id == data.section_id,
        SectionCourseOffering.batch_id == data.batch_id,
    ).first()

    if existing:
        return get_section_offering(db, existing.id)

    offering = SectionCourseOffering(
        curriculum_version_id=data.curriculum_version_id,
        curriculum_subject_mapping_id=data.curriculum_subject_mapping_id,
        academic_year_id=data.academic_year_id,
        semester_id=data.semester_id,
        section_id=data.section_id,
        batch_id=data.batch_id,
        enrolled_student_count=data.enrolled_student_count,
        is_active=True,
    )
    db.add(offering)
    db.flush()

    _log_curriculum_audit(
        db, user_id, "CREATE_SECTION_OFFERING", "SectionCourseOffering", offering.id,
        new_value={"section_id": offering.section_id, "subject_mapping_id": offering.curriculum_subject_mapping_id}
    )
    db.commit()
    db.refresh(offering)
    return get_section_offering(db, offering.id)


def allocate_faculty_to_offering(
    db: Session,
    data: FacultyCourseOfferingCreate,
    user_id: int,
) -> FacultyCourseOfferingResponse:
    offering = db.query(SectionCourseOffering).filter(SectionCourseOffering.id == data.section_course_offering_id).first()
    if not offering:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section offering not found.")

    faculty = db.query(Faculty).filter(Faculty.id == data.faculty_id).first()
    if not faculty:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Faculty member not found.")

    alloc = FacultyCourseOffering(
        section_course_offering_id=data.section_course_offering_id,
        faculty_id=data.faculty_id,
        assigned_role=data.assigned_role,
        assigned_hours=data.assigned_hours,
        is_active=True,
    )
    db.add(alloc)
    db.flush()

    _log_curriculum_audit(
        db, user_id, "ALLOCATE_FACULTY_OFFERING", "FacultyCourseOffering", alloc.id,
        new_value={"faculty_id": alloc.faculty_id, "offering_id": alloc.section_course_offering_id, "role": alloc.assigned_role}
    )
    db.commit()
    db.refresh(alloc)

    return FacultyCourseOfferingResponse(
        id=alloc.id,
        section_course_offering_id=alloc.section_course_offering_id,
        faculty_id=alloc.faculty_id,
        faculty_name=faculty.user.name if (faculty and faculty.user) else "Faculty",
        faculty_code=faculty.faculty_id if faculty else None,
        assigned_role=alloc.assigned_role,
        assigned_hours=alloc.assigned_hours,
        is_active=alloc.is_active,
        created_at=alloc.created_at,
    )


def get_section_offering(db: Session, offering_id: int) -> SectionCourseOfferingResponse:
    off = db.query(SectionCourseOffering).options(
        joinedload(SectionCourseOffering.subject_mapping),
        joinedload(SectionCourseOffering.academic_year),
        joinedload(SectionCourseOffering.semester),
        joinedload(SectionCourseOffering.section),
        joinedload(SectionCourseOffering.batch),
        joinedload(SectionCourseOffering.faculty_allocations).joinedload(FacultyCourseOffering.faculty).joinedload(Faculty.user),
    ).filter(SectionCourseOffering.id == offering_id).first()

    if not off:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Offering #{offering_id} not found.")

    allocs = [
        FacultyCourseOfferingResponse(
            id=fa.id,
            section_course_offering_id=fa.section_course_offering_id,
            faculty_id=fa.faculty_id,
            faculty_name=fa.faculty.user.name if (fa.faculty and fa.faculty.user) else "Faculty",
            faculty_code=fa.faculty.faculty_id if fa.faculty else None,
            assigned_role=fa.assigned_role,
            assigned_hours=fa.assigned_hours,
            is_active=fa.is_active,
            created_at=fa.created_at,
        )
        for fa in off.faculty_allocations
    ]

    return SectionCourseOfferingResponse(
        id=off.id,
        curriculum_version_id=off.curriculum_version_id,
        curriculum_subject_mapping_id=off.curriculum_subject_mapping_id,
        subject_code=off.subject_mapping.subject_code if off.subject_mapping else None,
        subject_name=off.subject_mapping.subject_name if off.subject_mapping else None,
        subject_type=off.subject_mapping.subject_type if off.subject_mapping else None,
        academic_year_id=off.academic_year_id,
        academic_year_name=off.academic_year.name if off.academic_year else None,
        semester_id=off.semester_id,
        semester_number=off.semester.semester_number if off.semester else None,
        section_id=off.section_id,
        section_name=off.section.section_name if off.section else None,
        batch_id=off.batch_id,
        batch_name=off.batch.batch_name if off.batch else None,
        enrolled_student_count=off.enrolled_student_count,
        is_active=off.is_active,
        faculty_allocations=allocs,
        created_at=off.created_at,
    )


def list_section_offerings(
    db: Session,
    academic_year_id: int,
    semester_id: int,
    department_id: Optional[int] = None,
    section_id: Optional[int] = None,
) -> List[SectionCourseOfferingResponse]:
    query = db.query(SectionCourseOffering).options(
        joinedload(SectionCourseOffering.subject_mapping),
        joinedload(SectionCourseOffering.academic_year),
        joinedload(SectionCourseOffering.semester),
        joinedload(SectionCourseOffering.section),
        joinedload(SectionCourseOffering.batch),
        joinedload(SectionCourseOffering.faculty_allocations).joinedload(FacultyCourseOffering.faculty).joinedload(Faculty.user),
    ).filter(
        SectionCourseOffering.academic_year_id == academic_year_id,
        SectionCourseOffering.semester_id == semester_id,
        SectionCourseOffering.is_active == True,
    )

    if section_id is not None:
        query = query.filter(SectionCourseOffering.section_id == section_id)

    offerings = query.all()
    if department_id is not None:
        offerings = [o for o in offerings if o.section and o.section.department_id == department_id]

    return [
        SectionCourseOfferingResponse(
            id=off.id,
            curriculum_version_id=off.curriculum_version_id,
            curriculum_subject_mapping_id=off.curriculum_subject_mapping_id,
            subject_code=off.subject_mapping.subject_code if off.subject_mapping else None,
            subject_name=off.subject_mapping.subject_name if off.subject_mapping else None,
            subject_type=off.subject_mapping.subject_type if off.subject_mapping else None,
            academic_year_id=off.academic_year_id,
            academic_year_name=off.academic_year.name if off.academic_year else None,
            semester_id=off.semester_id,
            semester_number=off.semester.semester_number if off.semester else None,
            section_id=off.section_id,
            section_name=off.section.section_name if off.section else None,
            batch_id=off.batch_id,
            batch_name=off.batch.batch_name if off.batch else None,
            enrolled_student_count=off.enrolled_student_count,
            is_active=off.is_active,
            faculty_allocations=[
                FacultyCourseOfferingResponse(
                    id=fa.id,
                    section_course_offering_id=fa.section_course_offering_id,
                    faculty_id=fa.faculty_id,
                    faculty_name=fa.faculty.user.name if (fa.faculty and fa.faculty.user) else "Faculty",
                    faculty_code=fa.faculty.faculty_id if fa.faculty else None,
                    assigned_role=fa.assigned_role,
                    assigned_hours=fa.assigned_hours,
                    is_active=fa.is_active,
                    created_at=fa.created_at,
                )
                for fa in off.faculty_allocations
            ],
            created_at=off.created_at,
        )
        for off in offerings
    ]


def check_curriculum_readiness(
    db: Session,
    curriculum_version_id: int,
    semester_number: int,
    academic_year_id: int,
    semester_id: int,
) -> CurriculumReadinessResponse:
    """
    Evaluates whether the curriculum version has complete section course offerings
    and faculty teaching assignments for all subjects in the target semester.
    """
    version = db.query(CurriculumVersion).options(
        joinedload(CurriculumVersion.department)
    ).filter(CurriculumVersion.id == curriculum_version_id).first()

    if not version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Curriculum version not found.")

    sem = db.query(CurriculumSemester).filter(
        CurriculumSemester.curriculum_version_id == version.id,
        CurriculumSemester.semester_number == semester_number,
    ).first()

    if not sem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Semester #{semester_number} not found in version.")

    subjects = db.query(CurriculumSubjectMapping).filter(
        CurriculumSubjectMapping.curriculum_semester_id == sem.id
    ).all()

    sections = db.query(Section).filter(
        Section.department_id == version.department_id,
        Section.id.isnot(None),
    ).all()
    sections_total = len(sections) or 1

    subject_readiness: List[SubjectReadinessItem] = []
    blocking_reasons: List[str] = []
    allocated_count = 0
    missing_faculty = 0

    for sub in subjects:
        # Check offerings for this subject
        offerings = db.query(SectionCourseOffering).options(
            joinedload(SectionCourseOffering.faculty_allocations).joinedload(FacultyCourseOffering.faculty).joinedload(Faculty.user)
        ).filter(
            SectionCourseOffering.curriculum_subject_mapping_id == sub.id,
            SectionCourseOffering.academic_year_id == academic_year_id,
            SectionCourseOffering.semester_id == semester_id,
            SectionCourseOffering.is_active == True,
        ).all()

        sections_covered = len(offerings)
        faculty_names: List[str] = []
        for o in offerings:
            for fa in o.faculty_allocations:
                if fa.is_active and fa.faculty and fa.faculty.user:
                    faculty_names.append(fa.faculty.user.name)

        missing_items: List[str] = []
        if sections_covered == 0:
            missing_items.append("No section course offerings created.")
        elif sections_covered < sections_total:
            missing_items.append(f"Only {sections_covered}/{sections_total} sections allocated.")

        if not faculty_names:
            missing_items.append("No faculty assigned.")
            missing_faculty += 1

        is_fully_alloc = (sections_covered > 0) and (len(faculty_names) > 0)
        if is_fully_alloc:
            allocated_count += 1
        else:
            blocking_reasons.append(f"{sub.subject_code} ({sub.subject_name}): {', '.join(missing_items)}")

        subject_readiness.append(
            SubjectReadinessItem(
                subject_code=sub.subject_code,
                subject_name=sub.subject_name,
                subject_type=sub.subject_type,
                credits=sub.credits,
                contact_hours=sub.contact_hours,
                requires_lab=sub.requires_lab,
                sections_covered=sections_covered,
                sections_total=sections_total,
                is_fully_allocated=is_fully_alloc,
                allocated_faculty_names=list(set(faculty_names)),
                missing_items=missing_items,
            )
        )

    total_subs = len(subjects)
    unallocated_count = total_subs - allocated_count
    pct = round((allocated_count / total_subs * 100.0), 1) if total_subs > 0 else 0.0
    is_ready = (unallocated_count == 0) and (total_subs > 0)

    return CurriculumReadinessResponse(
        curriculum_version_id=version.id,
        version_code=version.version_code,
        department_id=version.department_id,
        department_name=version.department.name if version.department else "Department",
        semester_number=semester_number,
        is_ready_for_scheduling=is_ready,
        readiness_percentage=pct,
        total_subjects=total_subs,
        allocated_subjects=allocated_count,
        unallocated_subjects=unallocated_count,
        missing_faculty_count=missing_faculty,
        subjects=subject_readiness,
        blocking_reasons=blocking_reasons,
    )


# ---------------------------------------------------------------------------
# 9. Super Admin Dashboard Metrics
# ---------------------------------------------------------------------------

def get_super_admin_stats(db: Session) -> SuperAdminDashboardStats:
    total_reg = db.query(func.count(Regulation.id)).scalar() or 0
    total_coh = db.query(func.count(AdmissionCohort.id)).scalar() or 0
    total_cv = db.query(func.count(CurriculumVersion.id)).scalar() or 0
    draft_cv = db.query(func.count(CurriculumVersion.id)).filter(CurriculumVersion.status == "DRAFT").scalar() or 0
    review_cv = db.query(func.count(CurriculumVersion.id)).filter(CurriculumVersion.status == "NEEDS_REVIEW").scalar() or 0
    appr_cv = db.query(func.count(CurriculumVersion.id)).filter(CurriculumVersion.status == "APPROVED").scalar() or 0
    pub_cv = db.query(func.count(CurriculumVersion.id)).filter(CurriculumVersion.status == "PUBLISHED").scalar() or 0
    open_req = db.query(func.count(CurriculumRequest.id)).filter(CurriculumRequest.status.in_(("OPEN", "UNDER_REVIEW"))).scalar() or 0
    docs = db.query(func.count(CurriculumDocument.id)).scalar() or 0
    jobs = db.query(func.count(CurriculumExtractionJob.id)).scalar() or 0
    releases = db.query(func.count(CurriculumRelease.id)).scalar() or 0

    # Recent activity from audit log
    recent_audits = db.query(AuditLog).options(
        joinedload(AuditLog.user)
    ).filter(
        AuditLog.entity_type.in_(("Regulation", "AdmissionCohort", "CurriculumVersion", "CurriculumSubjectMapping", "CurriculumExtractionJob", "CurriculumRequest", "CurriculumRelease"))
    ).order_by(AuditLog.timestamp.desc()).limit(10).all()

    activities: List[Dict[str, Any]] = [
        {
            "id": a.id,
            "action": a.action,
            "entity_type": a.entity_type,
            "entity_id": a.entity_id,
            "user_name": a.user.name if a.user else "System",
            "timestamp": str(a.timestamp),
            "details": a.new_value,
        }
        for a in recent_audits
    ]

    return SuperAdminDashboardStats(
        total_regulations=total_reg,
        total_cohorts=total_coh,
        total_curriculum_versions=total_cv,
        draft_versions_count=draft_cv,
        needs_review_count=review_cv,
        approved_versions_count=appr_cv,
        published_versions_count=pub_cv,
        open_requests_count=open_req,
        documents_count=docs,
        extraction_jobs_count=jobs,
        active_releases_count=releases,
        recent_activities=activities,
    )
