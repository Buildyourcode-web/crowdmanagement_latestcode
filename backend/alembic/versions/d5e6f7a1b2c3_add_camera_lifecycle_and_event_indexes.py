"""add_camera_lifecycle_and_event_indexes

Revision ID: d5e6f7a1b2c3
Revises: c4d5e6f7a1b2
Create Date: 2026-09-13 15:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a1b2c3'
down_revision: Union[str, None] = 'c4d5e6f7a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add camera lifecycle fields
    op.add_column('cameras', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('cameras', sa.Column('active_from', sa.DateTime(timezone=True), nullable=True))
    op.add_column('cameras', sa.Column('removed_at', sa.DateTime(timezone=True), nullable=True))

    op.create_index('ix_cameras_is_active', 'cameras', ['is_active'])
    op.create_index('ix_cameras_event_active', 'cameras', ['event_id', 'is_active'])

    # 2. Add event-scoped indexes on crowd_snapshots
    op.create_index('ix_crowd_event_time', 'crowd_snapshots', ['event_id', 'timestamp'])
    op.create_index('ix_crowd_event_cam_time', 'crowd_snapshots', ['event_id', 'camera_id', 'timestamp'])
    op.create_index('ix_crowd_event_zone_time', 'crowd_snapshots', ['event_id', 'zone_id', 'timestamp'])

    # 3. Add event-scoped indexes on queue_snapshots
    op.create_index('ix_queue_event_time', 'queue_snapshots', ['event_id', 'timestamp'])
    op.create_index('ix_queue_event_cam_time', 'queue_snapshots', ['event_id', 'camera_id', 'timestamp'])

    # 4. Data migration: Associate unassigned Khairatabad entities with KHB-2026
    op.execute("""
        UPDATE cameras
        SET event_id = (SELECT id FROM events WHERE code = 'KHB-2026' LIMIT 1),
            active_from = COALESCE(created_at, now())
        WHERE event_id IS NULL AND camera_code LIKE 'CAM-KHB%';
    """)

    op.execute("""
        UPDATE zones
        SET event_id = (SELECT id FROM events WHERE code = 'KHB-2026' LIMIT 1)
        WHERE event_id IS NULL;
    """)

    op.execute("""
        UPDATE crowd_snapshots
        SET event_id = (SELECT id FROM events WHERE code = 'KHB-2026' LIMIT 1)
        WHERE event_id IS NULL;
    """)

    op.execute("""
        UPDATE queue_snapshots
        SET event_id = (SELECT id FROM events WHERE code = 'KHB-2026' LIMIT 1)
        WHERE event_id IS NULL;
    """)

    op.execute("""
        UPDATE alerts
        SET event_id = (SELECT id FROM events WHERE code = 'KHB-2026' LIMIT 1)
        WHERE event_id IS NULL;
    """)


def downgrade() -> None:
    # Drop indexes on queue_snapshots
    op.drop_index('ix_queue_event_cam_time', table_name='queue_snapshots')
    op.drop_index('ix_queue_event_time', table_name='queue_snapshots')

    # Drop indexes on crowd_snapshots
    op.drop_index('ix_crowd_event_zone_time', table_name='crowd_snapshots')
    op.drop_index('ix_crowd_event_cam_time', table_name='crowd_snapshots')
    op.drop_index('ix_crowd_event_time', table_name='crowd_snapshots')

    # Drop indexes on cameras
    op.drop_index('ix_cameras_event_active', table_name='cameras')
    op.drop_index('ix_cameras_is_active', table_name='cameras')

    # Drop camera lifecycle columns
    op.drop_column('cameras', 'removed_at')
    op.drop_column('cameras', 'active_from')
    op.drop_column('cameras', 'is_active')
