"""add_camera_roi_configurations

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-09-03 18:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a1b2'
down_revision: Union[str, None] = 'b2c3d4e5f6a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'camera_roi_configurations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('camera_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False),
        sa.Column('camera_code', sa.String(length=50), nullable=False),
        sa.Column('profile_id', sa.String(length=50), nullable=False),
        sa.Column('roi_type', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('geometry_json', sa.JSON(), nullable=False),
        sa.Column('normalized', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_by', sa.String(length=100), server_default='SYSTEM', nullable=False),
        sa.Column('updated_by', sa.String(length=100), server_default='SYSTEM', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index('ix_camera_roi_configurations_camera_id', 'camera_roi_configurations', ['camera_id'], unique=False)
    op.create_index('ix_camera_roi_configurations_camera_code', 'camera_roi_configurations', ['camera_code'], unique=False)
    op.create_index('ix_camera_roi_configurations_profile_id', 'camera_roi_configurations', ['profile_id'], unique=False)
    op.create_index('ix_camera_roi_configurations_roi_type', 'camera_roi_configurations', ['roi_type'], unique=False)
    op.create_index('ix_camera_roi_lookup', 'camera_roi_configurations', ['camera_code', 'profile_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_camera_roi_lookup', table_name='camera_roi_configurations')
    op.drop_index('ix_camera_roi_configurations_roi_type', table_name='camera_roi_configurations')
    op.drop_index('ix_camera_roi_configurations_profile_id', table_name='camera_roi_configurations')
    op.drop_index('ix_camera_roi_configurations_camera_code', table_name='camera_roi_configurations')
    op.drop_index('ix_camera_roi_configurations_camera_id', table_name='camera_roi_configurations')
    op.drop_table('camera_roi_configurations')
