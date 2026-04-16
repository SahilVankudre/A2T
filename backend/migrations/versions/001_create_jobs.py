"""create jobs table

Revision ID: 001
Revises: None
Create Date: 2026-04-13
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        # Primary key
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Status
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),

        # Upload info
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),

        # Audio metadata
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("sample_rate", sa.Integer(), nullable=True),

        # Model configuration
        sa.Column("model_name", sa.String(100), nullable=False, server_default="large-v3-turbo"),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("beam_size", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("vad_filter", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("initial_prompt", sa.Text(), nullable=True),

        # Results
        sa.Column("language_detected", sa.String(10), nullable=True),
        sa.Column("language_probability", sa.Float(), nullable=True),
        sa.Column("processing_sec", sa.Float(), nullable=True),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("result_dir", sa.Text(), nullable=True),
        sa.Column("segment_count", sa.Integer(), nullable=True),

        # Error
        sa.Column("error_message", sa.Text(), nullable=True),

        # Timestamps
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Indexes for common queries
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_created_at", "jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_created_at", table_name="jobs")
    op.drop_index("ix_jobs_status", table_name="jobs")
    op.drop_table("jobs")