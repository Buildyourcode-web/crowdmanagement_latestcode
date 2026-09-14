"""add_line_crossing_events_and_dynamic_events

Revision ID: f7b8c9d0e1f2
Revises: d5e6f7a1b2c3
Create Date: 2026-09-14 01:10:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'f7b8c9d0e1f2'
down_revision: Union[str, None] = 'd5e6f7a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create line_crossing_events table
    op.create_table(
        'line_crossing_events',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', UUID(as_uuid=True), sa.ForeignKey('events.id', ondelete='SET NULL'), nullable=True),
        sa.Column('site_id', UUID(as_uuid=True), sa.ForeignKey('sites.id', ondelete='SET NULL'), nullable=True),
        sa.Column('camera_id', UUID(as_uuid=True), sa.ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False),
        sa.Column('camera_code', sa.String(length=50), nullable=False),
        sa.Column('line_id', sa.String(length=100), nullable=False),
        sa.Column('line_name', sa.String(length=150), nullable=True),
        sa.Column('track_session_id', sa.String(length=100), nullable=False),
        sa.Column('track_token', sa.String(length=50), nullable=False),
        sa.Column('crossing_sequence', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('direction', sa.String(length=10), nullable=False),
        sa.Column('count_delta', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('detection_confidence', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('frame_id', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('crossing_timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('idempotency_key', sa.String(length=200), nullable=False),
        sa.Column('ground_x', sa.Float(), nullable=True),
        sa.Column('ground_y', sa.Float(), nullable=True),
        sa.Column('signed_distance', sa.Float(), nullable=True),
        sa.Column('meta_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.UniqueConstraint('idempotency_key', name='uq_crossing_idempotency_key'),
        sa.UniqueConstraint('camera_id', 'line_id', 'track_session_id', 'crossing_sequence', name='uq_crossing_event_sequence'),
    )

    # 2. Create indices for line_crossing_events
    op.create_index('ix_crossing_events_event_id', 'line_crossing_events', ['event_id'])
    op.create_index('ix_crossing_events_camera_id', 'line_crossing_events', ['camera_id'])
    op.create_index('ix_crossing_events_camera_code', 'line_crossing_events', ['camera_code'])
    op.create_index('ix_crossing_events_line_id', 'line_crossing_events', ['line_id'])
    op.create_index('ix_crossing_events_track_session', 'line_crossing_events', ['track_session_id'])
    op.create_index('ix_crossing_events_track_token', 'line_crossing_events', ['track_token'])
    op.create_index('ix_crossing_events_direction', 'line_crossing_events', ['direction'])
    op.create_index('ix_crossing_events_timestamp', 'line_crossing_events', ['crossing_timestamp'])
    op.create_index('ix_crossing_events_idempotency', 'line_crossing_events', ['idempotency_key'])
    op.create_index('idx_crossing_event_time', 'line_crossing_events', ['event_id', 'direction', 'crossing_timestamp'])
    op.create_index('idx_crossing_cam_line_time', 'line_crossing_events', ['camera_id', 'line_id', 'crossing_timestamp'])


def downgrade() -> None:
    op.drop_index('idx_crossing_cam_line_time', table_name='line_crossing_events')
    op.drop_index('idx_crossing_event_time', table_name='line_crossing_events')
    op.drop_index('ix_crossing_events_idempotency', table_name='line_crossing_events')
    op.drop_index('ix_crossing_events_timestamp', table_name='line_crossing_events')
    op.drop_index('ix_crossing_events_direction', table_name='line_crossing_events')
    op.drop_index('ix_crossing_events_track_token', table_name='line_crossing_events')
    op.drop_index('ix_crossing_events_track_session', table_name='line_crossing_events')
    op.drop_index('ix_crossing_events_line_id', table_name='line_crossing_events')
    op.drop_index('ix_crossing_events_camera_code', table_name='line_crossing_events')
    op.drop_index('ix_crossing_events_camera_id', table_name='line_crossing_events')
    op.drop_index('ix_crossing_events_event_id', table_name='line_crossing_events')
    op.drop_table('line_crossing_events')
