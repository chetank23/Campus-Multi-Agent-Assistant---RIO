"""refactor_to_3_role_model

Revision ID: 2d9ab7d55114
Revises: 860895d79b1b
Create Date: 2026-08-23 17:10:07.751640

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2d9ab7d55114'
down_revision: Union[str, Sequence[str], None] = '860895d79b1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Migrate roles
    op.execute("UPDATE users SET role = 'ADMIN' WHERE role IN ('HOD', 'TIMETABLE_COORDINATOR')")
    
    # 2. Recreate user role check constraint
    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.create_check_constraint('ck_users_role', 'users', "role IN ('STUDENT','FACULTY','ADMIN')")
    
    # 3. Drop departments.hod_id
    op.drop_constraint('fk_departments_hod_id', 'departments', type_='foreignkey')
    op.drop_column('departments', 'hod_id')
    
    # 4. Rename timetable_version and update constraint
    op.rename_table('timetable_version', 'timetable_versions')
    op.drop_constraint('ck_tv_status', 'timetable_versions', type_='check')
    op.create_check_constraint(
        'ck_tv_status', 
        'timetable_versions', 
        "status IN ('DRAFT','GENERATED','REVIEWED','VALIDATED','FINALIZED','PUBLISHED','REJECTED','ARCHIVED')"
    )
    
    # 5. Rename timetable and add constraint
    op.rename_table('timetable', 'timetable_entries')
    op.create_check_constraint(
        'ck_te_status', 
        'timetable_entries', 
        "status IN ('DRAFT','ACTIVE','CANCELLED','RESCHEDULED')"
    )
    
    # 6. Rename composite indexes
    op.execute("ALTER INDEX ix_timetable_faculty_slot RENAME TO ix_timetable_entries_faculty_slot")
    op.execute("ALTER INDEX ix_timetable_room_slot RENAME TO ix_timetable_entries_room_slot")
    op.execute("ALTER INDEX ix_timetable_section_slot RENAME TO ix_timetable_entries_section_slot")


def downgrade() -> None:
    # 6. Revert composite indexes
    op.execute("ALTER INDEX ix_timetable_entries_faculty_slot RENAME TO ix_timetable_faculty_slot")
    op.execute("ALTER INDEX ix_timetable_entries_room_slot RENAME TO ix_timetable_room_slot")
    op.execute("ALTER INDEX ix_timetable_entries_section_slot RENAME TO ix_timetable_section_slot")

    # 5. Revert timetable rename
    op.drop_constraint('ck_te_status', 'timetable_entries', type_='check')
    op.rename_table('timetable_entries', 'timetable')

    # 4. Revert timetable_versions rename and constraint
    op.drop_constraint('ck_tv_status', 'timetable_versions', type_='check')
    op.create_check_constraint(
        'ck_tv_status', 
        'timetable_versions', 
        "status IN ('DRAFT','GENERATED','HOD_REVIEW','HOD_APPROVED','COORDINATOR_REVIEW','ADMIN_REVIEW','APPROVED','PUBLISHED','REJECTED','ARCHIVED')"
    )
    op.rename_table('timetable_versions', 'timetable_version')

    # 3. Revert departments.hod_id
    op.add_column('departments', sa.Column('hod_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_departments_hod_id', 'departments', 'users', ['hod_id'], ['id'])

    # 2. Revert users role check constraint
    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.create_check_constraint('ck_users_role', 'users', "role IN ('STUDENT','FACULTY','HOD','TIMETABLE_COORDINATOR','ADMIN')")
