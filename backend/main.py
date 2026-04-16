"""
FastAPI application — routes, WebSocket, lifespan, error handlers.

This is the entry point. Run with: uvicorn main:app --reload --port 8000

Depends on: ALL backend files (B01-B08)
"""

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect,
    HTTPException, Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select, func

from config import get_settings, MODEL_PRESETS
from database import engine, async_session, check_db_connection
from models import Job, JobStatus
from schemas import (
    JobCreateResponse, JobResponse, JobListResponse,
    HealthResponse, ModelInfo, ModelListResponse, ErrorResponse,
    SegmentSchema, WordSchema,
)
from preprocessor import validate_audio_file, check_ffmpeg, SUPPORTED_EXTENSIONS
from transcriber import Transcriber
from pipeline import run_pipeline

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


# ── WebSocket connection manager ──────────────────────────

class ConnectionManager:
    """Tracks active WebSocket connections per job_id."""

    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, job_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(job_id, []).append(ws)
        logger.info("WS connected: job=%s (total=%d)", job_id, len(self._connections[job_id]))

    def disconnect(self, job_id: str, ws: WebSocket):
        if job_id in self._connections:
            self._connections[job_id] = [c for c in self._connections[job_id] if c != ws]
            if not self._connections[job_id]:
                del self._connections[job_id]

    async def send_to_job(self, job_id: str, message: dict):
        """Send a message to all WebSocket clients watching a job."""
        if job_id not in self._connections:
            return
        dead = []
        for ws in self._connections[job_id]:
            try:
                await ws.send_json(message)
            except Exception as e:
                logger.warning("WS send failed for job=%s: %s", job_id, e)
                dead.append(ws)
        for ws in dead:
            self.disconnect(job_id, ws)


manager = ConnectionManager()


# ── Shared transcriber instance ───────────────────────────

_transcriber: Transcriber | None = None


def get_transcriber() -> Transcriber:
    if _transcriber is None:
        raise RuntimeError("Model not loaded. Server is still starting up.")
    return _transcriber


# ── Lifespan — model loading on startup ───────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _transcriber
    settings = get_settings()

    logger.info("Starting VoxScript POC...")

    # Check ffmpeg
    if not check_ffmpeg():
        logger.error("ffmpeg not found! Install it: https://www.gyan.dev/ffmpeg/builds/")

    # Load ASR model (10-30 seconds)
    logger.info("Loading ASR model: %s (%s)", settings.asr_model, settings.asr_compute_type)
    _transcriber = Transcriber()
    await asyncio.to_thread(_transcriber.load_model)
    logger.info("Model loaded. Server ready.")

    yield

    # Shutdown
    logger.info("Shutting down...")
    if _transcriber:
        _transcriber.unload_model()
    await engine.dispose()


# ── App setup ─────────────────────────────────────────────

settings = get_settings()

app = FastAPI(
    title="VoxScript POC",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # "*" "settings.frontend_origin, "http://localhost:3000""
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Exception handlers ────────────────────────────────────

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=exc.detail).model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(error="Internal server error", detail=str(exc)).model_dump(),
    )


# ── Helper: build JobResponse with segments from disk ─────

async def _load_job_response(job: Job) -> JobResponse:
    """Build a JobResponse, loading segments from the JSON file if completed."""
    segments = None
    if job.status == JobStatus.COMPLETED.value and job.result_dir:
        json_path = Path(job.result_dir) / f"{job.id}.json"
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                segments = [
                    SegmentSchema(
                        id=s["id"], start=s["start"], end=s["end"], text=s["text"],
                        words=[WordSchema(**w) for w in s.get("words", [])],
                        avg_logprob=s.get("avg_logprob", 0),
                        no_speech_prob=s.get("no_speech_prob", 0),
                    )
                    for s in data.get("segments", [])
                ]
            except Exception as e:
                logger.warning("Failed to load segments JSON: %s", e)
    return JobResponse.from_job(job, segments=segments)


# ── Routes: Transcription ─────────────────────────────────

@app.post("/api/transcribe", response_model=JobCreateResponse, status_code=202)
async def create_transcription(
    file: UploadFile = File(...),
    model: str = Form(default="large-v3-turbo"),
    language: str | None = Form(default=None),
    beam_size: int = Form(default=5),
    vad_filter: bool = Form(default=True),
    initial_prompt: str | None = Form(default=None),
):
    """Upload audio and start transcription. Returns job_id immediately."""
    transcriber = get_transcriber()

    # Generate job ID and save uploaded file
    job_id = uuid.uuid4()
    ext = Path(file.filename).suffix.lower() if file.filename else ".wav"
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported format: {ext}. Supported: {sorted(SUPPORTED_EXTENSIONS)}")

    upload_path = settings.upload_dir / f"{job_id}{ext}"
    content = await file.read()
    upload_path.write_bytes(content)

    # Validate the saved file
    is_valid, msg = validate_audio_file(upload_path)
    if not is_valid:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(400, msg)

    # Create job in database
    now = datetime.now(timezone.utc)
    job = Job(
        id=job_id,
        status=JobStatus.PENDING.value,
        original_filename=file.filename or "upload",
        file_path=str(upload_path),
        file_size_bytes=len(content),
        model_name=model,
        language=language,
        beam_size=beam_size,
        vad_filter=vad_filter,
        initial_prompt=initial_prompt,
    )

    async with async_session() as session:
        session.add(job)
        await session.commit()

    # Start pipeline as background task
    async def notify(msg: dict):
        await manager.send_to_job(str(job_id), msg)

    asyncio.create_task(run_pipeline(str(job_id), transcriber, notify))

    return JobCreateResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        websocket_url=f"/ws/{job_id}",
        created_at=now,
    )


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: uuid.UUID):
    """Get job status, results, and segments."""
    async with async_session() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(404, f"Job not found: {job_id}")

    return await _load_job_response(job)


