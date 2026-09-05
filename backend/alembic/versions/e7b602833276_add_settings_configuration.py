"""add_settings_configuration

Revision ID: e7b602833276
Revises: None
Create Date: 2026-08-24 18:50:05.119195

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e7b602833276'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Alert Threshold Configs ───────────────────────────────────────────────
    op.create_table(
        'alert_threshold_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('crowd_warning_pct', sa.Float(), nullable=False, server_default='80.0'),
        sa.Column('crowd_high_pct', sa.Float(), nullable=False, server_default='90.0'),
        sa.Column('crowd_critical_pct', sa.Float(), nullable=False, server_default='100.0'),
        sa.Column('crowd_extreme_pct', sa.Float(), nullable=False, server_default='110.0'),
        sa.Column('queue_warning_count', sa.Integer(), nullable=False, server_default='500'),
        sa.Column('queue_critical_count', sa.Integer(), nullable=False, server_default='1000'),
        sa.Column('queue_wait_warning_min', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('queue_wait_critical_min', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('sudden_inflow_pct', sa.Float(), nullable=False, server_default='40.0'),
        sa.Column('reverse_flow_pct', sa.Float(), nullable=False, server_default='25.0'),
        sa.Column('density_growth_rate_pct', sa.Float(), nullable=False, server_default='15.0'),
        sa.Column('camera_offline_sec', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('camera_degraded_sec', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('person_down_sec', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('panic_risk_score', sa.Float(), nullable=False, server_default='0.80'),
        sa.Column('bottleneck_risk_score', sa.Float(), nullable=False, server_default='0.75'),
        sa.Column('config_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_by', sa.String(length=100), nullable=True),
        sa.Column('config_label', sa.String(length=100), nullable=False, server_default='default'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # ── AI Config Settings ───────────────────────────────────────────────────
    op.create_table(
        'ai_config_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('crowd_detection_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('model_name', sa.String(length=100), nullable=False, server_default='YOLO'),
        sa.Column('model_version', sa.String(length=50), nullable=False, server_default='v1'),
        sa.Column('detection_confidence', sa.Float(), nullable=False, server_default='0.50'),
        sa.Column('tracking_algorithm', sa.String(length=50), nullable=False, server_default='ByteTrack'),
        sa.Column('processing_fps', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('people_counting_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('queue_detection_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('bottleneck_detection_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('reverse_flow_detection_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('fall_detection_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('panic_risk_detection_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('config_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # ── FRS Config Settings ──────────────────────────────────────────────────
    op.create_table(
        'frs_config_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('face_detection_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('min_face_size', sa.Integer(), nullable=False, server_default='80'),
        sa.Column('face_quality_threshold', sa.Float(), nullable=False, server_default='0.60'),
        sa.Column('match_threshold', sa.Float(), nullable=False, server_default='0.94'),
        sa.Column('candidate_threshold', sa.Float(), nullable=False, server_default='0.85'),
        sa.Column('max_candidates', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('human_review_required', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('auto_confirmation_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('watchlist_access_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('missing_person_access_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('candidate_retention_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('image_retention_days', sa.Integer(), nullable=False, server_default='90'),
        sa.Column('audit_retention_days', sa.Integer(), nullable=False, server_default='365'),
        sa.Column('config_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # ── Notification Configs ─────────────────────────────────────────────────
    op.create_table(
        'notification_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('inapp_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sms_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('websocket_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('critical_immediate', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('high_immediate', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('medium_grouped', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('low_summary', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_recipients', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('config_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # ── System Configs ───────────────────────────────────────────────────────
    op.create_table(
        'system_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('app_name', sa.String(length=100), nullable=False, server_default='BYC AI Command Center'),
        sa.Column('app_version', sa.String(length=20), nullable=False, server_default='1.0.0'),
        sa.Column('environment', sa.String(length=50), nullable=False, server_default='production'),
        sa.Column('timezone', sa.String(length=50), nullable=False, server_default='Asia/Kolkata'),
        sa.Column('websocket_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('redis_pubsub_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('event_retention_days', sa.Integer(), nullable=False, server_default='90'),
        sa.Column('maintenance_mode', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('maintenance_message', sa.String(length=500), nullable=True),
        sa.Column('config_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )


def downgrade() -> None:
    op.drop_table('system_configs')
    op.drop_table('notification_configs')
    op.drop_table('frs_config_settings')
    op.drop_table('ai_config_settings')
    op.drop_table('alert_threshold_configs')
