"""
backend/routes/curriculum.py
----------------------------
API Routes for:
1. Super Admin Central Curriculum Governance & Academic Structure
2. AI Syllabus PDF Upload, Extraction Studio & Review
3. Super Admin Requests Inbox & Admin Correction Requests
4. Admin Department Curriculum Inbox & Acknowledgement
5. Admin Section-Course & Faculty Offerings Allocation
6. Timetable Scheduling Readiness Preflight
7. Scoped Read-Only Curriculum access for Students and Faculty
"""

from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from backend.database import get_db
from backend.dependencies import get_current_user, require_role
from backend.models.academic import Faculty, Student
from backend.models.curriculum import (
    CurriculumSubjectMapping,
    CurriculumVersion,
    FacultyCourseOffering,
    SectionCourseOffering,
)
from backend.models.identity import User
from backend.schemas.curriculum import (
    AdmissionCohortCreate,
    AdmissionCohortResponse,
    AdmissionCohortUpdate,
    CurriculumExtractionJobResponse,
    CurriculumReadinessResponse,
    CurriculumReleaseAcknowledge,
    CurriculumReleaseCreate,
    CurriculumReleaseResponse,
    CurriculumRequestCreate,
    CurriculumRequestMessageCreate,
    CurriculumRequestMessageResponse,
    CurriculumRequestResponse,
    CurriculumRequestStatusUpdate,
    CurriculumSubjectMappingCreate,
    CurriculumSubjectMappingResponse,
    CurriculumSubjectMappingUpdate,
    CurriculumVersionCreate,
    CurriculumVersionPublishRequest,
    CurriculumVersionResponse,
    CurriculumVersionStatusUpdate,
    CurriculumVersionSummary,
    CurriculumVersionUpdate,
    ExtractionReviewRequest,
    FacultyCourseOfferingCreate,
    FacultyCourseOfferingResponse,
    RegulationCreate,
    RegulationResponse,
    RegulationUpdate,
    SectionCourseOfferingCreate,
    SectionCourseOfferingResponse,
    SuperAdminDashboardStats,
)
from backend.services import curriculum_service


# ---------------------------------------------------------------------------
# Router Definitions
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/curriculum", tags=["Curriculum"])
super_admin_router = APIRouter(prefix="/super-admin", tags=["Super Admin Curriculum"])
admin_curriculum_router = APIRouter(prefix="/admin/curriculum", tags=["Admin Curriculum Allocation"])


# ===========================================================================
# 1. SUPER ADMIN: Academic Structure (Regulations & Cohorts)
# ===========================================================================