@app.get("/api/jobs/{job_id}/download")
async def download_result(
    job_id: uuid.UUID,
    format: str = Query(default="txt", pattern="^(txt|srt|vtt|json)$"),
):
    """Download transcription result in the specified format."""
    async with async_session() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(404, f"Job not found: {job_id}")

    if job.status != JobStatus.COMPLETED.value:
        raise HTTPException(409, f"Job not completed (status: {job.status})")

    file_path = Path(job.result_dir) / f"{job_id}.{format}"
    if not file_path.exists():
        raise HTTPException(404, f"Output file not found: {format}")

    media_types = {
        "txt": "text/plain",
        "srt": "application/x-subrip",
        "vtt": "text/vtt",
        "json": "application/json",
    }

    # Build download filename from original name
    base_name = Path(job.original_filename).stem
    return FileResponse(
        file_path,
        media_type=media_types.get(format, "application/octet-stream"),
        filename=f"{base_name}.{format}",
    )


@app.get("/api/jobs/{job_id}/audio")
async def get_audio(job_id: uuid.UUID):
    """Serve the uploaded audio file (for frontend waveform player)."""
    async with async_session() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(404, f"Job not found: {job_id}")

    file_path = Path(job.file_path)
    if not file_path.exists():
        raise HTTPException(404, "Audio file no longer available")

    return FileResponse(file_path, media_type="audio/mpeg")


@app.get("/api/jobs", response_model=JobListResponse)
async def list_jobs(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
):
    """List recent transcription jobs with pagination."""
    async with async_session() as session:
        query = select(Job).order_by(Job.created_at.desc())
        count_query = select(func.count()).select_from(Job)

        if status:
            query = query.where(Job.status == status)
            count_query = count_query.where(Job.status == status)

        total = (await session.execute(count_query)).scalar() or 0
        query = query.offset((page - 1) * per_page).limit(per_page)
        result = await session.execute(query)
        jobs = result.scalars().all()

    job_responses = [await _load_job_response(j) for j in jobs]
    return JobListResponse(jobs=job_responses, total=total, page=page, per_page=per_page)


@app.delete("/api/jobs/{job_id}", status_code=204)
async def delete_job(job_id: uuid.UUID):
    """Delete a job and its associated files."""
    async with async_session() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()

        if job is None:
            raise HTTPException(404, f"Job not found: {job_id}")

        # Delete files from disk
        if job.file_path:
            Path(job.file_path).unlink(missing_ok=True)
        if job.result_dir:
            import shutil
            shutil.rmtree(job.result_dir, ignore_errors=True)

        await session.delete(job)
        await session.commit()


# ── Routes: Models ────────────────────────────────────────

@app.get("/api/models", response_model=ModelListResponse)
async def list_models():
    """List available ASR models and which one is currently loaded."""
    transcriber = get_transcriber()
    models = [
        ModelInfo(
            name=m["name"],
            compute_type=m["compute_type"],
            vram_gb=m["vram_gb"],
            description=m["description"],
            is_loaded=(m["name"] == transcriber.model_name),
        )
        for m in MODEL_PRESETS.values()
    ]
    return ModelListResponse(models=models, active_model=transcriber.model_name)


# ── Routes: Health ────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """System health: model status, GPU info, database connectivity."""
    transcriber = _transcriber
    db_ok = await check_db_connection()

    gpu_available = False
    gpu_name = None
    vram_total = None
    try:
        import torch
        gpu_available = torch.cuda.is_available()
        if gpu_available:
            gpu_name = torch.cuda.get_device_name(0)
            vram_total = round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1)
    except ImportError:
        pass

    return HealthResponse(
        status="healthy" if (transcriber and transcriber.is_loaded and db_ok) else "degraded",
        model_loaded=transcriber.is_loaded if transcriber else False,
        model_name=transcriber.model_name if transcriber else None,
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        vram_total_gb=vram_total,
        database_connected=db_ok,
    )


# ── WebSocket endpoint ────────────────────────────────────

@app.websocket("/ws/{job_id}")
async def websocket_endpoint(ws: WebSocket, job_id: str):
    """
    Live progress stream for a transcription job.
    On connect, sends current job state (handles race condition where
    pipeline completes before WS connects).
    """
    await manager.connect(job_id, ws)
    try:
        # Send current job state immediately on connect
        # This handles the race condition where pipeline finishes
        # before the frontend WebSocket connects
        try:
            async with async_session() as session:
                result = await session.execute(select(Job).where(Job.id == job_id))
                job = result.scalar_one_or_none()

            if job and job.status == JobStatus.COMPLETED.value:
                job_response = await _load_job_response(job)
                await ws.send_json({"type": "completed", "job": job_response.model_dump(mode="json")})
            elif job and job.status == JobStatus.FAILED.value:
                await ws.send_json({"type": "error", "error": job.error_message or "Unknown error", "stage": ""})
            elif job:
                await ws.send_json({"type": "progress", "stage": job.status, "progress": 0.5, "message": f"Currently {job.status}..."})
        except Exception as e:
            logger.warning("Failed to send initial WS state: %s", e)

        # Keep connection alive until client disconnects
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(job_id, ws)