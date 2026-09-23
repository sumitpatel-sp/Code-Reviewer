"""Add findings, ml_predictions tables and score columns to reports

Revision ID: b2c4d6e8f0a1
Revises: 094e98e263bf
Create Date: 2026-09-14 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c4d6e8f0a1'
down_revision: Union[str, Sequence[str], None] = '094e98e263bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add score columns to reports; create findings and ml_predictions tables."""
    # Add granular score columns to reports
    op.add_column('reports', sa.Column('quality_score', sa.Float(), nullable=False, server_default='0'))
    op.add_column('reports', sa.Column('security_score', sa.Float(), nullable=False, server_default='0'))
    op.add_column('reports', sa.Column('performance_score', sa.Float(), nullable=False, server_default='0'))
    op.add_column('reports', sa.Column('maintainability_score', sa.Float(), nullable=False, server_default='0'))
    op.add_column('reports', sa.Column('testing_score', sa.Float(), nullable=False, server_default='0'))

    # Add finding count columns to reports
    op.add_column('reports', sa.Column('critical_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('reports', sa.Column('high_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('reports', sa.Column('medium_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('reports', sa.Column('low_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('reports', sa.Column('info_count', sa.Integer(), nullable=False, server_default='0'))

    # Create findings table
    op.create_table(
        'findings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('report_id', sa.Integer(), nullable=False),
        sa.Column('finding_id', sa.String(length=100), nullable=False),
        sa.Column('agent', sa.String(length=200), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('confidence', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('file', sa.String(length=500), nullable=True),
        sa.Column('line_start', sa.Integer(), nullable=True),
        sa.Column('line_end', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('impact', sa.Text(), nullable=False),
        sa.Column('recommendation', sa.Text(), nullable=False),
        sa.Column('code_snippet', sa.Text(), nullable=True),
        sa.Column('suggested_fix', sa.Text(), nullable=True),
        sa.Column('merged_from', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_findings_id'), 'findings', ['id'], unique=False)
    op.create_index(op.f('ix_findings_report_id'), 'findings', ['report_id'], unique=False)

    # Create ml_predictions table
    op.create_table(
        'ml_predictions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('report_id', sa.Integer(), nullable=False),
        sa.Column('defect_probability', sa.Float(), nullable=False),
        sa.Column('maintenance_risk', sa.Float(), nullable=False),
        sa.Column('review_priority', sa.String(length=20), nullable=False),
        sa.Column('human_review_recommended', sa.Boolean(), nullable=False),
        sa.Column('top_risk_factors', sa.Text(), nullable=True),
        sa.Column('shap_values', sa.Text(), nullable=True),
        sa.Column('model_version', sa.String(length=20), nullable=False),
        sa.Column('model_used', sa.String(length=50), nullable=False),
        sa.Column('disclaimer', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('report_id'),
    )
    op.create_index(op.f('ix_ml_predictions_id'), 'ml_predictions', ['id'], unique=False)


def downgrade() -> None:
    """Remove findings, ml_predictions tables and score columns from reports."""
    op.drop_index(op.f('ix_ml_predictions_id'), table_name='ml_predictions')
    op.drop_table('ml_predictions')
    op.drop_index(op.f('ix_findings_report_id'), table_name='findings')
    op.drop_index(op.f('ix_findings_id'), table_name='findings')
    op.drop_table('findings')

    for column in ['quality_score', 'security_score', 'performance_score',
                   'maintainability_score', 'testing_score',
                   'critical_count', 'high_count', 'medium_count', 'low_count', 'info_count']:
        op.drop_column('reports', column)
