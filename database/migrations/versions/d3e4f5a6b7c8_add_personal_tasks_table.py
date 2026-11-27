"""add_personal_tasks_table

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-11-28 00:09:30.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "personal_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("priority", sa.String(length=10), server_default="MEDIUM", nullable=False),
        sa.Column("status", sa.String(length=15), server_default="PENDING", nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_personal_tasks_priority"),
        sa.CheckConstraint("status IN ('PENDING', 'COMPLETED')", name="ck_personal_tasks_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_personal_tasks_user_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_personal_tasks_user_status", "personal_tasks", ["user_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_personal_tasks_user_status", table_name="personal_tasks")
    op.drop_table("personal_tasks")
