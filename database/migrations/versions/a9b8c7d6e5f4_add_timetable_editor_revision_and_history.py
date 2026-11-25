"""add_timetable_editor_revision_and_history

Revision ID: a9b8c7d6e5f4
Revises: f2b3c4d5e6f7
Create Date: 2026-11-25 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, Sequence[str], None] = "f2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("timetable_versions", sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
    op.add_column("timetable_versions", sa.Column("validated_revision", sa.Integer(), nullable=True))
    op.add_column("timetable_versions", sa.Column("last_saved_at", sa.DateTime(), nullable=True))
    op.add_column("timetable_versions", sa.Column("last_saved_by", sa.Integer(), nullable=True))
    op.add_column("timetable_versions", sa.Column("finalized_by", sa.Integer(), nullable=True))
    op.add_column("timetable_versions", sa.Column("finalized_at", sa.DateTime(), nullable=True))
    op.add_column("timetable_versions", sa.Column("working_days", sa.String(length=10), server_default="MON_SAT", nullable=True))
    op.add_column("timetable_versions", sa.Column("score_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("timetable_versions", sa.Column("department_id", sa.Integer(), nullable=True))
    op.add_column("timetable_versions", sa.Column("program_id", sa.Integer(), nullable=True))
    op.add_column("timetable_versions", sa.Column("semester_id", sa.Integer(), nullable=True))

    op.create_foreign_key("fk_tv_last_saved_by", "timetable_versions", "users", ["last_saved_by"], ["id"])
    op.create_foreign_key("fk_tv_finalized_by", "timetable_versions", "users", ["finalized_by"], ["id"])
    op.create_foreign_key("fk_tv_department_id", "timetable_versions", "departments", ["department_id"], ["id"])
    op.create_foreign_key("fk_tv_program_id", "timetable_versions", "programs", ["program_id"], ["id"])
    op.create_foreign_key("fk_tv_semester_id", "timetable_versions", "semesters", ["semester_id"], ["id"])

    op.add_column("timetable_entries", sa.Column("course_assignment_id", sa.Integer(), nullable=True))
    op.add_column("timetable_entries", sa.Column("hour_type", sa.String(length=20), nullable=True))
    op.add_column("timetable_entries", sa.Column("block_group_id", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_tte_course_assignment_id",
        "timetable_entries",
        "course_assignments",
        ["course_assignment_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_timetable_entries_block_group_id", "timetable_entries", ["block_group_id"])

    op.create_table(
        "timetable_change_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=True),
        sa.Column("admin_id", sa.Integer(), nullable=False),
        sa.Column("previous_slot_id", sa.Integer(), nullable=True),
        sa.Column("new_slot_id", sa.Integer(), nullable=True),
        sa.Column("previous_room_id", sa.Integer(), nullable=True),
        sa.Column("new_room_id", sa.Integer(), nullable=True),
        sa.Column("previous_faculty_id", sa.Integer(), nullable=True),
        sa.Column("new_faculty_id", sa.Integer(), nullable=True),
        sa.Column("previous_day", sa.String(length=20), nullable=True),
        sa.Column("new_day", sa.String(length=20), nullable=True),
        sa.Column("validation_outcome", sa.String(length=40), server_default="VALID", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["admin_id"], ["users.id"], name="fk_tch_admin_id"),
        sa.ForeignKeyConstraint(["entry_id"], ["timetable_entries.id"], name="fk_tch_entry_id", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["version_id"], ["timetable_versions.id"], name="fk_tch_version_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tch_version_revision", "timetable_change_history", ["version_id", "revision"])
    op.create_index("ix_tch_entry_id", "timetable_change_history", ["entry_id"])


def downgrade() -> None:
    op.drop_index("ix_tch_entry_id", table_name="timetable_change_history")
    op.drop_index("ix_tch_version_revision", table_name="timetable_change_history")
    op.drop_table("timetable_change_history")

    op.drop_index("ix_timetable_entries_block_group_id", table_name="timetable_entries")
    op.drop_constraint("fk_tte_course_assignment_id", "timetable_entries", type_="foreignkey")
    op.drop_column("timetable_entries", "block_group_id")
    op.drop_column("timetable_entries", "hour_type")
    op.drop_column("timetable_entries", "course_assignment_id")

    op.drop_constraint("fk_tv_semester_id", "timetable_versions", type_="foreignkey")
    op.drop_constraint("fk_tv_program_id", "timetable_versions", type_="foreignkey")
    op.drop_constraint("fk_tv_department_id", "timetable_versions", type_="foreignkey")
    op.drop_constraint("fk_tv_finalized_by", "timetable_versions", type_="foreignkey")
    op.drop_constraint("fk_tv_last_saved_by", "timetable_versions", type_="foreignkey")
    op.drop_column("timetable_versions", "semester_id")
    op.drop_column("timetable_versions", "program_id")
    op.drop_column("timetable_versions", "department_id")
    op.drop_column("timetable_versions", "score_summary")
    op.drop_column("timetable_versions", "working_days")
    op.drop_column("timetable_versions", "finalized_at")
    op.drop_column("timetable_versions", "finalized_by")
    op.drop_column("timetable_versions", "last_saved_by")
    op.drop_column("timetable_versions", "last_saved_at")
    op.drop_column("timetable_versions", "validated_revision")
    op.drop_column("timetable_versions", "revision")
