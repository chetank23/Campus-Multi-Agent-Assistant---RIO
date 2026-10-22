"""add_notification_metadata

Revision ID: d4e82f1b90ac
Revises: c935fa023e45
Create Date: 2026-10-22 20:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e82f1b90ac'
down_revision: Union[str, Sequence[str], None] = 'c935fa023e45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('notifications', sa.Column('link', sa.String(length=255), nullable=True))
    op.add_column('notifications', sa.Column('entity_type', sa.String(length=50), nullable=True))
    op.add_column('notifications', sa.Column('entity_id', sa.Integer(), nullable=True))
    op.create_index('ix_notifications_user_id_is_read', 'notifications', ['user_id', 'is_read'])
    op.drop_constraint('fk_notif_user_id', 'notifications', type_='foreignkey')
    op.create_foreign_key('fk_notif_user_id', 'notifications', 'users', ['user_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    op.drop_constraint('fk_notif_user_id', 'notifications', type_='foreignkey')
    op.create_foreign_key('fk_notif_user_id', 'notifications', 'users', ['user_id'], ['id'])
    op.drop_index('ix_notifications_user_id_is_read', table_name='notifications')
    op.drop_column('notifications', 'entity_id')
    op.drop_column('notifications', 'entity_type')
    op.drop_column('notifications', 'link')
