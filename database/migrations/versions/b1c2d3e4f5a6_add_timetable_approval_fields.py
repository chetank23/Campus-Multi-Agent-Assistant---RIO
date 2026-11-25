"""add_timetable_approval_fields

Revision ID: b1c2d3e4f5a6
Revises: a9b8c7d6e5f4
Create Date: 2026-11-25 21:12:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("timetable_versions", sa.Column("approved_at", sa.DateTime(), nullable=True))
    op.add_column("timetable_versions", sa.Column("approved_revision", sa.Integer(), nullable=True))

    op.drop_constraint("ck_tv_status", "timetable_versions", type_="check")
    op.create_check_constraint(
        "ck_tv_status",
        "timetable_versions",
        "status IN ('DRAFT','GENERATED','REVIEWED','VALIDATED','FINALIZED','APPROVED','PUBLISHED','REJECTED','ARCHIVED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tv_status", "timetable_versions", type_="check")
    op.create_check_constraint(
        "ck_tv_status",
        "timetable_versions",
        "status IN ('DRAFT','GENERATED','REVIEWED','VALIDATED','FINALIZED','PUBLISHED','REJECTED','ARCHIVED')",
    )
    op.drop_column("timetable_versions", "approved_revision")
    op.drop_column("timetable_versions", "approved_at")
