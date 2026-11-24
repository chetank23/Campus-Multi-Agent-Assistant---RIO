"""add_placement_applications_club_memberships_event_registrations

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-11-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Placement Applications
    op.create_table(
        'placement_applications',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('drive_id', sa.Integer(), nullable=False),
        sa.Column('student_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='APPLIED', nullable=False),
        sa.Column('resume_url', sa.String(length=500), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('applied_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['drive_id'], ['placement_drives.id'], name='fk_placement_applications_drive_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], name='fk_placement_applications_student_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_placement_applications'),
        sa.UniqueConstraint('drive_id', 'student_id', name='uq_placement_application_drive_student'),
    )
    op.create_index('ix_placement_applications_drive_status', 'placement_applications', ['drive_id', 'status'], unique=False)
    op.create_index('ix_placement_applications_student', 'placement_applications', ['student_id'], unique=False)

    # 2. Club Memberships
    op.create_table(
        'club_memberships',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('club_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=30), server_default='MEMBER', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='ACTIVE', nullable=False),
        sa.Column('joined_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name='fk_club_memberships_club_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_club_memberships_user_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_club_memberships'),
        sa.UniqueConstraint('club_id', 'user_id', name='uq_club_membership_club_user'),
    )
    op.create_index('ix_club_memberships_club', 'club_memberships', ['club_id'], unique=False)
    op.create_index('ix_club_memberships_user', 'club_memberships', ['user_id'], unique=False)

    # 3. Event Registrations
    op.create_table(
        'event_registrations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='REGISTERED', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('registered_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['campus_events.id'], name='fk_event_registrations_event_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_event_registrations_user_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name='pk_event_registrations'),
        sa.UniqueConstraint('event_id', 'user_id', name='uq_event_registration_event_user'),
    )
    op.create_index('ix_event_registrations_event', 'event_registrations', ['event_id'], unique=False)
    op.create_index('ix_event_registrations_user', 'event_registrations', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_event_registrations_user', table_name='event_registrations')
    op.drop_index('ix_event_registrations_event', table_name='event_registrations')
    op.drop_table('event_registrations')

    op.drop_index('ix_club_memberships_user', table_name='club_memberships')
    op.drop_index('ix_club_memberships_club', table_name='club_memberships')
    op.drop_table('club_memberships')

    op.drop_index('ix_placement_applications_student', table_name='placement_applications')
    op.drop_index('ix_placement_applications_drive_status', table_name='placement_applications')
    op.drop_table('placement_applications')
