"""
Pipeline orchestrator — wires preprocessing, transcription, and formatting
together with real-time WebSocket progress updates and DB state tracking.

Runs as an async background task kicked off by main.py. The heavy work
(ffmpeg, GPU inference) runs in a thread via asyncio.to_thread() to
avoid blocking the event loop.

Depends on:  config.py (B01), database.py (B02), models.py (B03),
             preprocessor.py (B05), transcriber.py (B06), postprocessor.py (B07)
Depended by: main.py (B09)
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Awaitable

from sqlalchemy import select

from config import get_settings
from database import async_session
from models import Job, JobStatus
from preprocessor import preprocess_audio, get_audio_info
from transcriber import Transcriber, TranscriptionResult
from postprocessor import save_all_formats
from schemas import (
    WSProgressMessage, WSCompletedMessage, WSErrorMessage,
    JobResponse, SegmentSchema, WordSchema,
)

logger = logging.getLogger(__name__)

# Type for the async notify callback: main.py passes this in
NotifyCallback = Callable[[dict], Awaitable[None]]


def _result_to_segments(result: TranscriptionResult) -> list[SegmentSchema]:
    """Convert transcriber dataclasses to Pydantic schemas for API response."""
    return [
        SegmentSchema(
            id=seg.id,
            start=seg.start,
            end=seg.end,
            text=seg.text,
            words=[
                WordSchema(
                    word=w.word, start=w.start,
                    end=w.end, probability=w.probability,
                )
                for w in seg.words
            ],
            avg_logprob=seg.avg_logprob,
            no_speech_prob=seg.no_speech_prob,
        )
        for seg in result.segments
    ]


async def _update_job(job_id: str, **fields) -> Job:
    """Update a job's fields in the database."""
    async with async_session() as session:
        stmt = select(Job).where(Job.id == job_id)
        db_result = await session.execute(stmt)
        job = db_result.scalar_one()
        for key, value in fields.items():
            setattr(job, key, value)
        await session.commit()
        await session.refresh(job)
        return job