@super_admin_router.get("/regulations", response_model=List[RegulationResponse])
def list_regulations_endpoint(
    department_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.list_regulations(db, department_id=department_id, is_active=is_active)


@super_admin_router.post("/regulations", response_model=RegulationResponse, status_code=status.HTTP_201_CREATED)
def create_regulation_endpoint(
    data: RegulationCreate,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.create_regulation(db, data, user_id=super_admin.id)


@super_admin_router.get("/regulations/{regulation_id}", response_model=RegulationResponse)
def get_regulation_endpoint(
    regulation_id: int,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    reg = curriculum_service.get_regulation(db, regulation_id)
    return RegulationResponse(
        id=reg.id,
        code=reg.code,
        name=reg.name,
        department_id=reg.department_id,
        department_name=reg.department.name if reg.department else "All Departments",
        effective_year=reg.effective_year,
        is_active=reg.is_active,
        description=reg.description,
        cohorts_count=len(reg.cohorts),
        curriculum_versions_count=len(reg.curriculum_versions),
        created_at=reg.created_at,
        updated_at=reg.updated_at,
    )


@super_admin_router.put("/regulations/{regulation_id}", response_model=RegulationResponse)
def update_regulation_endpoint(
    regulation_id: int,
    data: RegulationUpdate,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.update_regulation(db, regulation_id, data, user_id=super_admin.id)


@super_admin_router.get("/cohorts", response_model=List[AdmissionCohortResponse])
def list_cohorts_endpoint(
    program_id: Optional[int] = Query(None),
    regulation_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.list_cohorts(db, program_id=program_id, regulation_id=regulation_id, is_active=is_active)


@super_admin_router.post("/cohorts", response_model=AdmissionCohortResponse, status_code=status.HTTP_201_CREATED)
def create_cohort_endpoint(
    data: AdmissionCohortCreate,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.create_cohort(db, data, user_id=super_admin.id)


@super_admin_router.get("/cohorts/{cohort_id}", response_model=AdmissionCohortResponse)
def get_cohort_endpoint(
    cohort_id: int,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    c = curriculum_service.get_cohort(db, cohort_id)
    return AdmissionCohortResponse(
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


@super_admin_router.put("/cohorts/{cohort_id}", response_model=AdmissionCohortResponse)
def update_cohort_endpoint(
    cohort_id: int,
    data: AdmissionCohortUpdate,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.update_cohort(db, cohort_id, data, user_id=super_admin.id)


# ===========================================================================
# 2. SUPER ADMIN: Curriculum Versions & Subject Mappings
# ===========================================================================

@super_admin_router.get("/curriculum-versions", response_model=List[CurriculumVersionSummary])
def list_curriculum_versions_endpoint(
    department_id: Optional[int] = Query(None),
    program_id: Optional[int] = Query(None),
    regulation_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.list_curriculum_versions(
        db, department_id=department_id, program_id=program_id, regulation_id=regulation_id, status=status
    )


@super_admin_router.post("/curriculum-versions", response_model=CurriculumVersionResponse, status_code=status.HTTP_201_CREATED)
def create_curriculum_version_endpoint(
    data: CurriculumVersionCreate,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.create_curriculum_version(db, data, user_id=super_admin.id)


@super_admin_router.get("/curriculum-versions/{version_id}", response_model=CurriculumVersionResponse)
def get_curriculum_version_endpoint(
    version_id: int,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.get_curriculum_version(db, version_id)


@super_admin_router.post("/curriculum-versions/{version_id}/status", response_model=CurriculumVersionResponse)
def update_version_status_endpoint(
    version_id: int,
    data: CurriculumVersionStatusUpdate,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.update_curriculum_version_status(
        db, version_id, new_status=data.status, notes=data.review_notes, user_id=super_admin.id
    )


@super_admin_router.post("/curriculum-versions/{version_id}/publish", response_model=CurriculumVersionResponse)
def publish_version_endpoint(
    version_id: int,
    data: Optional[CurriculumReleaseCreate] = None,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    dept_ids = data.department_ids if data else None
    return curriculum_service.publish_curriculum_version(db, version_id, user_id=super_admin.id, department_ids=dept_ids)


@super_admin_router.post("/curriculum-versions/{version_id}/revise", response_model=CurriculumVersionResponse, status_code=status.HTTP_201_CREATED)
def revise_version_endpoint(
    version_id: int,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.create_new_revision(db, version_id, user_id=super_admin.id)


@super_admin_router.post("/curriculum-versions/{version_id}/subjects", response_model=CurriculumSubjectMappingResponse, status_code=status.HTTP_201_CREATED)
def add_subject_mapping_endpoint(
    version_id: int,
    data: CurriculumSubjectMappingCreate,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.add_subject_mapping(db, version_id, data, user_id=super_admin.id)


@super_admin_router.put("/subjects/{mapping_id}", response_model=CurriculumSubjectMappingResponse)
def update_subject_mapping_endpoint(
    mapping_id: int,
    data: CurriculumSubjectMappingUpdate,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.update_subject_mapping(db, mapping_id, data, user_id=super_admin.id)


@super_admin_router.delete("/subjects/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subject_mapping_endpoint(
    mapping_id: int,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    curriculum_service.delete_subject_mapping(db, mapping_id, user_id=super_admin.id)
    return None


# ===========================================================================
# 3. SUPER ADMIN: PDF Upload & AI Syllabus Extraction Studio
# ===========================================================================

@super_admin_router.post("/documents/upload")
async def upload_curriculum_document_endpoint(
    file: UploadFile = File(...),
    title: str = Form(...),
    department_id: Optional[int] = Form(None),
    program_id: Optional[int] = Form(None),
    regulation_id: Optional[int] = Form(None),
    cohort_id: Optional[int] = Form(None),
    curriculum_version_id: Optional[int] = Form(None),
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only official institutional PDF syllabus documents are permitted."
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    doc = curriculum_service.store_curriculum_document(
        db,
        file_bytes=content,
        filename=file.filename,
        title=title,
        user_id=super_admin.id,
        department_id=department_id,
        program_id=program_id,
        regulation_id=regulation_id,
        cohort_id=cohort_id,
        curriculum_version_id=curriculum_version_id,
    )

    return {
        "id": doc.id,
        "title": doc.title,
        "file_name": doc.file_name,
        "file_hash": doc.file_hash,
        "file_size_bytes": doc.file_size_bytes,
        "status": doc.status,
        "created_at": str(doc.created_at),
    }


@super_admin_router.post("/documents/{document_id}/extract", response_model=CurriculumExtractionJobResponse)
def trigger_extraction_job_endpoint(
    document_id: int,
    target_version_id: Optional[int] = Query(None),
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.extract_curriculum_from_pdf(
        db, document_id=document_id, target_version_id=target_version_id, user_id=super_admin.id
    )


@super_admin_router.get("/extraction-jobs/{job_id}", response_model=CurriculumExtractionJobResponse)
def get_extraction_job_endpoint(
    job_id: int,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.get_extraction_job(db, job_id)


@super_admin_router.post("/extraction-jobs/{job_id}/review", response_model=CurriculumExtractionJobResponse)
def review_extraction_job_endpoint(
    job_id: int,
    data: ExtractionReviewRequest,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.review_extraction_job(
        db,
        job_id=job_id,
        action=data.action,
        feedback=data.feedback,
        target_version_id=data.target_version_id,
        edited_data=data.edited_data,
        user_id=super_admin.id,
    )


# ===========================================================================
# 4. SUPER ADMIN: Releases, Requests & Executive Dashboard
# ===========================================================================

@super_admin_router.post("/curriculum-versions/{version_id}/release", response_model=List[CurriculumReleaseResponse])
def release_version_endpoint(
    version_id: int,
    data: CurriculumReleaseCreate,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.release_curriculum_version(
        db, version_id=version_id, department_ids=data.department_ids, user_id=super_admin.id
    )


@super_admin_router.get("/requests", response_model=List[CurriculumRequestResponse])
def list_requests_super_admin_endpoint(
    department_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.list_curriculum_requests(db, department_id=department_id, status=status)


@super_admin_router.get("/requests/{request_id}", response_model=CurriculumRequestResponse)
def get_request_super_admin_endpoint(
    request_id: int,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.get_curriculum_request(db, request_id)


@super_admin_router.put("/requests/{request_id}/status", response_model=CurriculumRequestResponse)
def update_request_status_endpoint(
    request_id: int,
    data: CurriculumRequestStatusUpdate,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.update_curriculum_request_status(
        db,
        request_id=request_id,
        new_status=data.status,
        resolution_notes=data.resolution_notes,
        resulting_version_id=data.resulting_curriculum_version_id,
        super_admin_id=super_admin.id,
    )


@super_admin_router.post("/requests/{request_id}/messages", response_model=CurriculumRequestMessageResponse)
def add_request_message_super_admin_endpoint(
    request_id: int,
    data: CurriculumRequestMessageCreate,
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.add_request_message(
        db,
        request_id=request_id,
        message=data.message,
        sender_id=super_admin.id,
        sender_role="SUPER_ADMIN",
        attachments_json=data.attachments_json,
    )


@super_admin_router.get("/dashboard/stats", response_model=SuperAdminDashboardStats)
def get_dashboard_stats_endpoint(
    super_admin: User = Depends(require_role("SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.get_super_admin_stats(db)


# ===========================================================================
# 5. ADMIN: Curriculum Inbox, Operational Allocation & Requests
# ===========================================================================

@admin_curriculum_router.get("/inbox", response_model=List[CurriculumReleaseResponse])
def get_department_inbox_endpoint(
    current_user: User = Depends(require_role("ADMIN", "SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    dept_id = current_user.department_id
    if not dept_id:
        from backend.models.academic import Department
        dept = db.query(Department).first()
        dept_id = dept.id if dept else 1
    return curriculum_service.get_department_inbox(db, dept_id)


@admin_curriculum_router.post("/inbox/{release_id}/acknowledge", response_model=CurriculumReleaseResponse)
def acknowledge_release_endpoint(
    release_id: int,
    data: Optional[CurriculumReleaseAcknowledge] = None,
    current_user: User = Depends(require_role("ADMIN", "SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    notes = data.acknowledgement_notes if data else None
    return curriculum_service.acknowledge_curriculum_release(
        db, release_id=release_id, admin_user_id=current_user.id, notes=notes
    )


@admin_curriculum_router.get("/offerings", response_model=List[SectionCourseOfferingResponse])
def list_offerings_endpoint(
    academic_year_id: int = Query(...),
    semester_id: int = Query(...),
    section_id: Optional[int] = Query(None),
    current_user: User = Depends(require_role("ADMIN", "SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    dept_id = current_user.department_id
    return curriculum_service.list_section_offerings(
        db,
        academic_year_id=academic_year_id,
        semester_id=semester_id,
        department_id=dept_id,
        section_id=section_id,
    )


@admin_curriculum_router.post("/offerings", response_model=SectionCourseOfferingResponse, status_code=status.HTTP_201_CREATED)
def create_offering_endpoint(
    data: SectionCourseOfferingCreate,
    current_user: User = Depends(require_role("ADMIN", "SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.create_section_offering(db, data, user_id=current_user.id)


@admin_curriculum_router.post("/faculty-allocations", response_model=FacultyCourseOfferingResponse, status_code=status.HTTP_201_CREATED)
def allocate_faculty_endpoint(
    data: FacultyCourseOfferingCreate,
    current_user: User = Depends(require_role("ADMIN", "SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.allocate_faculty_to_offering(db, data, user_id=current_user.id)


@admin_curriculum_router.get("/readiness", response_model=CurriculumReadinessResponse)
def check_readiness_endpoint(
    curriculum_version_id: int = Query(...),
    semester_number: int = Query(...),
    academic_year_id: int = Query(...),
    semester_id: int = Query(...),
    current_user: User = Depends(require_role("ADMIN", "SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.check_curriculum_readiness(
        db,
        curriculum_version_id=curriculum_version_id,
        semester_number=semester_number,
        academic_year_id=academic_year_id,
        semester_id=semester_id,
    )


@admin_curriculum_router.post("/requests", response_model=CurriculumRequestResponse, status_code=status.HTTP_201_CREATED)
def create_admin_request_endpoint(
    data: CurriculumRequestCreate,
    current_user: User = Depends(require_role("ADMIN", "SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    return curriculum_service.create_curriculum_request(db, data, admin_user_id=current_user.id)


@admin_curriculum_router.get("/requests", response_model=List[CurriculumRequestResponse])
def list_admin_requests_endpoint(
    status: Optional[str] = Query(None),
    current_user: User = Depends(require_role("ADMIN", "SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    dept_id = current_user.department_id
    return curriculum_service.list_curriculum_requests(db, department_id=dept_id, status=status)


@admin_curriculum_router.get("/requests/{request_id}", response_model=CurriculumRequestResponse)
def get_admin_request_endpoint(
    request_id: int,
    current_user: User = Depends(require_role("ADMIN", "SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    req = curriculum_service.get_curriculum_request(db, request_id)
    if current_user.role != "SUPER_ADMIN" and current_user.department_id is not None and req.department_id != current_user.department_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to out-of-department request.")
    return req


@admin_curriculum_router.post("/requests/{request_id}/messages", response_model=CurriculumRequestMessageResponse)
def add_admin_request_message_endpoint(
    request_id: int,
    data: CurriculumRequestMessageCreate,
    current_user: User = Depends(require_role("ADMIN", "SUPER_ADMIN")),
    db: Session = Depends(get_db),
):
    req = curriculum_service.get_curriculum_request(db, request_id)
    if current_user.role != "SUPER_ADMIN" and current_user.department_id is not None and req.department_id != current_user.department_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to out-of-department request.")
    return curriculum_service.add_request_message(
        db,
        request_id=request_id,
        message=data.message,
        sender_id=current_user.id,
        sender_role=current_user.role,
        attachments_json=data.attachments_json,
    )


# ===========================================================================
# 6. SCOPED READ-ONLY ACCESS (Student, Faculty & General)
# ===========================================================================

@router.get("/versions/{version_id}", response_model=CurriculumVersionResponse)
def get_public_curriculum_version(
    version_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    version = curriculum_service.get_curriculum_version(db, version_id)
    # Students & Faculty can only view PUBLISHED curricula
    if current_user.role in ("STUDENT", "FACULTY") and version.status != "PUBLISHED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access restricted to published curricula.")
    return version


@router.get("/versions", response_model=List[CurriculumVersionSummary])
def list_published_curricula(
    department_id: Optional[int] = Query(None),
    program_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    status_filter = "PUBLISHED" if current_user.role in ("STUDENT", "FACULTY") else None
    return curriculum_service.list_curriculum_versions(
        db, department_id=department_id, program_id=program_id, status=status_filter
    )


@router.get("/student/current")
def get_student_curriculum(
    current_user: User = Depends(require_role("STUDENT")),
    db: Session = Depends(get_db),
):
    student = db.query(Student).filter(Student.user_id == current_user.id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student profile not found.")

    version_id = student.curriculum_version_id
    if not version_id:
        v = db.query(CurriculumVersion).filter(
            CurriculumVersion.status == "PUBLISHED"
        ).order_by(CurriculumVersion.version_number.desc()).first()
        if v:
            version_id = v.id

    curr = curriculum_service.get_curriculum_version(db, version_id) if version_id else None
    return {
        "student_name": current_user.name,
        "student_id": student.student_id,
        "current_semester": student.current_curriculum_semester or student.semester_id or 1,
        "curriculum": curr,
    }


@router.get("/faculty/assigned")
def get_faculty_curriculum(
    current_user: User = Depends(require_role("FACULTY")),
    db: Session = Depends(get_db),
):
    faculty = db.query(Faculty).filter(Faculty.user_id == current_user.id).first()
    if not faculty:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Faculty profile not found.")

    offerings = db.query(FacultyCourseOffering).options(
        joinedload(FacultyCourseOffering.section_offering).joinedload(SectionCourseOffering.subject_mapping)
    ).filter(
        FacultyCourseOffering.faculty_id == faculty.id,
        FacultyCourseOffering.is_active == True,
    ).all()

    assigned_items = []
    for off in offerings:
        so = off.section_offering
        sm = so.subject_mapping if so else None
        assigned_items.append({
            "offering_id": off.id,
            "subject_code": sm.subject_code if sm else None,
            "subject_name": sm.subject_name if sm else None,
            "assigned_role": off.assigned_role,
            "assigned_hours": off.assigned_hours,
        })

    return {
        "faculty_name": current_user.name,
        "faculty_code": faculty.faculty_id,
        "department_id": faculty.department_id,
        "assigned_offerings_count": len(offerings),
        "assigned_items": assigned_items,
    }
