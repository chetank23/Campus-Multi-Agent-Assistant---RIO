"""add_curriculum_and_super_admin

Revision ID: cdd3afe221f2
Revises: 9a60df141060
Create Date: 2026-11-03 19:26:20.143975

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cdd3afe221f2'
down_revision: Union[str, Sequence[str], None] = '9a60df141060'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema in correct topological dependency order."""
    # 0. Update users role check constraint to include SUPER_ADMIN
    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.create_check_constraint(
        'ck_users_role',
        'users',
        "role IN ('STUDENT','FACULTY','ADMIN','SUPER_ADMIN')"
    )

    # 1. Regulations table
    op.create_table(
        'regulations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('effective_year', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='TRUE', nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name='fk_regulations_department_id'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_regulations_code'), 'regulations', ['code'], unique=True)

    # 2. Admission cohorts table
    op.create_table(
        'admission_cohorts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('cohort_name', sa.String(length=50), nullable=False),
        sa.Column('start_year', sa.Integer(), nullable=False),
        sa.Column('end_year', sa.Integer(), nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('regulation_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='TRUE', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], name='fk_cohorts_program_id'),
        sa.ForeignKeyConstraint(['regulation_id'], ['regulations.id'], name='fk_cohorts_regulation_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('program_id', 'cohort_name', name='uq_program_cohort_name')
    )
    op.create_index(op.f('ix_admission_cohorts_program_id'), 'admission_cohorts', ['program_id'], unique=False)
    op.create_index(op.f('ix_admission_cohorts_regulation_id'), 'admission_cohorts', ['regulation_id'], unique=False)

    # 3. Curriculum versions table (source_document_id FK added after curriculum_documents)
    op.create_table(
        'curriculum_versions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('version_code', sa.String(length=50), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('regulation_id', sa.Integer(), nullable=False),
        sa.Column('cohort_id', sa.Integer(), nullable=True),
        sa.Column('version_number', sa.Integer(), server_default='1', nullable=False),
        sa.Column('status', sa.String(length=30), server_default='DRAFT', nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('total_credits', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('total_semesters', sa.Integer(), server_default='8', nullable=False),
        sa.Column('source_document_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('reviewed_by_id', sa.Integer(), nullable=True),
        sa.Column('approved_by_id', sa.Integer(), nullable=True),
        sa.Column('published_by_id', sa.Integer(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('superseded_by_id', sa.Integer(), nullable=True),
        sa.Column('previous_version_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT','NEEDS_REVIEW','VALIDATED','APPROVED','PUBLISHED','SUPERSEDED','ARCHIVED')",
            name='ck_curriculum_version_status'
        ),
        sa.ForeignKeyConstraint(['approved_by_id'], ['users.id'], name='fk_cv_approved_by'),
        sa.ForeignKeyConstraint(['cohort_id'], ['admission_cohorts.id'], name='fk_cv_cohort_id'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name='fk_cv_created_by'),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name='fk_cv_department_id'),
        sa.ForeignKeyConstraint(['previous_version_id'], ['curriculum_versions.id'], name='fk_cv_prev_version'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], name='fk_cv_program_id'),
        sa.ForeignKeyConstraint(['published_by_id'], ['users.id'], name='fk_cv_published_by'),
        sa.ForeignKeyConstraint(['regulation_id'], ['regulations.id'], name='fk_cv_regulation_id'),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], name='fk_cv_reviewed_by'),
        sa.ForeignKeyConstraint(['superseded_by_id'], ['curriculum_versions.id'], name='fk_cv_superseded_by'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_curriculum_versions_cohort_id'), 'curriculum_versions', ['cohort_id'], unique=False)
    op.create_index(op.f('ix_curriculum_versions_department_id'), 'curriculum_versions', ['department_id'], unique=False)
    op.create_index(op.f('ix_curriculum_versions_program_id'), 'curriculum_versions', ['program_id'], unique=False)
    op.create_index(op.f('ix_curriculum_versions_regulation_id'), 'curriculum_versions', ['regulation_id'], unique=False)
    op.create_index(op.f('ix_curriculum_versions_status'), 'curriculum_versions', ['status'], unique=False)
    op.create_index(op.f('ix_curriculum_versions_version_code'), 'curriculum_versions', ['version_code'], unique=True)

    # 4. Curriculum documents table
    op.create_table(
        'curriculum_documents',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('program_id', sa.Integer(), nullable=True),
        sa.Column('regulation_id', sa.Integer(), nullable=True),
        sa.Column('cohort_id', sa.Integer(), nullable=True),
        sa.Column('curriculum_version_id', sa.Integer(), nullable=True),
        sa.Column('uploaded_by_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='UPLOADED', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['cohort_id'], ['admission_cohorts.id'], name='fk_cd_cohort_id'),
        sa.ForeignKeyConstraint(['curriculum_version_id'], ['curriculum_versions.id'], name='fk_cd_curriculum_version_id'),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name='fk_cd_department_id'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], name='fk_cd_program_id'),
        sa.ForeignKeyConstraint(['regulation_id'], ['regulations.id'], name='fk_cd_regulation_id'),
        sa.ForeignKeyConstraint(['uploaded_by_id'], ['users.id'], name='fk_cd_uploaded_by'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_curriculum_documents_file_hash'), 'curriculum_documents', ['file_hash'], unique=False)

    # Link source_document_id on curriculum_versions
    op.create_foreign_key('fk_cv_document_id', 'curriculum_versions', 'curriculum_documents', ['source_document_id'], ['id'])

    # 5. Curriculum semesters table
    op.create_table(
        'curriculum_semesters',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('curriculum_version_id', sa.Integer(), nullable=False),
        sa.Column('semester_number', sa.Integer(), nullable=False),
        sa.Column('total_credits', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('total_contact_hours', sa.Integer(), server_default='0', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['curriculum_version_id'], ['curriculum_versions.id'], name='fk_cs_version_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('curriculum_version_id', 'semester_number', name='uq_curriculum_version_semester')
    )
    op.create_index(op.f('ix_curriculum_semesters_curriculum_version_id'), 'curriculum_semesters', ['curriculum_version_id'], unique=False)

    # 6. Curriculum subject mappings table
    op.create_table(
        'curriculum_subject_mappings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('curriculum_version_id', sa.Integer(), nullable=False),
        sa.Column('curriculum_semester_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=True),
        sa.Column('subject_code', sa.String(length=30), nullable=False),
        sa.Column('subject_name', sa.String(length=150), nullable=False),
        sa.Column('subject_type', sa.String(length=30), server_default='THEORY', nullable=False),
        sa.Column('is_mandatory', sa.Boolean(), server_default='TRUE', nullable=False),
        sa.Column('elective_group_name', sa.String(length=100), nullable=True),
        sa.Column('credits', sa.Float(), server_default='3.0', nullable=False),
        sa.Column('lecture_hours', sa.Integer(), server_default='3', nullable=False),
        sa.Column('tutorial_hours', sa.Integer(), server_default='0', nullable=False),
        sa.Column('practical_hours', sa.Integer(), server_default='0', nullable=False),
        sa.Column('contact_hours', sa.Integer(), server_default='3', nullable=False),
        sa.Column('practical_consecutive_periods', sa.Integer(), server_default='2', nullable=False),
        sa.Column('requires_lab', sa.Boolean(), server_default='FALSE', nullable=False),
        sa.Column('course_description', sa.Text(), nullable=True),
        sa.Column('prerequisites', sa.Text(), nullable=True),
        sa.Column('co_requisites', sa.Text(), nullable=True),
        sa.Column('source_pdf_id', sa.Integer(), nullable=True),
        sa.Column('source_page', sa.Integer(), nullable=True),
        sa.Column('source_text', sa.Text(), nullable=True),
        sa.Column('verification_status', sa.String(length=20), server_default='VERIFIED', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "subject_type IN ('THEORY','PRACTICAL','INTEGRATED','TUTORIAL','PROJECT','INTERNSHIP','SEMINAR','MANDATORY_NON_CREDIT','PROFESSIONAL_ELECTIVE','OPEN_ELECTIVE')",
            name='ck_csm_subject_type'
        ),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], name='fk_csm_course_id'),
        sa.ForeignKeyConstraint(['curriculum_semester_id'], ['curriculum_semesters.id'], name='fk_csm_semester_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['curriculum_version_id'], ['curriculum_versions.id'], name='fk_csm_version_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_pdf_id'], ['curriculum_documents.id'], name='fk_csm_source_pdf'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('curriculum_version_id', 'subject_code', name='uq_csm_version_subject_code')
    )
    op.create_index(op.f('ix_curriculum_subject_mappings_curriculum_semester_id'), 'curriculum_subject_mappings', ['curriculum_semester_id'], unique=False)
    op.create_index(op.f('ix_curriculum_subject_mappings_curriculum_version_id'), 'curriculum_subject_mappings', ['curriculum_version_id'], unique=False)
    op.create_index(op.f('ix_curriculum_subject_mappings_subject_code'), 'curriculum_subject_mappings', ['subject_code'], unique=False)

    # 7. Curriculum extraction jobs table
    op.create_table(
        'curriculum_extraction_jobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('document_id', sa.Integer(), nullable=False),
        sa.Column('target_curriculum_version_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=30), server_default='QUEUED', nullable=False),
        sa.Column('total_pages', sa.Integer(), server_default='0', nullable=False),
        sa.Column('extracted_semesters_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('extracted_subjects_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('extracted_data_json', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('reviewed_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "status IN ('QUEUED','PROCESSING','AWAITING_REVIEW','APPROVED','REJECTED','FAILED')",
            name='ck_cej_status'
        ),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name='fk_cej_created_by'),
        sa.ForeignKeyConstraint(['document_id'], ['curriculum_documents.id'], name='fk_cej_document_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], name='fk_cej_reviewed_by'),
        sa.ForeignKeyConstraint(['target_curriculum_version_id'], ['curriculum_versions.id'], name='fk_cej_version_id'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_curriculum_extraction_jobs_document_id'), 'curriculum_extraction_jobs', ['document_id'], unique=False)

    # 8. Curriculum releases table
    op.create_table(
        'curriculum_releases',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('curriculum_version_id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('released_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('released_by_id', sa.Integer(), nullable=False),
        sa.Column('is_acknowledged', sa.Boolean(), server_default='FALSE', nullable=False),
        sa.Column('acknowledged_by_id', sa.Integer(), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledgement_notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['acknowledged_by_id'], ['users.id'], name='fk_cr_acknowledged_by'),
        sa.ForeignKeyConstraint(['curriculum_version_id'], ['curriculum_versions.id'], name='fk_cr_version_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name='fk_cr_department_id'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], name='fk_cr_program_id'),
        sa.ForeignKeyConstraint(['released_by_id'], ['users.id'], name='fk_cr_released_by'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_curriculum_releases_curriculum_version_id'), 'curriculum_releases', ['curriculum_version_id'], unique=False)
    op.create_index(op.f('ix_curriculum_releases_department_id'), 'curriculum_releases', ['department_id'], unique=False)

    # 9. Curriculum requests table
    op.create_table(
        'curriculum_requests',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('request_number', sa.String(length=30), nullable=False),
        sa.Column('requesting_admin_id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=True),
        sa.Column('curriculum_version_id', sa.Integer(), nullable=True),
        sa.Column('curriculum_semester_id', sa.Integer(), nullable=True),
        sa.Column('subject_mapping_id', sa.Integer(), nullable=True),
        sa.Column('request_type', sa.String(length=40), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('proposed_change_json', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=30), server_default='OPEN', nullable=False),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('resolved_by_id', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resulting_curriculum_version_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "request_type IN ('MISSING_SUBJECT','INCORRECT_CODE','INCORRECT_NAME','WRONG_SEMESTER','INCORRECT_CREDITS','INCORRECT_HOURS','MISSING_LAB','MISSING_ELECTIVE','REVISED_SYLLABUS','OTHER')",
            name='ck_req_type'
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','UNDER_REVIEW','NEEDS_INFORMATION','RESOLVED','REJECTED','WITHDRAWN')",
            name='ck_curriculum_req_status'
        ),
        sa.ForeignKeyConstraint(['curriculum_semester_id'], ['curriculum_semesters.id'], name='fk_req_semester_id'),
        sa.ForeignKeyConstraint(['curriculum_version_id'], ['curriculum_versions.id'], name='fk_req_version_id'),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], name='fk_req_department_id'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], name='fk_req_program_id'),
        sa.ForeignKeyConstraint(['requesting_admin_id'], ['users.id'], name='fk_req_admin_id'),
        sa.ForeignKeyConstraint(['resolved_by_id'], ['users.id'], name='fk_req_resolved_by'),
        sa.ForeignKeyConstraint(['resulting_curriculum_version_id'], ['curriculum_versions.id'], name='fk_req_resulting_version_id'),
        sa.ForeignKeyConstraint(['subject_mapping_id'], ['curriculum_subject_mappings.id'], name='fk_req_subject_mapping_id'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_curriculum_requests_department_id'), 'curriculum_requests', ['department_id'], unique=False)
    op.create_index(op.f('ix_curriculum_requests_request_number'), 'curriculum_requests', ['request_number'], unique=True)

    # 10. Curriculum request messages table
    op.create_table(
        'curriculum_request_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('request_id', sa.Integer(), nullable=False),
        sa.Column('sender_id', sa.Integer(), nullable=False),
        sa.Column('sender_role', sa.String(length=30), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('attachments_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['request_id'], ['curriculum_requests.id'], name='fk_crm_request_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], name='fk_crm_sender_id'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_curriculum_request_messages_request_id'), 'curriculum_request_messages', ['request_id'], unique=False)

    # 11. Section course offerings table
    op.create_table(
        'section_course_offerings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('curriculum_version_id', sa.Integer(), nullable=False),
        sa.Column('curriculum_subject_mapping_id', sa.Integer(), nullable=False),
        sa.Column('academic_year_id', sa.Integer(), nullable=False),
        sa.Column('semester_id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('batch_id', sa.Integer(), nullable=True),
        sa.Column('enrolled_student_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='TRUE', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['academic_year_id'], ['academic_years.id'], name='fk_sco_academic_year_id'),
        sa.ForeignKeyConstraint(['batch_id'], ['batches.id'], name='fk_sco_batch_id'),
        sa.ForeignKeyConstraint(['curriculum_subject_mapping_id'], ['curriculum_subject_mappings.id'], name='fk_sco_csm_id'),
        sa.ForeignKeyConstraint(['curriculum_version_id'], ['curriculum_versions.id'], name='fk_sco_version_id'),
        sa.ForeignKeyConstraint(['section_id'], ['sections.id'], name='fk_sco_section_id'),
        sa.ForeignKeyConstraint(['semester_id'], ['semesters.id'], name='fk_sco_semester_id'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_section_course_offerings_curriculum_subject_mapping_id'), 'section_course_offerings', ['curriculum_subject_mapping_id'], unique=False)
    op.create_index(op.f('ix_section_course_offerings_curriculum_version_id'), 'section_course_offerings', ['curriculum_version_id'], unique=False)
    op.create_index(op.f('ix_section_course_offerings_section_id'), 'section_course_offerings', ['section_id'], unique=False)

    # 12. Faculty course offerings table
    op.create_table(
        'faculty_course_offerings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('section_course_offering_id', sa.Integer(), nullable=False),
        sa.Column('faculty_id', sa.Integer(), nullable=False),
        sa.Column('assigned_role', sa.String(length=30), server_default='PRIMARY_LECTURER', nullable=False),
        sa.Column('assigned_hours', sa.Integer(), server_default='3', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='TRUE', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['faculty_id'], ['faculty.id'], name='fk_fco_faculty_id'),
        sa.ForeignKeyConstraint(['section_course_offering_id'], ['section_course_offerings.id'], name='fk_fco_sco_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_faculty_course_offerings_faculty_id'), 'faculty_course_offerings', ['faculty_id'], unique=False)
    op.create_index(op.f('ix_faculty_course_offerings_section_course_offering_id'), 'faculty_course_offerings', ['section_course_offering_id'], unique=False)

    # 13. Extend students table
    op.add_column('students', sa.Column('admission_cohort_id', sa.Integer(), nullable=True))
    op.add_column('students', sa.Column('regulation_id', sa.Integer(), nullable=True))
    op.add_column('students', sa.Column('curriculum_version_id', sa.Integer(), nullable=True))
    op.add_column('students', sa.Column('current_curriculum_semester', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_students_cohort_id', 'students', 'admission_cohorts', ['admission_cohort_id'], ['id'])
    op.create_foreign_key('fk_students_regulation_id', 'students', 'regulations', ['regulation_id'], ['id'])
    op.create_foreign_key('fk_students_curriculum_version_id', 'students', 'curriculum_versions', ['curriculum_version_id'], ['id'])

    # 14. Extend timetable_versions table
    op.add_column('timetable_versions', sa.Column('curriculum_version_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_tv_curriculum_version_id', 'timetable_versions', 'curriculum_versions', ['curriculum_version_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema in reverse order."""
    op.drop_constraint('fk_tv_curriculum_version_id', 'timetable_versions', type_='foreignkey')
    op.drop_column('timetable_versions', 'curriculum_version_id')

    op.drop_constraint('fk_students_curriculum_version_id', 'students', type_='foreignkey')
    op.drop_constraint('fk_students_regulation_id', 'students', type_='foreignkey')
    op.drop_constraint('fk_students_cohort_id', 'students', type_='foreignkey')
    op.drop_column('students', 'current_curriculum_semester')
    op.drop_column('students', 'curriculum_version_id')
    op.drop_column('students', 'regulation_id')
    op.drop_column('students', 'admission_cohort_id')

    op.drop_index(op.f('ix_faculty_course_offerings_section_course_offering_id'), table_name='faculty_course_offerings')
    op.drop_index(op.f('ix_faculty_course_offerings_faculty_id'), table_name='faculty_course_offerings')
    op.drop_table('faculty_course_offerings')

    op.drop_index(op.f('ix_section_course_offerings_section_id'), table_name='section_course_offerings')
    op.drop_index(op.f('ix_section_course_offerings_curriculum_version_id'), table_name='section_course_offerings')
    op.drop_index(op.f('ix_section_course_offerings_curriculum_subject_mapping_id'), table_name='section_course_offerings')
    op.drop_table('section_course_offerings')

    op.drop_index(op.f('ix_curriculum_request_messages_request_id'), table_name='curriculum_request_messages')
    op.drop_table('curriculum_request_messages')

    op.drop_index(op.f('ix_curriculum_requests_request_number'), table_name='curriculum_requests')
    op.drop_index(op.f('ix_curriculum_requests_department_id'), table_name='curriculum_requests')
    op.drop_table('curriculum_requests')

    op.drop_index(op.f('ix_curriculum_releases_department_id'), table_name='curriculum_releases')
    op.drop_index(op.f('ix_curriculum_releases_curriculum_version_id'), table_name='curriculum_releases')
    op.drop_table('curriculum_releases')

    op.drop_index(op.f('ix_curriculum_extraction_jobs_document_id'), table_name='curriculum_extraction_jobs')
    op.drop_table('curriculum_extraction_jobs')

    op.drop_index(op.f('ix_curriculum_subject_mappings_subject_code'), table_name='curriculum_subject_mappings')
    op.drop_index(op.f('ix_curriculum_subject_mappings_curriculum_version_id'), table_name='curriculum_subject_mappings')
    op.drop_index(op.f('ix_curriculum_subject_mappings_curriculum_semester_id'), table_name='curriculum_subject_mappings')
    op.drop_table('curriculum_subject_mappings')

    op.drop_index(op.f('ix_curriculum_semesters_curriculum_version_id'), table_name='curriculum_semesters')
    op.drop_table('curriculum_semesters')

    op.drop_constraint('fk_cv_document_id', 'curriculum_versions', type_='foreignkey')

    op.drop_index(op.f('ix_curriculum_documents_file_hash'), table_name='curriculum_documents')
    op.drop_table('curriculum_documents')

    op.drop_index(op.f('ix_curriculum_versions_version_code'), table_name='curriculum_versions')
    op.drop_index(op.f('ix_curriculum_versions_status'), table_name='curriculum_versions')
    op.drop_index(op.f('ix_curriculum_versions_regulation_id'), table_name='curriculum_versions')
    op.drop_index(op.f('ix_curriculum_versions_program_id'), table_name='curriculum_versions')
    op.drop_index(op.f('ix_curriculum_versions_department_id'), table_name='curriculum_versions')
    op.drop_index(op.f('ix_curriculum_versions_cohort_id'), table_name='curriculum_versions')
    op.drop_table('curriculum_versions')

    op.drop_index(op.f('ix_admission_cohorts_regulation_id'), table_name='admission_cohorts')
    op.drop_index(op.f('ix_admission_cohorts_program_id'), table_name='admission_cohorts')
    op.drop_table('admission_cohorts')

    op.drop_index(op.f('ix_regulations_code'), table_name='regulations')
    op.drop_table('regulations')

    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.create_check_constraint(
        'ck_users_role',
        'users',
        "role IN ('STUDENT','FACULTY','ADMIN')"
    )
