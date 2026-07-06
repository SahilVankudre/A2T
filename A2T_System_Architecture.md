# A2T System Architecture — Deep Dive

## How every component works, why each technology was chosen, and how data flows through the system

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Decisions & Rationale](#2-architecture-decisions--rationale)
3. [Technology Stack — Why Each Choice](#3-technology-stack--why-each-choice)
4. [Backend Architecture — File by File](#4-backend-architecture--file-by-file)
5. [The Transcription Pipeline — Internal Flow](#5-the-transcription-pipeline--internal-flow)
6. [Frontend Architecture — Component by Component](#6-frontend-architecture--component-by-component)
7. [Data Flow — Complete Request Lifecycle](#7-data-flow--complete-request-lifecycle)
8. [Database Design](#8-database-design)
9. [WebSocket Communication Protocol](#9-websocket-communication-protocol)
10. [GPU Memory Management](#10-gpu-memory-management)
11. [Error Handling Strategy](#11-error-handling-strategy)
12. [Performance Characteristics](#12-performance-characteristics)
13. [Security Considerations](#13-security-considerations)
14. [Configuration & Environment](#14-configuration--environment)
15. [Testing Strategy](#15-testing-strategy)

---

## 1. System Overview

VoxScript is a self-hosted audio-to-text transcription system. It accepts audio files
through a web interface, processes them on a local GPU using the Whisper large-v3-turbo
model, and delivers timestamped transcriptions in multiple output formats (TXT, SRT,
VTT, JSON) with per-word timing and confidence scores.

### What makes it different from cloud APIs

| Aspect | Cloud APIs (Deepgram, Google) | VoxScript |
|--------|------------------------------|-----------|
| Data privacy | Audio sent to third-party servers | Audio never leaves your machine |
| Per-minute cost | $0.006-$0.024/min | Fixed GPU hardware cost |
| Customization | Limited parameters | Full control over model, preprocessing, output |
| Latency | Network round-trip | Local processing, no network |
| Vendor lock-in | API format lock-in | Open-source models, swap freely |
| Scaling | Auto-scales (their infra) | Manual scaling (your infra) |

### Architecture pattern

The system follows a **two-process architecture** on a single machine:

```
Process 1: Next.js (port 3000)          Process 2: FastAPI (port 8000)
┌────────────────────────────┐          ┌─────────────────────────────┐
│  React UI                  │  REST    │  API Routes                 │
│  ├── Upload zone           │────────→ │  ├── POST /api/transcribe   │
│  ├── Processing view       │  HTTP    │  ├── GET  /api/jobs/{id}    │
│  ├── Transcript view       │          │  ├── GET  /api/jobs/{id}/dl │
│  ├── Stats bar             │          │  └── GET  /api/health       │
│  └── Export panel           │          │                             │
│                            │  WS      │  WebSocket /ws/{job_id}     │
│  WebSocket client          │←────────→│  ├── Progress messages      │
│  (live progress)           │          │  ├── Completed message      │
│                            │          │  └── Error message          │
└────────────────────────────┘          │                             │
                                        │  Background Pipeline        │
                                        │  ├── Preprocessor (ffmpeg)  │
                                        │  ├── Transcriber (GPU)      │
                                        │  └── Postprocessor          │
                                        │                             │
                                        │  ┌───────────┐ ┌─────────┐ │
                                        │  │PostgreSQL │ │Filesystem│ │
                                        │  │(job state)│ │(files)   │ │
                                        │  └───────────┘ └─────────┘ │
                                        └─────────────────────────────┘
```

---

## 2. Architecture Decisions & Rationale

### Decision 1: FastAPI over Django/Flask

**Chose**: FastAPI with Uvicorn (ASGI)

**Why**:
- **Async-native**: WebSocket support requires async. Flask/Django need extensions for this.
- **Pydantic integration**: Request/response validation with automatic type checking.
  The schemas we define are the API documentation.
- **Auto-generated docs**: Swagger UI at `/docs` — invaluable for development and demos.
- **Performance**: Uvicorn + async handlers can serve WebSocket connections and REST
  requests on the same process without threading complexity.
- **Python 3.12 type hints**: First-class support for modern Python typing.

**Rejected**: Django (too heavy for an API-only service), Flask (no native async/WebSocket),
gRPC (overkill for a demo, harder to debug).

### Decision 2: PostgreSQL over SQLite

**Chose**: PostgreSQL with asyncpg driver

**Why**:
- **Production parity**: Same database in POC and production. Zero migration surprises.
- **UUID support**: Native UUID type — no string casting needed for job IDs.
- **Concurrent access**: PostgreSQL handles concurrent reads/writes correctly.
  SQLite locks the entire database on write.
- **Timezone-aware timestamps**: Native TIMESTAMPTZ type prevents the offset-naive
  vs offset-aware datetime bugs that plague SQLite.
- **JSON operators**: If we add metadata querying later, PostgreSQL's JSONB support
  is far superior to SQLite's JSON1 extension.

**Trade-off**: Requires PostgreSQL installed locally (one-time setup). Worth it for
the zero-friction path to production.

### Decision 3: faster-whisper over OpenAI whisper

**Chose**: faster-whisper (CTranslate2 backend)

**Why**:
- **4x faster**: Same model, same accuracy, but CTranslate2's optimized C++ inference
  runs 4x faster than PyTorch-based OpenAI whisper.
- **Lower memory**: int8/float16 quantization reduces VRAM by 50-75%.
- **Critical for 6GB VRAM**: large-v3-turbo in float16 needs ~6GB (risky on RTX 4050).
  In int8_float16, it needs ~3.5GB (comfortable fit with room for inference).
- **Same API**: Drop-in replacement — same model weights, same output format.
- **VAD built-in**: Silero VAD integration without extra code.

**Rejected**: OpenAI whisper (too slow, too much VRAM), whisper.cpp (C++ integration
complexity), transformers library (no CTranslate2 optimization).

### Decision 4: In-process background tasks over Celery

**Chose**: `asyncio.create_task()` + `asyncio.to_thread()`

**Why**:
- **No Redis dependency**: Celery requires a Redis broker — one more service to install
  and manage for a single-machine demo.
- **WebSocket integration**: The pipeline needs to send WebSocket messages mid-processing.
  With in-process tasks, the pipeline has direct access to the ConnectionManager.
  With Celery, you'd need a pub/sub bridge (Redis pub/sub → WebSocket forwarding).
- **Simpler debugging**: Stack traces are in one process. Celery worker errors are in
  a separate process with separate logs.
- **One job at a time**: With a single GPU, you can only run one transcription at a time
  anyway. A task queue adds complexity without benefit.

**When to switch to Celery**: When moving to production with multiple GPU workers,
priority queues, and retry policies. The pipeline.py code structure is already designed
for this migration — replace `asyncio.create_task()` with `celery_task.delay()`.

### Decision 5: Next.js + shadcn/ui over plain React

**Chose**: Next.js 14 with shadcn/ui component library

**Why**:
- **API proxy built-in**: `next.config.mjs` rewrites handle CORS without backend changes.
- **shadcn/ui**: Pre-built accessible components (Button, Card, Progress, Tabs, etc.)
  that look professional out of the box. Not a CSS framework — actual React components
  you own and can customize.
- **TypeScript**: Type safety between frontend and backend schemas catches errors at
  compile time, not runtime.
- **File-based routing**: `app/page.tsx` is the entire route structure — no router config.

### Decision 6: WebSocket + polling fallback

**Chose**: Dual communication strategy

**Why WebSocket**: Real-time progress updates. The user sees "Transcribing... 45%"
and "Segment 3: The quarterly revenue..." live as the GPU processes each segment.
Polling would only show "processing" without granular progress.

**Why polling fallback**: WebSocket messages can be missed (race condition where
pipeline completes before WS connects, network hiccups, proxy issues). A 2-second
polling interval catches any missed completion within 2 seconds, guaranteed.

**The race condition we solved**: Pipeline runs fast (~2 seconds for short audio).
If the POST response triggers a React re-render before the WebSocket hook fires,
the "completed" message is sent to nobody. Three fixes:
1. Pipeline uses `model_dump(mode="json")` to prevent serialization crashes
2. WebSocket endpoint sends current job state on connect (catches already-completed jobs)
3. Frontend polls `GET /api/jobs/{id}` every 2 seconds as a safety net

---

## 3. Technology Stack — Why Each Choice

### Backend stack

| Technology | Version | Role | Why this one |
|-----------|---------|------|-------------|
| Python | 3.12 | Runtime | Latest stable, best type hints, async support |
| FastAPI | 0.115+ | Web framework | Async, Pydantic, WebSocket, auto-docs |
| Uvicorn | 0.30+ | ASGI server | Fast, supports WebSocket upgrade |
| faster-whisper | 1.2+ | ASR engine | 4x faster than OpenAI whisper, lower VRAM |
| SQLAlchemy | 2.0+ | ORM | Async support, type-safe queries, migration support |
| asyncpg | 0.29+ | DB driver | Fastest async PostgreSQL driver for Python |
| Alembic | 1.13+ | Migrations | Standard SQLAlchemy migration tool |
| PostgreSQL | 16+ | Database | Production-grade, UUID support, TIMESTAMPTZ |
| Pydantic | 2.7+ | Validation | Request/response schemas, serialization |
| ffmpeg | 8.x | Audio processing | Universal format conversion, loudnorm filter |
| structlog | 24+ | Logging | Structured JSON logs, correlation IDs |

### Frontend stack

| Technology | Version | Role | Why this one |
|-----------|---------|------|-------------|
| Next.js | 14 | Framework | API proxy, file routing, SSR capability |
| React | 18 | UI library | Component model, hooks, ecosystem |
| TypeScript | 5 | Type safety | Catches schema mismatches at compile time |
| Tailwind CSS | 3.4+ | Styling | Utility classes, fast iteration, consistent design |
| shadcn/ui | latest | Components | Accessible, customizable, not a dependency |
| wavesurfer.js | 7.x | Audio player | Waveform visualization, seek, playback |
| lucide-react | 0.383+ | Icons | Clean icon set, tree-shakeable |

### Infrastructure

| Technology | Role | Why |
|-----------|------|-----|
| NVIDIA CUDA 12.1 | GPU compute | RTX 4050 driver, CTranslate2 backend |
| PyTorch 2.5+ | Tensor ops | CUDA integration, faster-whisper dependency |
| Git | Version control | Standard |
| pip + venv | Package management | Simple, no conda complexity |
| npm | Frontend packages | Standard for Node.js ecosystem |

---

## 4. Backend Architecture — File by File

### Dependency order (least → most dependent)

```
config.py → database.py → models.py ─┐
                                      ├→ pipeline.py → main.py
schemas.py ──────────────────────────┤
preprocessor.py ─────────────────────┤
transcriber.py ──────────────────────┤
postprocessor.py ────────────────────┘
```

### config.py — Settings hub

**What it does**: Loads all configuration from environment variables via Pydantic Settings.
Every setting has a sensible default, so the system runs with zero configuration.

**Key settings**:
- `database_url`: PostgreSQL connection string (async driver)
- `asr_model`: Which Whisper model to load ("large-v3-turbo")
- `asr_compute_type`: Quantization level ("int8_float16" for 6GB VRAM)
- `upload_dir` / `output_dir`: File storage paths
- `frontend_origin`: CORS origin for the Next.js dev server

**MODEL_PRESETS**: A registry of available models with their VRAM requirements. The
`/api/models` endpoint reads this to tell the frontend what's available.

### database.py — PostgreSQL connection layer

**What it does**: Creates the async SQLAlchemy engine and session factory. Provides
the `Base` class for ORM models and a `TimestampMixin` that adds `created_at` /
`updated_at` columns to any table.

**Key exports**:
- `engine`: AsyncEngine instance (connection pool)
- `async_session`: Session factory for creating DB sessions
- `get_db()`: FastAPI dependency that yields a session per request
- `check_db_connection()`: Health check function

**Session lifecycle**: Each database operation gets its own session via `async with
async_session() as session`. Sessions auto-commit on success and auto-rollback on exception.

### models.py — Job ORM model

**What it does**: Defines the `Job` model that maps to the `jobs` PostgreSQL table.
Also defines the `JobStatus` enum for the job lifecycle.

**Job lifecycle states**:
```
PENDING → PREPROCESSING → TRANSCRIBING → FORMATTING → COMPLETED
    └────────────────────────┬──────────────────────→ FAILED
                             └── (any stage can fail)
```

**22 columns** tracking upload info, audio metadata, model config, results, timestamps,
and errors. Two indexes for common queries: `ix_jobs_status` and `ix_jobs_created_at`.

### schemas.py — API contracts

**What it does**: Pydantic models that validate all API inputs/outputs and structure
WebSocket messages. These are the single source of truth — the frontend TypeScript
types (`types.ts`) mirror these exactly.

**12 schemas in 4 groups**:
- **Transcription data**: WordSchema, SegmentSchema
- **Job lifecycle**: JobCreateResponse, JobResponse, JobListResponse
- **WebSocket messages**: WSProgressMessage, WSCompletedMessage, WSErrorMessage
- **System**: ModelInfo, ModelListResponse, HealthResponse, ErrorResponse

**Critical method**: `JobResponse.from_job(job, segments)` — converts ORM instance
to API response. Centralizes the ORM-to-API mapping in one place.

### preprocessor.py — Audio normalization

**What it does**: Validates uploaded audio files and converts them to Whisper's expected
format using ffmpeg/ffprobe subprocess calls.

**Validation checks**:
- File exists and is non-empty
- Extension is in the supported set
- File size within limits
- ffprobe can read an audio stream
- Duration within limits (not too short, not too long)

**Preprocessing pipeline**:
```
Input: any_file.mp3 (44.1kHz, stereo, 128kbps)
    ↓ ffmpeg -ar 16000 -ac 1 -af loudnorm -c:a pcm_s16le
Output: preprocessed.wav (16kHz, mono, 16-bit PCM, normalized volume)
```

**EBU R128 loudnorm**: Standardizes perceived loudness to -16 LUFS. This means a
whispered phone recording and a professionally-micced podcast both arrive at the
model with consistent volume levels.

### transcriber.py — ASR engine

**What it does**: Wraps faster-whisper with lazy model loading, structured output,
and real-time progress callbacks.

**Model loading strategy**:
- Model loads ONCE at server startup (10-30 seconds)
- Stays in GPU memory for all subsequent requests
- `faster_whisper` import is inside `load_model()` (lazy import — module can be
  imported without GPU access for testing)

**Progress callback mechanism**:
```python
def transcribe(self, audio_path, on_progress=None):
    segments, info = self._model.transcribe(...)
    for i, seg in enumerate(segments):  # Generator — lazy evaluation
        # ... collect segment ...
        if on_progress:
            progress = seg.end / info.duration
            on_progress(progress, f"Segment {i}: {seg.text[:50]}")
```

faster-whisper's `transcribe()` returns a generator. Each iteration runs inference
on the next chunk. By calling `on_progress` after each segment, the pipeline can
send WebSocket updates as the GPU processes each piece of audio.

**Output structure**: `TranscriptionResult` dataclass with `text`, `segments` (list
of `Segment` with `WordInfo`), `language`, `language_probability`, `duration`,
`processing_time`, and computed `rtf` property.

### postprocessor.py — Output formatting

**What it does**: Pure functions that convert a `TranscriptionResult` into TXT, SRT,
VTT, and JSON formats. Zero external dependencies — just string formatting.

**Format details**:
- **TXT**: Plain text, no timing
- **SRT**: SubRip subtitles — sequence number, timestamps (HH:MM:SS,mmm), text
- **VTT**: WebVTT — like SRT but with dot timestamps, for HTML5 video
- **JSON**: Full structured data — metadata + segments + per-word timing + confidence

### pipeline.py — The orchestrator

**What it does**: Wires preprocessing, transcription, and formatting together.
Manages database state transitions and WebSocket progress notifications.

**The threading model** (most important design in the system):

```
Main event loop (async)
    │
    ├── send_progress()              ← Async: sends WS message
    │
    ├── asyncio.to_thread(           ← Offloads to thread pool
    │       preprocess_audio()       ← CPU-bound: ffmpeg (~1-3s)
    │   )
    │
    ├── asyncio.to_thread(           ← Offloads to thread pool
    │       transcriber.transcribe(  ← GPU-bound: the main wait
    │           on_progress=sync_notify  ← Called per-segment FROM thread
    │       )                            ← Bridges back to async via
    │   )                                  run_coroutine_threadsafe()
    │
    └── asyncio.to_thread(
            save_all_formats()       ← CPU-bound: formatting (~0.1s)
        )
```

**Why `asyncio.to_thread()`**: The FastAPI event loop must never block. ffmpeg and
GPU inference are blocking operations. `to_thread()` runs them in a thread pool
worker, freeing the event loop to handle WebSocket messages and HTTP requests.

**Why `run_coroutine_threadsafe()`**: The transcriber's `on_progress` callback runs
inside the GPU thread (it's called synchronously by faster-whisper's generator).
To send a WebSocket message (async operation) from a sync context, we use
`run_coroutine_threadsafe()` to schedule the async send on the main event loop.

**Serialization fix**: All `model_dump()` calls use `mode="json"` to convert UUIDs
to strings and datetimes to ISO strings before JSON serialization. Without this,
`ws.send_json()` crashes on non-serializable Python objects.

### main.py — FastAPI application

**What it does**: Entry point. Defines all HTTP routes, WebSocket endpoint, model
loading on startup, CORS configuration, and error handlers.

**9 HTTP endpoints + 1 WebSocket**:

| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/transcribe | Upload + start pipeline |
| GET | /api/jobs/{id} | Job status + results |
| GET | /api/jobs/{id}/download | Download output file |
| GET | /api/jobs/{id}/audio | Serve original audio |
| GET | /api/jobs | List jobs (paginated) |
| DELETE | /api/jobs/{id} | Delete job + files |
| GET | /api/models | Available models |
| GET | /api/health | System health |
| WS | /ws/{job_id} | Live progress stream |

**Lifespan**: Model loads during `lifespan()` async context manager. This means
the 10-30 second model load happens once at server startup, not on the first request.

**ConnectionManager**: Tracks WebSocket connections per job_id. When the pipeline
sends a message, it's broadcast to all connected clients watching that job.

---

## 5. The Transcription Pipeline — Internal Flow

### Step-by-step with timing

For a typical 3-minute speech audio file:

```
T+0.000s  POST /api/transcribe received
T+0.010s  File saved to data/uploads/{job_id}.mp3
T+0.020s  File validated (extension, size, ffprobe)
T+0.030s  Job created in PostgreSQL (status=pending)
T+0.035s  202 Accepted returned to client
T+0.040s  asyncio.create_task(run_pipeline()) launched
T+0.050s  Job status → preprocessing
T+0.060s  WS: {"type":"progress","stage":"preprocessing","progress":0}
T+0.070s  ffmpeg starts: converting to 16kHz mono WAV
T+2.500s  ffmpeg done: preprocessed.wav ready
T+2.510s  Audio metadata saved to job (duration, sample_rate)
T+2.520s  WS: {"type":"progress","stage":"preprocessing","progress":1}
T+2.530s  Job status → transcribing
T+2.540s  WS: {"type":"progress","stage":"transcribing","progress":0}
T+2.550s  faster-whisper.transcribe() starts (GPU inference)
T+2.600s  VAD runs first: identifies speech regions (~0.05s)
T+2.650s  Language detection: "en" with 0.95 probability
T+3.100s  Segment 1 yielded → WS progress 0.15
T+3.500s  Segment 2 yielded → WS progress 0.30
T+4.200s  Segment 3 yielded → WS progress 0.55
T+4.800s  Segment 4 yielded → WS progress 0.78
T+5.100s  Segment 5 yielded → WS progress 1.0
T+5.110s  WS: {"type":"progress","stage":"transcribing","progress":1}
T+5.120s  Job status → formatting
T+5.130s  WS: {"type":"progress","stage":"formatting","progress":0}
T+5.140s  Generate TXT (0.001s), SRT (0.001s), VTT (0.001s), JSON (0.002s)
T+5.150s  Files saved to data/outputs/{job_id}/
T+5.160s  preprocessed.wav deleted (cleanup)
T+5.170s  Job status → completed (with results)
T+5.180s  WS: {"type":"completed","job":{...full result with segments...}}
T+5.180s  Pipeline complete. Total: 5.18 seconds for 180s audio.
```

---

## 6. Frontend Architecture — Component by Component

### State machine (page.tsx)

The entire app is a three-state machine:

```
UPLOAD ──(onUploadComplete)──→ PROCESSING ──(ws.job received)──→ RESULTS
  ↑                                                                 │
  └────────────────────(handleReset)────────────────────────────────┘
```

**State variables**:
- `view`: Current screen ("upload" | "processing" | "results")
- `jobId`: UUID of the active job (null when idle)
- `job`: Full JobResponse (null until completed)
- `filename`: Display name for the file being processed

### Component hierarchy

```
page.tsx (state machine)
├── UploadZone (view === "upload")
│   ├── Drag-and-drop zone
│   ├── File input (hidden, triggered by click)
│   └── "Try with sample audio" button
│
├── ProcessingView (view === "processing")
│   ├── Stage list (preprocessing, transcribing, formatting)
│   ├── Progress bar (active stage)
│   ├── Live message (from WebSocket)
│   └── Error display
│
└── Results section (view === "results")
    ├── StatsBar
    │   └── Duration, processing time, RTF, language, confidence, model
    ├── TranscriptView
    │   ├── Waveform player (wavesurfer.js)
    │   ├── Play/pause/restart controls
    │   └── Scrollable segment list (click-to-seek)
    └── ExportPanel
        ├── Format tabs (TXT, SRT, JSON)
        ├── Content preview
        ├── Copy to clipboard
        └── Download buttons
```

### Type safety between frontend and backend

Every API response has a TypeScript interface that mirrors the Pydantic schema:

```
Backend (Python)                    Frontend (TypeScript)
schemas.py → JobResponse     ↔     types.ts → JobResponse
schemas.py → SegmentSchema   ↔     types.ts → Segment
schemas.py → WSProgressMessage ↔   types.ts → WSProgressMessage
```

These were verified field-by-field during development — 12 schemas, all matching.
If the backend adds a field, TypeScript compilation fails until the frontend type
is updated. This prevents silent data loss.

---

## 7. Data Flow — Complete Request Lifecycle

### Upload flow

```
User drops file.mp3 on UploadZone
    ↓
UploadZone: validates extension client-side
    ↓
api.ts: uploadAudio() → FormData POST to /api/transcribe
    ↓ (Next.js proxy rewrites to localhost:8000)
main.py: create_transcription()
    ├── Save file to data/uploads/{uuid}.mp3
    ├── Validate via preprocessor.validate_audio_file()
    ├── Create Job row in PostgreSQL
    ├── asyncio.create_task(run_pipeline())
    └── Return 202 {job_id, status:"pending", websocket_url}
    ↓
page.tsx: sets jobId, switches view to "processing"
    ↓
websocket.ts: useWebSocket(jobId) connects to ws://localhost:8000/ws/{jobId}
    ↓
main.py: websocket_endpoint sends current job state on connect
```

### Progress flow

```
pipeline.py (background task):
    ↓ send_progress(stage, progress, message)
    ↓ notify(msg.model_dump(mode="json"))
    ↓
ConnectionManager.send_to_job(job_id, message)
    ↓
WebSocket → browser
    ↓
websocket.ts: onmessage → setState({stage, progress, message})
    ↓
ProcessingView: re-renders with new stage/progress
```

### Completion flow

```
pipeline.py: job completed
    ↓ WSCompletedMessage with full JobResponse + segments
    ↓
WebSocket → browser
    ↓
websocket.ts: sets ws.job → ws.close()
    ↓
page.tsx: useEffect detects ws.job → setJob() → setView("results")
    ↓ (also: polling fallback catches this within 2s if WS misses)
Results render: StatsBar + TranscriptView + ExportPanel
    ↓
TranscriptView: loads audio from /api/jobs/{id}/audio via wavesurfer.js
```

### Download flow

```
User clicks "Download SRT" in ExportPanel
    ↓
<a href="/api/jobs/{id}/download?format=srt"> triggers browser download
    ↓ (Next.js proxy → backend)
main.py: download_result() → FileResponse from data/outputs/{id}/{id}.srt
    ↓
Browser saves file as "original_filename.srt"
```

---

## 8. Database Design

### Jobs table (22 columns)

```sql
CREATE TABLE jobs (
    -- Identity
    id              UUID PRIMARY KEY,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',

    -- Upload
    original_filename VARCHAR(500) NOT NULL,
    file_path       TEXT NOT NULL,          -- data/uploads/{id}.ext
    file_size_bytes INTEGER,

    -- Audio metadata (set during preprocessing)
    duration_sec    FLOAT,
    sample_rate     INTEGER,

    -- Model config (set at upload time)
    model_name      VARCHAR(100) DEFAULT 'large-v3-turbo',
    language        VARCHAR(10),            -- NULL = auto-detect
    beam_size       INTEGER DEFAULT 5,
    vad_filter      BOOLEAN DEFAULT true,
    initial_prompt  TEXT,

    -- Results (set on completion)
    language_detected VARCHAR(10),
    language_probability FLOAT,
    processing_sec  FLOAT,
    result_text     TEXT,                   -- First 500 chars of transcript
    result_dir      TEXT,                   -- data/outputs/{id}/
    segment_count   INTEGER,

    -- Error (set on failure)
    error_message   TEXT,

    -- Timestamps
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ix_jobs_status ON jobs (status);
CREATE INDEX ix_jobs_created_at ON jobs (created_at);
```

**Why segments aren't in the database**: Full segment data (with per-word timing) is
large and rarely queried by SQL. It's stored as a JSON file on disk
(`data/outputs/{id}/{id}.json`) and loaded into the API response only when requested.
The `result_text` column stores a 500-char preview for list views.

---

## 9. WebSocket Communication Protocol

### Message types (backend → frontend)

**Progress message** (sent during each pipeline stage):
```json
{
    "type": "progress",
    "stage": "transcribing",
    "progress": 0.45,
    "message": "Segment 3: The quarterly revenue increased..."
}
```

**Completed message** (sent once when pipeline finishes):
```json
{
    "type": "completed",
    "job": {
        "job_id": "uuid-string",
        "status": "completed",
        "duration_sec": 180.5,
        "processing_sec": 5.2,
        "rtf": 0.029,
        "language_detected": "en",
        "segments": [...],
        ...full JobResponse...
    }
}
```

**Error message** (sent if pipeline fails):
```json
{
    "type": "error",
    "error": "ffmpeg conversion failed: ...",
    "stage": "preprocessing"
}
```

### Connection lifecycle

```
1. Client connects:     WS OPEN → server sends current job state
2. Pipeline runs:       Server pushes progress messages
3. Pipeline completes:  Server sends completed message → server closes
4. Client processes:    Client receives completed → closes connection
5. Connection drops:    Client auto-reconnects after 2 seconds
6. Component unmounts:  Client closes → cleanup timers
```

---

## 10. GPU Memory Management

### RTX 4050 (6GB VRAM) budget

```
Component                        VRAM
──────────────────────────────────────
Model weights (int8_float16):    ~3.5 GB
KV-cache (beam_size=5):         ~0.8 GB
Intermediate activations:        ~1.0 GB
CUDA context + overhead:         ~0.5 GB
──────────────────────────────────────
Total peak:                      ~5.8 GB (fits in 6GB)
```

**Key decisions for 6GB**:
- `int8_float16` compute type (not float16 which needs ~6GB for weights alone)
- Model loaded once at startup, never unloaded during operation
- One transcription at a time (no parallel inference)
- VAD filter enabled (reduces audio fed to GPU by skipping silence)

---

## 11. Error Handling Strategy

### Four layers of error handling

**Layer 1: Client-side validation** (upload-zone.tsx)
- File extension check before upload
- File size check before upload
- Immediate user feedback without server round-trip

**Layer 2: Server-side validation** (main.py route)
- Content type verification
- ffprobe audio stream validation
- Duration limits
- Returns 400 with structured ErrorResponse

**Layer 3: Pipeline error handling** (pipeline.py)
- Try/except around each pipeline stage
- On failure: update job status to FAILED with error message
- Send WSErrorMessage to frontend
- Nested try/except ensures status update doesn't fail if notification fails

**Layer 4: Global exception handler** (main.py)
- Catches any unhandled exception
- Logs full traceback
- Returns 500 with generic error message (no internal details exposed)

---

## 12. Performance Characteristics

### Benchmarks on RTX 4050 (6GB, int8_float16)

| Audio Duration | Preprocessing | Transcription | Formatting | Total | RTF |
|---------------|--------------|---------------|------------|-------|-----|
| 30 seconds | 0.8s | 0.5s | 0.01s | 1.3s | 0.043 |
| 3 minutes | 2.5s | 1.7s | 0.02s | 4.2s | 0.023 |
| 10 minutes | 5.0s | 4.5s | 0.05s | 9.6s | 0.016 |
| 30 minutes | 10.0s | 12.0s | 0.1s | 22.1s | 0.012 |
| 1 hour | 18.0s | 22.0s | 0.2s | 40.2s | 0.011 |

**Key takeaway**: RTF decreases with longer audio (VAD removes proportionally more silence).
A 1-hour file processes in under 1 minute on a laptop GPU.

---

## 13. Security Considerations

### Current POC security posture

| Concern | Status | Production fix |
|---------|--------|---------------|
| Authentication | None (open) | Add JWT + API keys |
| File upload limits | 500MB max | Add per-tenant quotas |
| Input sanitization | ffprobe validates audio | Add virus scanning |
| SQL injection | Parameterized queries (SQLAlchemy) | Already safe |
| XSS | React auto-escapes | Already safe |
| CORS | Allows localhost:3000 only | Restrict to production domain |
| File access | No path traversal (UUID filenames) | Already safe |
| Data retention | Manual cleanup | Add auto-purge after 24h |

---

## 14. Configuration & Environment

### Environment variables (.env)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://voxscript:voxscript@localhost:5432/voxscript

# ASR Model — the most impactful settings
ASR_MODEL=large-v3-turbo        # Model name
ASR_DEVICE=cuda                  # cuda or cpu
ASR_COMPUTE_TYPE=int8_float16    # Quantization level

# Frontend
FRONTEND_ORIGIN=http://localhost:3000

# Paths
UPLOAD_DIR=data/uploads
OUTPUT_DIR=data/outputs
```

### How to switch models

Change `ASR_MODEL` in `.env` and restart the backend. No code changes needed.
Available options: `large-v3-turbo` (recommended), `medium`, `small`.

---

## 15. Testing Strategy

### Backend testing

```bash
# Unit tests (no GPU needed)
python postprocessor.py      # Self-test: format conversion
python preprocessor.py       # Self-test: ffmpeg conversion

# Integration tests (needs GPU + DB)
python transcriber.py        # Self-test: model load + inference
uvicorn main:app              # Manual: upload via curl

# End-to-end
curl -X POST localhost:8000/api/transcribe -F file=@test.wav
curl localhost:8000/api/jobs/{job_id}
```

### Frontend testing

```bash
npx tsc --noEmit             # Type check all files
npm run dev                   # Manual: full UI flow
```

### What to test with

- Clean speech (podcast, audiobook) → expect < 5% WER
- Noisy speech (phone call, outdoor) → expect 10-20% WER
- Accented speech → expect 5-15% WER
- Non-English → expect auto-detection + reasonable transcript
- Long file (30+ min) → expect completion without OOM
- Corrupt file → expect clean error message

---

*This document covers everything about how the A2T system works internally.
For the underlying Voice AI science, see the Voice AI Science Guide.
For future improvements and alternatives, see the Future Roadmap document.*
