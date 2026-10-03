"""add_contact_number_and_class_teacher

Revision ID: b824ef912d34
Revises: a7156e0cf272
Create Date: 2026-10-03 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b824ef912d34'
down_revision: Union[str, Sequence[str], None] = 'a7156e0cf272'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('faculty', sa.Column('contact_number', sa.String(length=20), nullable=True))
    op.add_column('sections', sa.Column('class_teacher_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_sections_class_teacher_id', 'sections', 'faculty', ['class_teacher_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_sections_class_teacher_id', 'sections', type_='foreignkey')
    op.drop_column('sections', 'class_teacher_id')
    op.drop_column('faculty', 'contact_number')
