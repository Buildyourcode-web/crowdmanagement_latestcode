"""add_locations_and_location_access

Revision ID: g8c9d0e1f2a3
Revises: f7b8c9d0e1f2
Create Date: 2026-09-28 12:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'g8c9d0e1f2a3'
down_revision: Union[str, None] = 'f7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create locations table
    op.create_table(
        'locations',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('city', sa.String(length=100), nullable=False),
        sa.Column('state', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('access_code_hash', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='ACTIVE', nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_by', sa.String(length=100), nullable=True),
        sa.Column('updated_by', sa.String(length=100), nullable=True),
    )
    op.create_index('ix_locations_code', 'locations', ['code'], unique=True)
    op.create_index('ix_locations_status', 'locations', ['status'])

    # 2. Create location_verifications table (temporary OTP records with expiry & rate-limiting)
    op.create_table(
        'location_verifications',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('location_code', sa.String(length=50), nullable=True),
        sa.Column('code_hash', sa.String(length=255), nullable=False),
        sa.Column('purpose', sa.String(length=50), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_used', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_location_verifications_email', 'location_verifications', ['email'])

    # 3. Add additive nullable location_id to events table (strictly non-destructive to existing events)
    op.add_column(
        'events',
        sa.Column('location_id', UUID(as_uuid=True), sa.ForeignKey('locations.id', ondelete='SET NULL'), nullable=True)
    )
    op.create_index('ix_events_location_id', 'events', ['location_id'])


def downgrade() -> None:
    # Schema-level rollback only; production downgrade must be deliberate
    op.drop_index('ix_events_location_id', table_name='events')
    op.drop_column('events', 'location_id')
    op.drop_table('location_verifications')
    op.drop_table('locations')
