"""add_notification_outbox_table

Revision ID: f01a2b3c4d5e
Revises: e5f6a7b8c9d0
Create Date: 2026-10-28 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f01a2b3c4d5e'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notification_outbox',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('notification_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(length=20), server_default='SSE', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='PENDING', nullable=False),
        sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_retries', sa.Integer(), server_default='3', nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], name='fk_no_notification_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_no_user_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notification_outbox_status', 'notification_outbox', ['status'])
    op.create_index('ix_notification_outbox_user_id', 'notification_outbox', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_notification_outbox_user_id', table_name='notification_outbox')
    op.drop_index('ix_notification_outbox_status', table_name='notification_outbox')
    op.drop_table('notification_outbox')

