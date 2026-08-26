"""Create conversion_jobs table for async job tracking

Revision ID: 001
Revises:
Create Date: 2026-08-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'conversion_jobs',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('job_type', sa.String(50), nullable=False),
        sa.Column('status', sa.Enum('queued', 'processing', 'completed', 'failed', 'cancelled', name='jobstatus'), nullable=False, server_default='queued'),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('source_filename', sa.String(255), nullable=False),
        sa.Column('source_file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('source_page_count', sa.Integer(), nullable=True),
        sa.Column('result_filename', sa.String(255), nullable=True),
        sa.Column('result_file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('source_file_path', sa.String(512), nullable=True),
        sa.Column('result_file_path', sa.String(512), nullable=True),
        sa.Column('options', sqlite.JSON(), nullable=True),
        sa.Column('user_id', sa.String(36), nullable=True),
        sa.Column('client_ip', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('celery_task_id', sa.String(36), nullable=True),
        sa.Column('processing_seconds', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('celery_task_id', name='uq_celery_task_id')
    )
    op.create_index('ix_job_status_created', 'conversion_jobs', ['status', 'created_at'])
    op.create_index('ix_job_type_status', 'conversion_jobs', ['job_type', 'status'])
    op.create_index('ix_job_expires_at', 'conversion_jobs', ['expires_at'])
    op.create_index('ix_conversion_jobs_job_type', 'conversion_jobs', ['job_type'])
    op.create_index('ix_conversion_jobs_status', 'conversion_jobs', ['status'])
    op.create_index('ix_conversion_jobs_created_at', 'conversion_jobs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_conversion_jobs_created_at', table_name='conversion_jobs')
    op.drop_index('ix_conversion_jobs_status', table_name='conversion_jobs')
    op.drop_index('ix_conversion_jobs_job_type', table_name='conversion_jobs')
    op.drop_index('ix_job_expires_at', table_name='conversion_jobs')
    op.drop_index('ix_job_type_status', table_name='conversion_jobs')
    op.drop_index('ix_job_status_created', table_name='conversion_jobs')
    op.drop_table('conversion_jobs')
