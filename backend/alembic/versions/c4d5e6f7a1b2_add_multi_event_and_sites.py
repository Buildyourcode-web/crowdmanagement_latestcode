"""add_multi_event_and_sites

Revision ID: c4d5e6f7a1b2
Revises: a1b2c3d4e5f7
Create Date: 2026-09-09 14:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a1b2'
down_revision: Union[str, None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend events table
    op.add_column('events', sa.Column('location', sa.String(length=300), nullable=True))
    op.add_column('events', sa.Column('city', sa.String(length=100), nullable=True))
    op.add_column('events', sa.Column('state', sa.String(length=100), nullable=True))
    op.add_column('events', sa.Column('country', sa.String(length=100), server_default='India', nullable=True))
    op.add_column('events', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('events', sa.Column('longitude', sa.Float(), nullable=True))
    op.add_column('events', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('events', sa.Column('created_by', sa.String(length=100), nullable=True))
    op.add_column('events', sa.Column('updated_by', sa.String(length=100), nullable=True))

    # 2. Create sites table
    op.create_table(
        'sites',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('event_id', UUID(as_uuid=True), sa.ForeignKey('events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_code', sa.String(length=50), nullable=False),
        sa.Column('site_name', sa.String(length=150), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('location', sa.String(length=300), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('status', sa.String(length=50), server_default='ACTIVE', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.Column('updated_by', sa.String(length=100), nullable=True),
        sa.UniqueConstraint('event_id', 'site_code', name='uq_site_event_code'),
    )
    op.create_index('ix_sites_event_id', 'sites', ['event_id'])
    op.create_index('ix_sites_site_code', 'sites', ['site_code'])
    op.create_index('ix_sites_status', 'sites', ['status'])

    # 3. Create user_event_access table
    op.create_table(
        'user_event_access',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_id', UUID(as_uuid=True), sa.ForeignKey('events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('access_role', sa.String(length=50), server_default='VIEWER', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('granted_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'event_id', name='uq_user_event_access'),
    )
    op.create_index('ix_user_event_access_user_id', 'user_event_access', ['user_id'])
    op.create_index('ix_user_event_access_event_id', 'user_event_access', ['event_id'])

    # 4. Create user_site_access table
    op.create_table(
        'user_site_access',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_id', UUID(as_uuid=True), sa.ForeignKey('events.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', UUID(as_uuid=True), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('granted_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('user_id', 'site_id', name='uq_user_site_access'),
    )
    op.create_index('ix_user_site_access_user_id', 'user_site_access', ['user_id'])
    op.create_index('ix_user_site_access_event_id', 'user_site_access', ['event_id'])
    op.create_index('ix_user_site_access_site_id', 'user_site_access', ['site_id'])

    # 5. Extend cameras table
    op.add_column('cameras', sa.Column('event_id', UUID(as_uuid=True), sa.ForeignKey('events.id'), nullable=True))
    op.add_column('cameras', sa.Column('site_id', UUID(as_uuid=True), sa.ForeignKey('sites.id'), nullable=True))
    op.create_index('ix_cameras_event_id', 'cameras', ['event_id'])
    op.create_index('ix_cameras_site_id', 'cameras', ['site_id'])

    # 6. Extend queue_snapshots table
    op.add_column('queue_snapshots', sa.Column('event_id', UUID(as_uuid=True), sa.ForeignKey('events.id'), nullable=True))
    op.create_index('ix_queue_snapshots_event_id', 'queue_snapshots', ['event_id'])

    # 7. Extend ai_pipeline_deployments table
    op.add_column('ai_pipeline_deployments', sa.Column('event_id', UUID(as_uuid=True), sa.ForeignKey('events.id'), nullable=True))
    op.create_index('ix_ai_pipeline_deployments_event_id', 'ai_pipeline_deployments', ['event_id'])


def downgrade() -> None:
    # Drop ai_pipeline_deployments event_id
    op.drop_index('ix_ai_pipeline_deployments_event_id', table_name='ai_pipeline_deployments')
    op.drop_column('ai_pipeline_deployments', 'event_id')

    # Drop queue_snapshots event_id
    op.drop_index('ix_queue_snapshots_event_id', table_name='queue_snapshots')
    op.drop_column('queue_snapshots', 'event_id')

    # Drop cameras site_id, event_id
    op.drop_index('ix_cameras_site_id', table_name='cameras')
    op.drop_index('ix_cameras_event_id', table_name='cameras')
    op.drop_column('cameras', 'site_id')
    op.drop_column('cameras', 'event_id')

    # Drop user_site_access
    op.drop_index('ix_user_site_access_site_id', table_name='user_site_access')
    op.drop_index('ix_user_site_access_event_id', table_name='user_site_access')
    op.drop_index('ix_user_site_access_user_id', table_name='user_site_access')
    op.drop_table('user_site_access')

    # Drop user_event_access
    op.drop_index('ix_user_event_access_event_id', table_name='user_event_access')
    op.drop_index('ix_user_event_access_user_id', table_name='user_event_access')
    op.drop_table('user_event_access')

    # Drop sites
    op.drop_index('ix_sites_status', table_name='sites')
    op.drop_index('ix_sites_site_code', table_name='sites')
    op.drop_index('ix_sites_event_id', table_name='sites')
    op.drop_table('sites')

    # Drop events columns
    op.drop_column('events', 'updated_by')
    op.drop_column('events', 'created_by')
    op.drop_column('events', 'is_active')
    op.drop_column('events', 'longitude')
    op.drop_column('events', 'latitude')
    op.drop_column('events', 'country')
    op.drop_column('events', 'state')
    op.drop_column('events', 'city')
    op.drop_column('events', 'location')