async def run_pipeline(
    job_id: str,
    transcriber: Transcriber,
    notify: NotifyCallback,
) -> None:
    """
    Execute the full transcription pipeline for a job.

    Args:
        job_id:       UUID of the job to process.
        transcriber:  Shared Transcriber instance (model already loaded).
        notify:       Async callback to send WebSocket messages to the client.
                      Accepts a dict that gets JSON-serialized and sent.

    Flow:
        1. Load job from DB
        2. Preprocess audio (ffmpeg → 16kHz mono WAV)
        3. Transcribe (faster-whisper on GPU)
        4. Format outputs (txt, srt, json)
        5. Update job → completed
        6. Send completed message via WebSocket
    """
    settings = get_settings()
    loop = asyncio.get_event_loop()
    current_stage = JobStatus.PENDING.value

    async def send_progress(stage: JobStatus, progress: float, message: str = ""):
        """Send a progress update to the client via WebSocket."""
        msg = WSProgressMessage(
            stage=stage, progress=progress, message=message,
        )
        await notify(msg.model_dump(mode="json"))

    def sync_notify(stage: JobStatus, progress: float, message: str = ""):
        """Thread-safe wrapper for sending progress from sync code (GPU thread)."""
        try:
            future = asyncio.run_coroutine_threadsafe(
                send_progress(stage, progress, message), loop,
            )
            future.result(timeout=5)
        except Exception as e:
            logger.warning("Failed to send progress update: %s", e)

    try:
        # ── Load job from DB ──────────────────────────────
        async with async_session() as session:
            db_result = await session.execute(select(Job).where(Job.id == job_id))
            job = db_result.scalar_one_or_none()

        if job is None:
            logger.error("Job not found: %s", job_id)
            return

        file_path = Path(job.file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Upload not found: {file_path}")

        # ── Stage 1: Preprocess ───────────────────────────
        current_stage = JobStatus.PREPROCESSING.value
        await _update_job(job_id, status=current_stage)
        await send_progress(JobStatus.PREPROCESSING, 0.0, "Normalizing audio...")

        # Build output paths
        job_output_dir = settings.output_dir / str(job_id)
        job_output_dir.mkdir(parents=True, exist_ok=True)
        preprocessed_path = job_output_dir / "preprocessed.wav"

        # Run ffmpeg in a thread (CPU-bound, ~1-2 seconds)
        audio_info = await asyncio.to_thread(
            preprocess_audio, file_path, preprocessed_path,
        )

        await _update_job(
            job_id,
            duration_sec=audio_info.duration_sec,
            sample_rate=audio_info.sample_rate,
        )
        await send_progress(JobStatus.PREPROCESSING, 1.0, "Audio normalized")

        # ── Stage 2: Transcribe ───────────────────────────
        current_stage = JobStatus.TRANSCRIBING.value
        await _update_job(job_id, status=current_stage)
        await send_progress(JobStatus.TRANSCRIBING, 0.0, "Starting transcription...")

        # Transcription progress callback (runs in GPU thread)
        def on_transcribe_progress(progress: float, message: str):
            sync_notify(JobStatus.TRANSCRIBING, progress, message)

        # Run inference in a thread (GPU-bound, the main wait)
        result: TranscriptionResult = await asyncio.to_thread(
            transcriber.transcribe,
            preprocessed_path,
            language=job.language,
            beam_size=job.beam_size,
            vad_filter=job.vad_filter,
            word_timestamps=True,
            initial_prompt=job.initial_prompt,
            on_progress=on_transcribe_progress,
        )

        await send_progress(JobStatus.TRANSCRIBING, 1.0, "Transcription complete")

        # ── Stage 3: Format outputs ───────────────────────
        current_stage = JobStatus.FORMATTING.value
        await _update_job(job_id, status=current_stage)
        await send_progress(JobStatus.FORMATTING, 0.0, "Generating output files...")

        saved_files = await asyncio.to_thread(
            save_all_formats, result, job_output_dir, str(job_id),
            ["txt", "srt", "vtt", "json"],
        )

        await send_progress(JobStatus.FORMATTING, 1.0, "Outputs ready")

        # Clean up preprocessed file (keep originals + outputs)
        preprocessed_path.unlink(missing_ok=True)

        # ── Stage 4: Complete ─────────────────────────────
        now = datetime.now(timezone.utc)
        text_preview = result.text[:500] if result.text else ""

        job = await _update_job(
            job_id,
            status=JobStatus.COMPLETED.value,
            language_detected=result.language,
            language_probability=result.language_probability,
            processing_sec=result.processing_time,
            result_text=text_preview,
            result_dir=str(job_output_dir),
            segment_count=len(result.segments),
            completed_at=now,
        )

        # Build the completed response with segments
        segments = _result_to_segments(result)
        job_response = JobResponse.from_job(job, segments=segments)
        completed_msg = WSCompletedMessage(job=job_response)
        await notify(completed_msg.model_dump(mode="json"))

        logger.info(
            "Pipeline complete: job=%s, duration=%.1fs, processing=%.1fs, "
            "rtf=%.3f, segments=%d, language=%s",
            job_id, result.duration, result.processing_time,
            result.rtf, len(result.segments), result.language,
        )

    except Exception as e:
        logger.exception("Pipeline failed: job=%s, stage=%s", job_id, current_stage)

        # Update job as failed
        try:
            await _update_job(
                job_id,
                status=JobStatus.FAILED.value,
                error_message=str(e),
            )
        except Exception:
            logger.exception("Failed to update job status to FAILED")

        # Notify client of failure
        try:
            error_msg = WSErrorMessage(error=str(e), stage=current_stage)
            await notify(error_msg.model_dump(mode="json"))
        except Exception:
            logger.exception("Failed to send error notification")