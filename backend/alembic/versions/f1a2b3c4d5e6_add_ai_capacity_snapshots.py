"""add_ai_capacity_snapshots

Revision ID: f1a2b3c4d5e6
Revises: e7b602833276
Create Date: 2026-09-03 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e7b602833276'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ai_capacity_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('server_hostname', sa.String(length=255), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cpu_info', sa.JSON(), nullable=False),
        sa.Column('ram_info', sa.JSON(), nullable=False),
        sa.Column('gpu_info', sa.JSON(), nullable=False),
        sa.Column('runtime_readiness', sa.String(length=50), nullable=False),
        sa.Column('readiness_details', sa.JSON(), nullable=True),
        sa.Column('capacity_snapshot', sa.JSON(), nullable=False),
        sa.Column('calculation_mode', sa.String(length=50), nullable=False, server_default='ESTIMATED'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        'ix_ai_capacity_snapshots_server_hostname',
        'ai_capacity_snapshots',
        ['server_hostname'],
        unique=False,
    )
    op.create_index(
        'ix_ai_capacity_snapshots_timestamp',
        'ai_capacity_snapshots',
        ['timestamp'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_ai_capacity_snapshots_timestamp', table_name='ai_capacity_snapshots')
    op.drop_index('ix_ai_capacity_snapshots_server_hostname', table_name='ai_capacity_snapshots')
    op.drop_table('ai_capacity_snapshots')
