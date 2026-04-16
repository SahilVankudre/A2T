"""
Pydantic schemas — request/response validation for all API endpoints.

Note: POST /api/transcribe uses multipart form data (file + fields),
so its parameters are defined as Form() in main.py, not as a schema here.
These schemas cover everything else: responses, WebSocket messages, etc.

Depends on:  config.py (B01) — MODEL_PRESETS
             models.py (B03) — JobStatus enum
Depended by: main.py (B09) — route type hints and response models
             pipeline.py (B08) — result construction
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from models import JobStatus
from config import MODEL_PRESETS


# ── Word & Segment (transcription output) ─────────────────

class WordSchema(BaseModel):
    """Single word with timing and confidence."""
    word: str
    start: float
    end: float
    probability: float


class SegmentSchema(BaseModel):
    """One transcription segment (typically a sentence or phrase)."""
    id: int
    start: float
    end: float
    text: str
    words: list[WordSchema] = []
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0


# ── Job responses ─────────────────────────────────────────

class JobCreateResponse(BaseModel):
    """Returned immediately after POST /api/transcribe (202 Accepted)."""
    job_id: UUID
    status: JobStatus
    websocket_url: str = Field(description="Connect here for live progress")
    created_at: datetime


class JobResponse(BaseModel):
    """Full job detail for GET /api/jobs/{id}."""
    job_id: UUID
    status: JobStatus
    original_filename: str
    file_size_bytes: int | None = None

    # Audio metadata
    duration_sec: float | None = None
    sample_rate: int | None = None

    # Config used
    model_name: str
    language: str | None = None
    beam_size: int = 5

    # Results (populated when status=completed)
    language_detected: str | None = None
    language_probability: float | None = None
    processing_sec: float | None = None
    rtf: float | None = None
    result_text: str | None = None
    segment_count: int | None = None
    segments: list[SegmentSchema] | None = None

    # Error (populated when status=failed)
    error_message: str | None = None

    # Timestamps
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_job(cls, job, segments: list[SegmentSchema] | None = None) -> "JobResponse":
        """Build response from a Job ORM instance."""
        return cls(
            job_id=job.id,
            status=JobStatus(job.status),
            original_filename=job.original_filename,
            file_size_bytes=job.file_size_bytes,
            duration_sec=job.duration_sec,
            sample_rate=job.sample_rate,
            model_name=job.model_name,
            language=job.language,
            beam_size=job.beam_size,
            language_detected=job.language_detected,
            language_probability=job.language_probability,
            processing_sec=job.processing_sec,
            rtf=job.rtf,
            result_text=job.result_text,
            segment_count=job.segment_count,
            segments=segments,
            error_message=job.error_message,
            created_at=job.created_at,
            completed_at=job.completed_at,
        )


class JobListResponse(BaseModel):
    """Paginated list of jobs for GET /api/jobs."""
    jobs: list[JobResponse]
    total: int
    page: int
    per_page: int


# ── WebSocket messages ────────────────────────────────────

class WSProgressMessage(BaseModel):
    """
    Sent from backend → frontend over WebSocket during transcription.
    Frontend uses 'stage' to show which step is active
    and 'progress' (0.0-1.0) to fill the progress bar.
    """
    type: str = "progress"
    stage: JobStatus
    progress: float = Field(ge=0.0, le=1.0)
    message: str = ""


class WSCompletedMessage(BaseModel):
    """Sent when transcription finishes successfully."""
    type: str = "completed"
    job: JobResponse


class WSErrorMessage(BaseModel):
    """Sent when transcription fails."""
    type: str = "error"
    error: str
    stage: str = ""


# ── Model info ────────────────────────────────────────────

class ModelInfo(BaseModel):
    """One entry in GET /api/models response."""
    name: str
    compute_type: str
    vram_gb: float
    description: str
    is_loaded: bool = False  # True if this is the currently active model


class ModelListResponse(BaseModel):
    """Response for GET /api/models."""
    models: list[ModelInfo]
    active_model: str


# ── Health check ──────────────────────────────────────────

class HealthResponse(BaseModel):
    """Response for GET /api/health."""
    status: str  # "healthy" or "degraded"
    model_loaded: bool
    model_name: str | None = None
    gpu_available: bool
    gpu_name: str | None = None
    vram_total_gb: float | None = None
    database_connected: bool


# ── Error response ────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standard error format for all error responses."""
    error: str
    detail: str | None = None