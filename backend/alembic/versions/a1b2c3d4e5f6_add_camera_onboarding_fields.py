"""add_camera_onboarding_fields

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-09-03 17:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new onboarding and stream management columns to cameras table
    op.add_column('cameras', sa.Column('description', sa.String(length=500), nullable=True))
    op.add_column('cameras', sa.Column('private_ip', sa.String(length=50), nullable=True))
    op.add_column('cameras', sa.Column('port', sa.Integer(), server_default='554', nullable=True))
    op.add_column('cameras', sa.Column('username', sa.String(length=100), nullable=True))
    op.add_column('cameras', sa.Column('password_encrypted', sa.String(length=500), nullable=True))
    op.add_column('cameras', sa.Column('codec', sa.String(length=50), server_default='h264', nullable=True))
    op.add_column('cameras', sa.Column('protocol', sa.String(length=20), server_default='rtsp', nullable=True))
    op.add_column('cameras', sa.Column('location_name', sa.String(length=200), nullable=True))
    op.add_column('cameras', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('cameras', sa.Column('longitude', sa.Float(), nullable=True))
    op.add_column('cameras', sa.Column('stream_status', sa.String(length=50), server_default='NOT_TESTED', nullable=False))
    op.add_column('cameras', sa.Column('stream_stability', sa.String(length=50), server_default='UNKNOWN', nullable=False))
    op.add_column('cameras', sa.Column('enabled', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('cameras', sa.Column('reconnect_count', sa.Integer(), server_default='0', nullable=False))
    op.add_column('cameras', sa.Column('last_error', sa.String(length=500), nullable=True))
    op.add_column('cameras', sa.Column('last_tested_at', sa.DateTime(timezone=True), nullable=True))

    op.create_index('ix_cameras_private_ip', 'cameras', ['private_ip'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_cameras_private_ip', table_name='cameras')
    op.drop_column('cameras', 'last_tested_at')
    op.drop_column('cameras', 'last_error')
    op.drop_column('cameras', 'reconnect_count')
    op.drop_column('cameras', 'enabled')
    op.drop_column('cameras', 'stream_stability')
    op.drop_column('cameras', 'stream_status')
    op.drop_column('cameras', 'longitude')
    op.drop_column('cameras', 'latitude')
    op.drop_column('cameras', 'location_name')
    op.drop_column('cameras', 'protocol')
    op.drop_column('cameras', 'codec')
    op.drop_column('cameras', 'password_encrypted')
    op.drop_column('cameras', 'username')
    op.drop_column('cameras', 'port')
    op.drop_column('cameras', 'private_ip')
    op.drop_column('cameras', 'description')
