"""add_timetable_recall_and_validation_fields

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-11-25 22:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("timetable_versions", sa.Column("recalled_at", sa.DateTime(), nullable=True))
    op.add_column("timetable_versions", sa.Column("recalled_by", sa.Integer(), sa.ForeignKey("users.id", name="fk_tv_recalled_by"), nullable=True))
    op.add_column("timetable_versions", sa.Column("recall_reason", sa.Text(), nullable=True))
    op.add_column("timetable_versions", sa.Column("validation_status", sa.String(30), server_default="NOT_VALIDATED", nullable=True))
    op.add_column("timetable_versions", sa.Column("validation_errors_count", sa.Integer(), server_default="0", nullable=True))
    op.add_column("timetable_versions", sa.Column("validation_warnings_count", sa.Integer(), server_default="0", nullable=True))
    op.add_column("timetable_versions", sa.Column("validated_at", sa.DateTime(), nullable=True))

    op.drop_constraint("ck_tv_status", "timetable_versions", type_="check")
    op.create_check_constraint(
        "ck_tv_status",
        "timetable_versions",
        "status IN ('DRAFT','GENERATED','REVIEWED','VALIDATED','FINALIZED','APPROVED','PUBLISHED','RECALLED','REJECTED','ARCHIVED')",
    )

    op.drop_constraint("ck_timetable_status", "timetables", type_="check")
    op.create_check_constraint(
        "ck_timetable_status",
        "timetables",
        "status IN ('DRAFT','PUBLISHED','ARCHIVED','RECALLED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_timetable_status", "timetables", type_="check")
    op.create_check_constraint(
        "ck_timetable_status",
        "timetables",
        "status IN ('DRAFT','PUBLISHED','ARCHIVED')",
    )
    op.drop_constraint("ck_tv_status", "timetable_versions", type_="check")
    op.create_check_constraint(
        "ck_tv_status",
        "timetable_versions",
        "status IN ('DRAFT','GENERATED','REVIEWED','VALIDATED','FINALIZED','APPROVED','PUBLISHED','REJECTED','ARCHIVED')",
    )
    op.drop_constraint("fk_tv_recalled_by", "timetable_versions", type_="foreignkey")
    op.drop_column("timetable_versions", "validated_at")
    op.drop_column("timetable_versions", "validation_warnings_count")
    op.drop_column("timetable_versions", "validation_errors_count")
    op.drop_column("timetable_versions", "validation_status")
    op.drop_column("timetable_versions", "recall_reason")
    op.drop_column("timetable_versions", "recalled_by")
    op.drop_column("timetable_versions", "recalled_at")
