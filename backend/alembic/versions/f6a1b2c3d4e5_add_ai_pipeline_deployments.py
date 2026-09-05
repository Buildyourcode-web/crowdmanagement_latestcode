"""add_ai_pipeline_deployments

Revision ID: f6a1b2c3d4e5
Revises: e5f6a1b2c3d4
Create Date: 2026-09-04 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = 'f6a1b2c3d4e5'
down_revision: Union[str, None] = 'e5f6a1b2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ai_pipeline_deployments',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('camera_id', UUID(as_uuid=True), sa.ForeignKey('cameras.id', ondelete='CASCADE'), nullable=False),
        sa.Column('camera_code', sa.String(length=50), nullable=False),
        sa.Column('profile_id', sa.String(length=50), nullable=False),
        sa.Column('pipeline_type', sa.String(length=50), nullable=False),
        sa.Column('desired_state', sa.String(length=50), server_default='STOPPED', nullable=False),
        sa.Column('actual_state', sa.String(length=50), server_default='STOPPED', nullable=False),
        sa.Column('health_state', sa.String(length=50), server_default='UNKNOWN', nullable=False),
        sa.Column('priority', sa.String(length=20), server_default='NORMAL', nullable=False),
        sa.Column('auto_restart_enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('auto_reconnect_enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('restart_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('reconnect_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('last_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_stopped_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_failure_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.String(length=500), nullable=True),
        sa.Column('process_id', sa.Integer(), nullable=True),
        sa.Column('runtime_instance_id', sa.String(length=100), nullable=True),
        sa.Column('created_by', sa.String(length=100), server_default='SYSTEM', nullable=False),
        sa.Column('updated_by', sa.String(length=100), server_default='SYSTEM', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('camera_id', 'profile_id', name='uq_pipeline_deployment_camera_profile'),
    )

    op.create_index('ix_ai_pipeline_deployments_camera_id', 'ai_pipeline_deployments', ['camera_id'], unique=False)
    op.create_index('ix_ai_pipeline_deployments_camera_code', 'ai_pipeline_deployments', ['camera_code'], unique=False)
    op.create_index('ix_ai_pipeline_deployments_profile_id', 'ai_pipeline_deployments', ['profile_id'], unique=False)
    op.create_index('ix_ai_pipeline_deployments_pipeline_type', 'ai_pipeline_deployments', ['pipeline_type'], unique=False)
    op.create_index('ix_ai_pipeline_deployments_desired_state', 'ai_pipeline_deployments', ['desired_state'], unique=False)
    op.create_index('ix_ai_pipeline_deployments_actual_state', 'ai_pipeline_deployments', ['actual_state'], unique=False)
    op.create_index('ix_deployment_cam_type', 'ai_pipeline_deployments', ['camera_code', 'pipeline_type'], unique=False)
    op.create_index('ix_deployment_states', 'ai_pipeline_deployments', ['desired_state', 'actual_state'], unique=False)


def downgrade() -> None:
    op.drop_table('ai_pipeline_deployments')
