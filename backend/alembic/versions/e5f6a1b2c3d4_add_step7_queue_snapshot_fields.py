"""add_step7_queue_snapshot_fields

Revision ID: e5f6a1b2c3d4
Revises: d4e5f6a1b2c3
Create Date: 2026-09-04 12:20:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'e5f6a1b2c3d4'
down_revision: Union[str, None] = 'd4e5f6a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('queue_snapshots', sa.Column('camera_id', UUID(as_uuid=True), nullable=True))
    op.add_column('queue_snapshots', sa.Column('camera_code', sa.String(length=50), nullable=True))
    op.add_column('queue_snapshots', sa.Column('profile_id', sa.String(length=50), nullable=True))
    op.add_column('queue_snapshots', sa.Column('zone_id', UUID(as_uuid=True), nullable=True))
    op.add_column('queue_snapshots', sa.Column('occupancy_percent', sa.Float(), nullable=True))
    op.add_column('queue_snapshots', sa.Column('density', sa.Float(), nullable=True))
    op.add_column('queue_snapshots', sa.Column('density_type', sa.String(length=50), server_default='RELATIVE', nullable=True))
    op.add_column('queue_snapshots', sa.Column('queue_length_val', sa.Float(), nullable=True))
    op.add_column('queue_snapshots', sa.Column('queue_length_unit', sa.String(length=50), server_default='normalized_extent', nullable=True))
    op.add_column('queue_snapshots', sa.Column('outflow_rate', sa.Integer(), server_default='0', nullable=True))
    op.add_column('queue_snapshots', sa.Column('max_dwell_seconds', sa.Integer(), server_default='0', nullable=True))
    op.add_column('queue_snapshots', sa.Column('risk_score', sa.Float(), server_default='0.0', nullable=True))

    # Indexes
    op.create_index('idx_queue_snapshots_camera_id', 'queue_snapshots', ['camera_id'], unique=False)
    op.create_index('idx_queue_snapshots_camera_code', 'queue_snapshots', ['camera_code'], unique=False)
    op.create_index('idx_queue_snapshots_cam_time', 'queue_snapshots', ['camera_code', 'timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_queue_snapshots_cam_time', table_name='queue_snapshots')
    op.drop_index('idx_queue_snapshots_camera_code', table_name='queue_snapshots')
    op.drop_index('idx_queue_snapshots_camera_id', table_name='queue_snapshots')

    op.drop_column('queue_snapshots', 'risk_score')
    op.drop_column('queue_snapshots', 'max_dwell_seconds')
    op.drop_column('queue_snapshots', 'outflow_rate')
    op.drop_column('queue_snapshots', 'queue_length_unit')
    op.drop_column('queue_snapshots', 'queue_length_val')
    op.drop_column('queue_snapshots', 'density_type')
    op.drop_column('queue_snapshots', 'density')
    op.drop_column('queue_snapshots', 'occupancy_percent')
    op.drop_column('queue_snapshots', 'zone_id')
    op.drop_column('queue_snapshots', 'profile_id')
    op.drop_column('queue_snapshots', 'camera_code')
    op.drop_column('queue_snapshots', 'camera_id')
