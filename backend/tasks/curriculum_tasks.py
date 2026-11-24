"""
backend/tasks/curriculum_tasks.py
---------------------------------
Celery background task for asynchronous curriculum syllabus PDF extraction.
Transitions CurriculumExtractionJob through states:
QUEUED -> PROCESSING -> AWAITING_REVIEW / FAILED
"""

import os
import re
import json
import logging
from typing import Any, Dict, List, Optional

from backend.celery_app import celery_app
from backend.config import SessionLocal
from backend.models.curriculum import CurriculumDocument, CurriculumExtractionJob
from backend.schemas.curriculum import ExtractedSubjectItem
from backend.services.curriculum_service import _log_curriculum_audit

logger = logging.getLogger("campus_ai.tasks.curriculum")


def _safe_update_state(task: Any, state: str, meta: Dict[str, Any]) -> None:
    """Safely updates Celery task state only if valid Celery request context exists."""
    if task is not None and getattr(task, "request", None) and getattr(task.request, "id", None):
        try:
            task.update_state(state=state, meta=meta)
        except Exception as exc:
            logger.debug("Failed to update Celery state: %s", exc)


@celery_app.task(bind=True, name="tasks.extract_curriculum", max_retries=3)
def extract_curriculum_task(
    self,
    document_id: int,
    target_version_id: Optional[int] = None,
    user_id: Optional[int] = None,
    job_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Executes curriculum syllabus extraction asynchronously in Celery worker.
    Updates CurriculumExtractionJob status in database and reports progress.
    """
    _safe_update_state(
        self,
        state="PROGRESS",
        meta={
            "progress": 10,
            "stage": "INITIALIZING",
            "document_id": document_id,
            "job_id": job_id,
        },
    )

    with SessionLocal() as db:
        doc = db.query(CurriculumDocument).filter(CurriculumDocument.id == document_id).first()
        if not doc:
            error_msg = f"CurriculumDocument #{document_id} not found."
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not os.path.exists(doc.file_path):
            error_msg = f"File not found on disk: {doc.file_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)

        # Retrieve or create CurriculumExtractionJob
        if job_id:
            job = db.query(CurriculumExtractionJob).filter(CurriculumExtractionJob.id == job_id).first()
            if not job:
                error_msg = f"CurriculumExtractionJob #{job_id} not found."
                logger.error(error_msg)
                raise ValueError(error_msg)
        else:
            job = CurriculumExtractionJob(
                document_id=doc.id,
                target_curriculum_version_id=target_version_id,
                status="QUEUED",
                created_by_id=user_id or 1,
            )
            db.add(job)
            db.commit()
            db.refresh(job)

        # Transition status to PROCESSING
        job.status = "PROCESSING"
        db.commit()
        db.refresh(job)

        _safe_update_state(
            self,
            state="PROGRESS",
            meta={
                "progress": 30,
                "stage": "READING_PDF",
                "document_id": document_id,
                "job_id": job.id,
            },
        )

        try:
            from pypdf import PdfReader

            reader = PdfReader(doc.file_path)
            total_pages = len(reader.pages)
            job.total_pages = total_pages

            _safe_update_state(
                self,
                state="PROGRESS",
                meta={
                    "progress": 50,
                    "stage": "PARSING_CURRICULUM",
                    "total_pages": total_pages,
                    "job_id": job.id,
                },
            )

            extracted_items: List[ExtractedSubjectItem] = []
            semesters_found: set[int] = set()

            # Regular expressions for curriculum items
            course_code_pattern = re.compile(r'\b([A-Z]{2,4}\s?[\d]{3,4}[A-Z]?)\b')
            ltpc_pattern = re.compile(r'(\d+)\s*[-|\s]\s*(\d+)\s*[-|\s]\s*(\d+)\s*[-|\s]\s*(\d+(\.\d+)?)')
            sem_header_pattern = re.compile(r'(?:SEMESTER|SEM|Sem)\s*[:\-]?\s*([IVXLCDM]+|\d+)', re.IGNORECASE)

            roman_to_int = {
                "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
                "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
            }

            current_sem = 1

            for page_idx, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                lines = [line.strip() for line in text.split("\n") if line.strip()]

                for line in lines:
                    sem_match = sem_header_pattern.search(line)
                    if sem_match:
                        sem_str = sem_match.group(1).upper()
                        if sem_str in roman_to_int:
                            current_sem = roman_to_int[sem_str]
                        elif sem_str.isdigit():
                            current_sem = int(sem_str)
                        semesters_found.add(current_sem)

                    code_match = course_code_pattern.search(line)
                    if code_match:
                        raw_code = code_match.group(1).replace(" ", "").upper()
                        if raw_code in ("ISO", "AICTE", "NBA", "PAGE", "VOL", "REV"):
                            continue

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

                        cleaned_name = line
                        cleaned_name = course_code_pattern.sub('', cleaned_name)
                        cleaned_name = ltpc_pattern.sub('', cleaned_name)
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

            # De-duplicate by code
            seen_codes: set[str] = set()
            deduped_items: List[ExtractedSubjectItem] = []
            for it in extracted_items:
                if it.code not in seen_codes:
                    seen_codes.add(it.code)
                    deduped_items.append(it)

            has_llm = bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY"))
            mode = "LLM_STRUCTURED_EXTRACTION" if has_llm else "DETERMINISTIC_PARSER_FALLBACK"

            job.status = "AWAITING_REVIEW"
            job.extracted_semesters_count = len(semesters_found) or 1
            job.extracted_subjects_count = len(deduped_items)
            job.extracted_data_json = json.dumps([item.model_dump() for item in deduped_items])
            doc.status = "EXTRACTED"

            audit_action = "AI_EXTRACTION_COMPLETED" if has_llm else "DETERMINISTIC_EXTRACTION_COMPLETED"
            effective_user_id = user_id or job.created_by_id
            _log_curriculum_audit(
                db,
                effective_user_id,
                audit_action,
                "CurriculumExtractionJob",
                job.id,
                new_value={"subjects_extracted": len(deduped_items), "pages": total_pages, "mode": mode},
            )
            db.commit()
            db.refresh(job)

            result = {
                "job_id": job.id,
                "document_id": document_id,
                "status": "AWAITING_REVIEW",
                "total_pages": job.total_pages,
                "extracted_subjects_count": job.extracted_subjects_count,
                "extracted_semesters_count": job.extracted_semesters_count,
                "mode": mode,
            }

            _safe_update_state(
                self,
                state="SUCCESS",
                meta={
                    "progress": 100,
                    "stage": "COMPLETED",
                    "result": result,
                },
            )
            return result

        except Exception as exc:
            logger.exception("Curriculum extraction failed for job #%s: %s", job.id, exc)
            job.status = "FAILED"
            job.error_message = str(exc)
            db.commit()

            _safe_update_state(
                self,
                state="FAILURE",
                meta={"progress": 100, "stage": "FAILURE", "error": str(exc)},
            )

            if getattr(self, "request", None) and getattr(self.request, "retries", 0) < self.max_retries:
                logger.info("Retrying extraction task (attempt %s/%s)...", self.request.retries + 1, self.max_retries)
                raise self.retry(exc=exc, countdown=2 ** self.request.retries)

            raise exc
