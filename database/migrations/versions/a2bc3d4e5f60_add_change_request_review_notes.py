"""add change request review notes

Revision ID: a2bc3d4e5f60
Revises: 91ab2c3d4e5f
Create Date: 2026-11-02
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a2bc3d4e5f60"
down_revision: Union[str, Sequence[str], None] = "91ab2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("change_requests", sa.Column("review_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("change_requests", "review_note")
