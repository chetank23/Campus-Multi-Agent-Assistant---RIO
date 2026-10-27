"""add_agent_proposals_table

Revision ID: e5f6a7b8c9d0
Revises: d4e82f1b90ac
Create Date: 2026-10-27 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e82f1b90ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_proposals',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('proposal_id', sa.String(length=100), nullable=False),
        sa.Column('proposal_type', sa.String(length=50), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('revision', sa.Integer(), server_default='1', nullable=False),
        sa.Column('parent_proposal_id', sa.String(length=100), nullable=True),
        sa.Column('superseded', sa.Boolean(), server_default='FALSE', nullable=False),
        sa.Column('superseded_by', sa.String(length=100), nullable=True),
        sa.Column('consumed', sa.Boolean(), server_default='FALSE', nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_ap_user_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_proposals_proposal_id', 'agent_proposals', ['proposal_id'], unique=True)
    op.create_index('ix_agent_proposals_lookup', 'agent_proposals', ['user_id', 'proposal_type', 'consumed', 'superseded'])


def downgrade() -> None:
    op.drop_index('ix_agent_proposals_lookup', table_name='agent_proposals')
    op.drop_index('ix_agent_proposals_proposal_id', table_name='agent_proposals')
    op.drop_table('agent_proposals')
