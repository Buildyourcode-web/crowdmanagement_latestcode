"""add_step6_crowd_snapshot_fields

Revision ID: d4e5f6a1b2c3
Revises: c3d4e5f6a1b2
Create Date: 2026-09-04 11:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a1b2c3'
down_revision: Union[str, None] = 'c3d4e5f6a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to crowd_snapshots
    op.add_column('crowd_snapshots', sa.Column('camera_code', sa.String(length=50), nullable=True))
    op.add_column('crowd_snapshots', sa.Column('profile_id', sa.String(length=50), nullable=True))
    op.add_column('crowd_snapshots', sa.Column('risk_score', sa.Float(), nullable=True, server_default='0.0'))

    # Indexes
    op.create_index('idx_crowd_snapshots_camera_code', 'crowd_snapshots', ['camera_code'], unique=False)
    op.create_index('idx_crowd_snapshots_cam_time', 'crowd_snapshots', ['camera_code', 'timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_crowd_snapshots_cam_time', table_name='crowd_snapshots')
    op.drop_index('idx_crowd_snapshots_camera_code', table_name='crowd_snapshots')
    op.drop_column('crowd_snapshots', 'risk_score')
    op.drop_column('crowd_snapshots', 'profile_id')
    op.drop_column('crowd_snapshots', 'camera_code')
