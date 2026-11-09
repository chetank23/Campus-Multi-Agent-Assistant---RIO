"""add_system_settings_table

Revision ID: f1a2b3c4d5e6
Revises: e4f5a6b7c8d9
Create Date: 2026-11-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e4f5a6b7c8d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'system_settings',
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ['updated_by_id'],
            ['users.id'],
            name='fk_ss_updated_by_id',
            ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('key', name='pk_system_settings')
    )
    op.create_index(
        'ix_system_settings_category',
        'system_settings',
        ['category'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_system_settings_category', table_name='system_settings')
    op.drop_table('system_settings')

