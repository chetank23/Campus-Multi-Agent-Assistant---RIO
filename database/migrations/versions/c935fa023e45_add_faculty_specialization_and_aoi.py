"""add_faculty_specialization_and_aoi

Revision ID: c935fa023e45
Revises: b824ef912d34
Create Date: 2026-10-03 15:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c935fa023e45'
down_revision: Union[str, Sequence[str], None] = 'b824ef912d34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('faculty', 'designation', existing_type=sa.String(length=50), type_=sa.String(length=100), existing_nullable=True)
    op.add_column('faculty', sa.Column('specialization', sa.Text(), nullable=True))
    op.add_column('faculty', sa.Column('areas_of_interest', sa.Text(), nullable=True))
    op.add_column('faculty', sa.Column('source_url', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('faculty', 'source_url')
    op.drop_column('faculty', 'areas_of_interest')
    op.drop_column('faculty', 'specialization')
    op.alter_column('faculty', 'designation', existing_type=sa.String(length=100), type_=sa.String(length=50), existing_nullable=True)
