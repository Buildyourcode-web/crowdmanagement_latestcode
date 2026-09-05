"""add_camera_ai_profile_assignments

Revision ID: b2c3d4e5f6a1
Revises: a1b2c3d4e5f6
Create Date: 2026-09-03 17:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a1'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'camera_ai_profile_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('camera_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False),
        sa.Column('camera_code', sa.String(length=50), nullable=False),
        sa.Column('profile_id', sa.String(length=50), nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('assigned_by', sa.String(length=100), server_default='SYSTEM', nullable=False),
        sa.Column('validation_status', sa.String(length=50), server_default='VALID', nullable=False),
        sa.Column('validation_message', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('camera_id', 'profile_id', name='uq_camera_profile_assignment'),
    )

    op.create_index('ix_camera_ai_profile_assignments_camera_id', 'camera_ai_profile_assignments', ['camera_id'], unique=False)
    op.create_index('ix_camera_ai_profile_assignments_camera_code', 'camera_ai_profile_assignments', ['camera_code'], unique=False)
    op.create_index('ix_camera_ai_profile_assignments_profile_id', 'camera_ai_profile_assignments', ['profile_id'], unique=False)
    op.create_index('ix_camera_profile_code', 'camera_ai_profile_assignments', ['camera_code', 'profile_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_camera_profile_code', table_name='camera_ai_profile_assignments')
    op.drop_index('ix_camera_ai_profile_assignments_profile_id', table_name='camera_ai_profile_assignments')
    op.drop_index('ix_camera_ai_profile_assignments_camera_code', table_name='camera_ai_profile_assignments')
    op.drop_index('ix_camera_ai_profile_assignments_camera_id', table_name='camera_ai_profile_assignments')
    op.drop_table('camera_ai_profile_assignments')
