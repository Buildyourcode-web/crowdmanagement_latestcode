"""add_step9_frs_fields

Revision ID: a1b2c3d4e5f7
Revises: f6a1b2c3d4e5
Create Date: 2026-09-04 15:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'f6a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend frs_reference_profiles
    op.add_column('frs_reference_profiles', sa.Column('reference_code', sa.String(length=50), nullable=True))
    op.add_column('frs_reference_profiles', sa.Column('embedding_vector', sa.JSON(), nullable=True))
    op.add_column('frs_reference_profiles', sa.Column('embedding_model', sa.String(length=50), server_default='buffalo_l', nullable=False))
    op.add_column('frs_reference_profiles', sa.Column('embedding_version', sa.String(length=50), server_default='1.0.0', nullable=False))
    op.add_column('frs_reference_profiles', sa.Column('active', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('frs_reference_profiles', sa.Column('created_by', sa.String(length=100), nullable=True))
    op.create_index('ix_frs_reference_profiles_reference_code', 'frs_reference_profiles', ['reference_code'])

    # 2. Extend frs_candidates
    op.add_column('frs_candidates', sa.Column('detection_confidence', sa.Float(), nullable=True))
    op.add_column('frs_candidates', sa.Column('quality_score', sa.Float(), nullable=True))
    op.add_column('frs_candidates', sa.Column('review_reason', sa.Text(), nullable=True))
    op.add_column('frs_candidates', sa.Column('model_version', sa.String(length=50), server_default='buffalo_l', nullable=False))
    op.add_column('frs_candidates', sa.Column('embedding_model_version', sa.String(length=50), server_default='insightface-r50', nullable=False))
    op.add_column('frs_candidates', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Revert frs_candidates
    op.drop_column('frs_candidates', 'expires_at')
    op.drop_column('frs_candidates', 'embedding_model_version')
    op.drop_column('frs_candidates', 'model_version')
    op.drop_column('frs_candidates', 'review_reason')
    op.drop_column('frs_candidates', 'quality_score')
    op.drop_column('frs_candidates', 'detection_confidence')

    # Revert frs_reference_profiles
    op.drop_index('ix_frs_reference_profiles_reference_code', table_name='frs_reference_profiles')
    op.drop_column('frs_reference_profiles', 'created_by')
    op.drop_column('frs_reference_profiles', 'active')
    op.drop_column('frs_reference_profiles', 'embedding_version')
    op.drop_column('frs_reference_profiles', 'embedding_model')
    op.drop_column('frs_reference_profiles', 'embedding_vector')
    op.drop_column('frs_reference_profiles', 'reference_code')
