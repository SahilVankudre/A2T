"""
Job ORM model — the central entity of the system.

Every transcription request creates one Job row that tracks its
lifecycle from upload through completion or failure.

Depends on:  database.py (B02) — Base, TimestampMixin
Depended by: schemas.py (B04), pipeline.py (B08), main.py (B09), migrations
"""

import uuid
import enum
from datetime import datetime

from sqlalchemy import String, Float, Text, Boolean, Integer, Index, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base, TimestampMixin


class JobStatus(str, enum.Enum):
    """Job lifecycle states. Stored as varchar in PostgreSQL."""
    PENDING = "pending"
    PREPROCESSING = "preprocessing"
    TRANSCRIBING = "transcribing"
    FORMATTING = "formatting"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20), default=JobStatus.PENDING.value, nullable=False
    )

    # Upload info
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)  # Path to uploaded file
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=True)

    # Audio metadata (populated after preprocessing)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Model configuration used for this job
    model_name: Mapped[str] = mapped_column(String(100), default="large-v3-turbo")
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)  # Requested
    beam_size: Mapped[int] = mapped_column(Integer, default=5)
    vad_filter: Mapped[bool] = mapped_column(Boolean, default=True)
    initial_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Results (populated after transcription)
    language_detected: Mapped[str | None] = mapped_column(String(10), nullable=True)
    language_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # Full transcript
    result_dir: Mapped[str | None] = mapped_column(Text, nullable=True)   # Path to output files
    segment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Error info (populated on failure)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Completion timestamp (separate from updated_at for precise RTF calculation)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_created_at", "created_at"),
    )

    @property
    def rtf(self) -> float | None:
        """Real-Time Factor: processing_time / audio_duration."""
        if self.processing_sec and self.duration_sec and self.duration_sec > 0:
            return self.processing_sec / self.duration_sec
        return None

    def __repr__(self) -> str:
        return f"<Job {self.id} status={self.status} file={self.original_filename}>"