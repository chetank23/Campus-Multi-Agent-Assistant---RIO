"""add_canonical_timetables

Revision ID: e4f5a6b7c8d9
Revises: cdd3afe221f2
Create Date: 2026-11-07 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: Union[str, Sequence[str], None] = 'cdd3afe221f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create canonical timetables table
    op.create_table(
        'timetables',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('academic_year_id', sa.Integer(), nullable=False),
        sa.Column('semester_id', sa.Integer(), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='PUBLISHED', nullable=False),
        sa.Column('working_days', sa.String(length=10), server_default='MON_SAT', nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('published_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','ARCHIVED')",
            name='ck_timetable_status'
        ),
        sa.CheckConstraint(
            "working_days IN ('MON_FRI','MON_SAT')",
            name='ck_timetable_working_days'
        ),
        sa.ForeignKeyConstraint(
            ['academic_year_id'],
            ['academic_years.id'],
            name='fk_tt_academic_year_id',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['created_by'],
            ['users.id'],
            name='fk_tt_created_by'
        ),
        sa.ForeignKeyConstraint(
            ['section_id'],
            ['sections.id'],
            name='fk_tt_section_id',
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['semester_id'],
            ['semesters.id'],
            name='fk_tt_semester_id',
            ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'academic_year_id',
            'semester_id',
            'section_id',
            name='uq_timetables_ay_sem_sec'
        )
    )

    # 2. Add timetable_id to timetable_entries
    op.add_column(
        'timetable_entries',
        sa.Column('timetable_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_tte_timetable_id',
        'timetable_entries',
        'timetables',
        ['timetable_id'],
        ['id'],
        ondelete='CASCADE'
    )
    op.create_index(
        'ix_timetable_entries_timetable_id',
        'timetable_entries',
        ['timetable_id']
    )

    # 3. Backfill existing published timetable entries into canonical timetables
    conn = op.get_bind()
    # Find distinct (academic_year_id, semester_id, section_id) from timetable_entries joined with timetable_versions
    conn.execute(sa.text("""
        INSERT INTO timetables (academic_year_id, semester_id, section_id, status, created_at, published_at)
        SELECT DISTINCT
            COALESCE(tv.academic_year_id, s.academic_year_id) as academic_year_id,
            te.semester_id,
            te.section_id,
            'PUBLISHED',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM timetable_entries te
        JOIN timetable_versions tv ON te.version_id = tv.id
        LEFT JOIN semesters s ON te.semester_id = s.id
        WHERE tv.status = 'PUBLISHED'
          AND te.section_id IS NOT NULL
          AND te.semester_id IS NOT NULL
          AND COALESCE(tv.academic_year_id, s.academic_year_id) IS NOT NULL
        ON CONFLICT (academic_year_id, semester_id, section_id) DO NOTHING;
    """))

    # Link timetable_entries to timetables
    conn.execute(sa.text("""
        UPDATE timetable_entries te
        SET timetable_id = t.id
        FROM timetables t, timetable_versions tv, semesters s
        WHERE te.version_id = tv.id
          AND te.semester_id = s.id
          AND t.academic_year_id = COALESCE(tv.academic_year_id, s.academic_year_id)
          AND t.semester_id = te.semester_id
          AND t.section_id = te.section_id
          AND tv.status = 'PUBLISHED';
    """))


def downgrade() -> None:
    op.drop_index('ix_timetable_entries_timetable_id', table_name='timetable_entries')
    op.drop_constraint('fk_tte_timetable_id', 'timetable_entries', type_='foreignkey')
    op.drop_column('timetable_entries', 'timetable_id')
    op.drop_table('timetables')
