# AIIT — AI-Powered Audio Transcription

> Self-hosted audio-to-text transcription with real-time progress, word-level timestamps, confidence scores, and multi-format export — powered by OpenAI's Whisper large-v3-turbo running on your local GPU.

---

## What is AIIT?

VoxScript is an open-source transcription platform that runs entirely on your machine. Upload any audio file through the web interface, watch it process in real-time via WebSocket, and get accurate timestamped transcriptions you can download as TXT, SRT, VTT, or JSON.

**Your audio never leaves your machine.** There are no API keys, no per-minute charges, and no cloud dependencies.

### Key Features

- **High accuracy** — Uses Whisper large-v3-turbo (809M parameters, trained on 680K hours)
- **Faster than real-time** — RTF ~0.01-0.04 on consumer GPUs (a 10-minute file processes in ~10 seconds)
- **Word-level timestamps** — Every word has a start time, end time, and confidence score
- **Live progress** — WebSocket-powered real-time updates as each segment is transcribed
- **Click-to-seek** — Click any transcript segment and the audio jumps to that moment
- **Multi-format export** — TXT, SRT (subtitles), VTT (web subtitles), JSON (structured data)
- **96+ languages** — Auto-detects language or can be set manually
- **Job history** — Browse and re-download all past transcriptions
- **Playback speed** — 0.5x to 2x playback with keyboard shortcuts

### Demo

```
Upload audio → Real-time progress → Results with audio player + transcript + export
```

The system processes a 3-minute speech recording in approximately 4-5 seconds on an NVIDIA RTX 4050 (6GB VRAM).

System frontend:

- [Image](img/1.png)
- [Image](img/2.png)
- [Image](img/3.png)
- [Image](img/4.png)

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [System Requirements](#system-requirements)
3. [Installation — Windows](#installation--windows)
4. [Installation — macOS](#installation--macos)
5. [Database Setup](#database-setup)
6. [Backend Setup](#backend-setup)
7. [Frontend Setup](#frontend-setup)
8. [Running the Application](#running-the-application)
9. [Verifying the Installation](#verifying-the-installation)
10. [Configuration Reference](#configuration-reference)
11. [Usage Guide](#usage-guide)
12. [API Reference](#api-reference)
13. [Supported Audio Formats](#supported-audio-formats)
14. [Troubleshooting](#troubleshooting)
15. [Project Structure](#project-structure)
16. [Tech Stack](#tech-stack)
17. [License](#license)

---

## Prerequisites

You need the following installed on your system before starting:

| Prerequisite | Required Version | What it does |
|-------------|-----------------|-------------|
| Python | 3.12+ | Backend runtime |
| Node.js | 18+ (recommend 22 LTS) | Frontend runtime |
| PostgreSQL | 15+ | Job database |
| ffmpeg + ffprobe | 6+ | Audio format conversion |
| NVIDIA GPU + CUDA | CUDA 12.x (optional but strongly recommended) | GPU-accelerated inference |
| Git | Any recent version | Clone the repository |

> **No NVIDIA GPU?** The system works on CPU too — set `ASR_DEVICE=cpu` in your `.env` file. Processing will be 5-10x slower but functionally identical.

---

## System Requirements

### Minimum (CPU-only)

- **CPU**: Any modern x86_64 processor (Intel/AMD)
- **RAM**: 8 GB
- **Storage**: 5 GB free (for model weights + audio files)
- **GPU**: Not required (set `ASR_DEVICE=cpu`)

### Recommended (GPU-accelerated)

- **CPU**: Intel i5 / AMD Ryzen 5 or better
- **RAM**: 16 GB
- **GPU**: NVIDIA GPU with 6+ GB VRAM (RTX 3060, RTX 4050, RTX 4060, etc.)
- **CUDA**: 12.x with cuDNN
- **Storage**: 10 GB free

### VRAM Requirements by Model

| Model | VRAM (int8_float16) | VRAM (float16) | Accuracy |
|-------|-------------------|----------------|----------|
| large-v3-turbo (default) | ~3.5 GB | ~6 GB | Best (recommended) |
| medium | ~2.5 GB | ~5 GB | Good |
| small | ~1.5 GB | ~2 GB | Moderate |

---

## Installation — Windows

### Step 1: Install Python 3.12+

1. Download Python from [python.org/downloads](https://www.python.org/downloads/)
2. **Important**: Check "Add Python to PATH" during installation
3. Verify installation:
   ```powershell
   python --version
   # Expected: Python 3.12.x or higher
   ```

### Step 2: Install Node.js

1. Download Node.js LTS from [nodejs.org](https://nodejs.org/)
2. Run the installer with default settings
3. Verify installation:
   ```powershell
   node --version
   # Expected: v18.x or higher (recommend v22.x)
   
   npm --version
   # Expected: 10.x or higher
   ```

### Step 3: Install PostgreSQL

1. Download PostgreSQL from [postgresql.org/download/windows](https://www.postgresql.org/download/windows/)
2. Run the installer:
   - Choose components: PostgreSQL Server, pgAdmin 4, Command Line Tools
   - Set the superuser password (remember this — you'll need it)
   - Default port: **5432** (keep this)
   - Default locale: your system locale is fine
3. After installation, add PostgreSQL to your PATH:
   - Open System Properties → Environment Variables → System Variables → Path → Edit
   - Add: `C:\Program Files\PostgreSQL\16\bin` (adjust version number if different)
4. Verify:
   ```powershell
   psql --version
   # Expected: psql (PostgreSQL) 16.x
   ```

### Step 4: Install ffmpeg

ffmpeg is required for audio format conversion (MP3 → WAV, resampling, loudness normalization).

**Option A: Manual installation (recommended)**

1. Download ffmpeg from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/)
   - Download the **ffmpeg-release-essentials.zip** file (not the git or shared builds)
2. Extract the ZIP file to a permanent location:
   - Recommended: `C:\ffmpeg\`
   - The extracted folder should contain `bin\ffmpeg.exe` and `bin\ffprobe.exe`
3. Add ffmpeg to your PATH:
   - Open System Properties → Environment Variables → System Variables → Path → Edit
   - Add: `C:\ffmpeg\bin` (or wherever you extracted the `bin` folder)
4. **Restart your terminal** (close and reopen PowerShell/Command Prompt)
5. Verify:
   ```powershell
   ffmpeg -version
   # Expected: ffmpeg version 7.x or 8.x ...
   
   ffprobe -version
   # Expected: ffprobe version 7.x or 8.x ...
   ```

**Option B: Install via winget**

```powershell
winget install Gyan.FFmpeg
```

Then restart your terminal and verify with `ffmpeg -version`.

**Option C: Install via Chocolatey**

```powershell
choco install ffmpeg
```

> **YouTube installation guide**: <!-- Add your YouTube link here -->

### Step 5: Install NVIDIA CUDA (GPU users only)

Skip this step if you're running CPU-only.

1. Check your GPU: Open Task Manager → Performance → GPU. Note the GPU name.
2. Install the latest NVIDIA driver from [nvidia.com/drivers](https://www.nvidia.com/Download/index.aspx)
3. Install CUDA Toolkit 12.x from [developer.nvidia.com/cuda-downloads](https://developer.nvidia.com/cuda-downloads)
   - Select: Windows → x86_64 → Your Windows version → exe (local)
   - Run the installer with default settings
4. Verify:
   ```powershell
   nvidia-smi
   # Should show your GPU name, CUDA version, and VRAM
   
   nvcc --version
   # Expected: Cuda compilation tools, release 12.x
   ```

### Step 6: Install PyTorch with CUDA

```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

Verify GPU is detected:
```powershell
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}, GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')"
# Expected: CUDA: True, GPU: NVIDIA GeForce RTX 4050 (or your GPU name)
```

> **CPU-only users**: Install the CPU version instead:
> ```powershell
> pip install torch torchvision torchaudio
> ```

---

## Installation — macOS

### Step 1: Install Homebrew (if not already installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Step 2: Install Python 3.12+

```bash
brew install python@3.12
```

Verify:
```bash
python3 --version
# Expected: Python 3.12.x or higher
```

### Step 3: Install Node.js

```bash
brew install node
```

Verify:
```bash
node --version && npm --version
```

### Step 4: Install PostgreSQL

```bash
brew install postgresql@16
brew services start postgresql@16
```

Verify:
```bash
psql --version
```

### Step 5: Install ffmpeg

```bash
brew install ffmpeg
```

Verify:
```bash
ffmpeg -version
ffprobe -version
```

### Step 6: Install PyTorch

macOS does not have CUDA. Use the CPU or MPS (Apple Silicon) version:

**Apple Silicon (M1/M2/M3/M4):**
```bash
pip3 install torch torchvision torchaudio
```

PyTorch on Apple Silicon uses the Metal Performance Shaders (MPS) backend. Set `ASR_DEVICE=cpu` in your `.env` (faster-whisper's CTranslate2 doesn't support MPS yet, so it falls back to CPU with ARM NEON acceleration).

**Intel Mac:**
```bash
pip3 install torch torchvision torchaudio
```

Set `ASR_DEVICE=cpu` and `ASR_COMPUTE_TYPE=float32` in your `.env`.

---

## Database Setup

These steps are the same for both Windows and macOS.

### Create the database and user

**Windows** (open a new PowerShell as Administrator):
```powershell
# Connect to PostgreSQL as the superuser
psql -U postgres

# Inside the psql shell, run these commands:
CREATE USER voxscript WITH PASSWORD 'voxscript';
CREATE DATABASE voxscript OWNER voxscript;
GRANT ALL PRIVILEGES ON DATABASE voxscript TO voxscript;
\q
```

**macOS**:
```bash
# macOS PostgreSQL installs with your username as superuser
psql postgres

# Inside the psql shell:
CREATE USER voxscript WITH PASSWORD 'voxscript';
CREATE DATABASE voxscript OWNER voxscript;
GRANT ALL PRIVILEGES ON DATABASE voxscript TO voxscript;
\q
```

### Verify the connection

```bash
psql -U voxscript -d voxscript -c "SELECT 1;"
```

If this returns `1`, your database is ready.

> **Connection refused?** Make sure PostgreSQL is running:
> - Windows: Open Services (`services.msc`) → find `postgresql-x64-16` → Start
> - macOS: `brew services start postgresql@16`

---

## Backend Setup

### Step 1: Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/voxscript-poc.git
cd voxscript-poc
```

### Step 2: Create a Python virtual environment

**Windows:**
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
```

> If you get an "execution policy" error, run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

**macOS:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Python dependencies

```bash
pip install -e .
```

This reads `pyproject.toml` and installs all dependencies (FastAPI, faster-whisper, SQLAlchemy, etc.).

### Step 4: Create the .env file

Create a file called `.env` in the `backend/` directory:

**Windows (PowerShell):**
```powershell
@"
# Database
DATABASE_URL=postgresql+asyncpg://voxscript:voxscript@localhost:5432/voxscript
DATABASE_URL_SYNC=postgresql://voxscript:voxscript@localhost:5432/voxscript

# ASR Model
ASR_MODEL=large-v3-turbo
ASR_DEVICE=cuda
ASR_COMPUTE_TYPE=int8_float16

# Frontend
FRONTEND_ORIGIN=http://localhost:3000
"@ | Out-File -FilePath .env -Encoding utf8
```

**macOS:**
```bash
cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql+asyncpg://voxscript:voxscript@localhost:5432/voxscript
DATABASE_URL_SYNC=postgresql://voxscript:voxscript@localhost:5432/voxscript

# ASR Model
ASR_MODEL=large-v3-turbo
ASR_DEVICE=cpu
ASR_COMPUTE_TYPE=float32

# Frontend
FRONTEND_ORIGIN=http://localhost:3000
EOF
```

> **CPU-only users** (no NVIDIA GPU): Set `ASR_DEVICE=cpu` and `ASR_COMPUTE_TYPE=float32`

### Step 5: Run database migrations

```bash
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 001, create jobs table
```

Verify the table was created:
```bash
psql -U voxscript -d voxscript -c "\dt"
```

You should see `jobs` and `alembic_version` tables.

### Step 6: Verify the backend setup

```bash
python verify_setup.py
```

This checks Python, PyTorch, CUDA, faster-whisper, FastAPI, ffmpeg, PostgreSQL, and optionally loads the ASR model. All checks should pass.

---

## Frontend Setup

### Step 1: Install dependencies

```bash
cd ../frontend
npm install
```

```bash
In case after starting frontend server and system starts compiling, 
it will be classic node_modules corruption issue. This may cause your desktop to crash. 
Recommended stop the terminal immediately and perform the following fixes :

Windows :

cd path\voxscript-poc-repo\frontend

# Delete the corrupted copies
Remove-Item -Recurse -Force node_modules -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .next -ErrorAction SilentlyContinue

# Fresh install (downloads correct binaries for this path)
npm install

# Now run
npm run dev

macOS:

cd ~/path-to/voxscript-poc-repo/frontend

# Delete the corrupted copies
rm -rf node_modules .next

# Fresh install
npm install

# Run
npm run dev

```

### Step 2: Verify the Next.js proxy config

Make sure `frontend/next.config.mjs` exists with this content:

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: "http://localhost:8000/api/:path*" },
      { source: "/ws/:path*", destination: "http://localhost:8000/ws/:path*" },
    ];
  },
};

export default nextConfig;
```

This proxies all `/api/*` and `/ws/*` requests from the frontend (port 3000) to the backend (port 8000).

### Step 3: Add a sample audio file (optional)

Place any short WAV or MP3 file as `frontend/public/sample.wav`. This enables the "Try with sample audio" button on the upload page. A 10-30 second speech recording works best.

---

## Running the Application

You need **two terminals** — one for the backend, one for the frontend.

### Terminal 1: Start the backend

```bash
cd backend

# Activate virtual environment
# Windows:
.venv\Scripts\Activate.ps1
# macOS:
source .venv/bin/activate

# Start the server
uvicorn main:app --reload --port 8000
```

The first startup takes **10-30 seconds** while the Whisper model loads into GPU memory. You'll see:
```
INFO main: Starting VoxScript POC...
INFO main: Loading ASR model: large-v3-turbo (int8_float16)
INFO transcriber: Model loaded in 12.3s
INFO main: Model loaded. Server ready.
INFO: Uvicorn running on http://0.0.0.0:8000
```

### Terminal 2: Start the frontend

```bash
cd frontend
npm run dev
```

You'll see:
```
▲ Next.js 14.x
- Local: http://localhost:3000
✓ Ready
```

### Open the application

Navigate to **http://localhost:3000** in your browser.

---

## Verifying the Installation

### Quick health check

Open a new terminal and run:

```bash
curl http://localhost:8000/api/health
```

Expected response:
```json
{
  "status": "healthy",
  "model_loaded": true,
  "model_name": "large-v3-turbo",
  "gpu_available": true,
  "gpu_name": "NVIDIA GeForce RTX 4050",
  "vram_total_gb": 6.0,
  "database_connected": true
}
```

### Full end-to-end test

1. Open http://localhost:3000
2. Upload a speech audio file (MP3, WAV, FLAC, M4A, etc.)
3. Watch the live progress: Preprocessing → Transcribing → Formatting
4. View the results: waveform player, timestamped segments, confidence dots
5. Click a segment — the audio jumps to that timestamp
6. Export as TXT, SRT, VTT, or JSON
7. Click "History" to see all past transcriptions

---

## Configuration Reference

All settings are in `backend/.env`. Every setting has a sensible default in `config.py`.

### Core settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://voxscript:voxscript@localhost:5432/voxscript` | Async PostgreSQL connection string |
| `DATABASE_URL_SYNC` | `postgresql://voxscript:voxscript@localhost:5432/voxscript` | Sync connection for Alembic migrations |
| `ASR_MODEL` | `large-v3-turbo` | Whisper model name. Options: `large-v3-turbo`, `medium`, `small` |
| `ASR_DEVICE` | `cuda` | Inference device. Options: `cuda` (NVIDIA GPU), `cpu` |
| `ASR_COMPUTE_TYPE` | `int8_float16` | Quantization. Options: `int8_float16` (lowest VRAM), `float16`, `float32` (CPU) |
| `FRONTEND_ORIGIN` | `http://localhost:3000` | CORS allowed origin |

### Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_FILE_SIZE_MB` | `500` | Maximum upload file size in MB |
| `MAX_AUDIO_DURATION_MINUTES` | `120` | Maximum audio duration in minutes |
| `DEFAULT_BEAM_SIZE` | `5` | Beam search width (higher = slower but slightly more accurate) |
| `DEFAULT_VAD_FILTER` | `True` | Skip silence regions (strongly recommended) |

### Model selection guide

| Model | Speed | Accuracy | VRAM (int8_float16) | Best for |
|-------|-------|----------|---------------------|----------|
| `large-v3-turbo` | Fast | Highest | ~3.5 GB | Default — best balance |
| `medium` | Faster | Good | ~2.5 GB | Lower VRAM GPUs |
| `small` | Fastest | Moderate | ~1.5 GB | Quick testing, low resources |

To switch models, change `ASR_MODEL` in `.env` and restart the backend.

---

## Usage Guide

### Uploading audio

- **Drag and drop**: Drag any audio file onto the upload zone
- **Click to browse**: Click the upload zone to open your file browser
- **Sample audio**: Click "Try with sample audio" to test with a bundled sample

### During processing

The system shows three stages with live progress:
1. **Preprocessing** — Converting audio to 16kHz mono WAV with volume normalization (~1-3 seconds)
2. **Transcribing** — Running Whisper AI inference on GPU (~1-20 seconds depending on audio length)
3. **Formatting** — Generating output files in all formats (~0.1 seconds)

### Viewing results

- **Audio player**: Waveform visualization with play/pause, restart, and speed control
- **Transcript**: Click any segment to seek the audio to that timestamp
- **Confidence dots**: Green (high), yellow (medium), red (low) confidence per segment
- **Keyboard shortcut**: Press Space to play/pause

### Exporting

Four output formats available:
- **TXT**: Plain text, no timestamps
- **SRT**: SubRip subtitles (compatible with VLC, YouTube, Premiere Pro)
- **VTT**: WebVTT subtitles (compatible with HTML5 video, web players)
- **JSON**: Structured data with word-level timestamps and confidence scores

### Job history

Click "History" in the header to see all past transcriptions. Click any completed job to reload its results and re-download exports.

---

## API Reference

The backend exposes a RESTful API. Full interactive docs available at `http://localhost:8000/docs` (Swagger UI).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/transcribe` | Upload audio file and start transcription |
| `GET` | `/api/jobs/{id}` | Get job status, results, and segments |
| `GET` | `/api/jobs/{id}/download?format=srt` | Download transcription in specified format |
| `GET` | `/api/jobs/{id}/audio` | Stream the original uploaded audio |
| `GET` | `/api/jobs` | List all jobs (paginated) |
| `DELETE` | `/api/jobs/{id}` | Delete a job and its files |
| `GET` | `/api/models` | List available ASR models |
| `GET` | `/api/health` | System health check |
| `WS` | `/ws/{job_id}` | WebSocket for live transcription progress |

### Example: Transcribe via curl

```bash
# Upload and start transcription
curl -X POST http://localhost:8000/api/transcribe \
  -F "file=@recording.mp3" \
  -F "model=large-v3-turbo"

# Response:
# {"job_id": "abc-123", "status": "pending", "websocket_url": "/ws/abc-123"}

# Check status (poll until completed)
curl http://localhost:8000/api/jobs/abc-123

# Download SRT subtitles
curl -O http://localhost:8000/api/jobs/abc-123/download?format=srt
```

---

## Supported Audio Formats

| Format | Extension | Notes |
|--------|-----------|-------|
| WAV | `.wav` | Uncompressed — best quality input |
| MP3 | `.mp3` | Most common, works well at 128kbps+ |
| FLAC | `.flac` | Lossless compression |
| M4A/AAC | `.m4a`, `.aac` | Apple/YouTube format |
| OGG/Opus | `.ogg`, `.opus` | Open-source formats |
| WebM | `.webm` | Browser recording format |
| WMA | `.wma` | Windows Media Audio |
| MP4 | `.mp4` | Video files — audio track is extracted |

All formats are converted to 16kHz mono 16-bit PCM WAV internally using ffmpeg before transcription.

---

## Troubleshooting

### Backend won't start

**"Model not loaded" error:**
The ASR model is still loading. Wait 10-30 seconds after starting the server (first run downloads the model which takes longer).

**"ffmpeg not found" error:**
ffmpeg is not on your system PATH. Verify with `ffmpeg -version`. If it fails, follow the ffmpeg installation steps above and restart your terminal.

**"relation 'jobs' does not exist" error:**
Database migrations haven't been run. Execute: `alembic upgrade head`

**"psycopg2" ModuleNotFoundError during alembic:**
Install the sync PostgreSQL driver: `pip install psycopg2-binary`

### Frontend issues

**Page loads but upload fails with network error:**
- Is the backend running on port 8000? Check with `curl http://localhost:8000/api/health`
- Does `next.config.mjs` have the API rewrite rules? See [Frontend Setup](#step-2-verify-the-nextjs-proxy-config)

**Stuck on "Formatting" stage:**
This was a serialization bug in earlier versions. Make sure `pipeline.py` uses `model_dump(mode="json")` on all three WebSocket message calls.

### GPU/CUDA issues

**"CUDA not available" in health check:**
- Verify NVIDIA driver: `nvidia-smi`
- Verify PyTorch CUDA: `python -c "import torch; print(torch.cuda.is_available())"`
- If False, reinstall PyTorch with CUDA: `pip install torch --index-url https://download.pytorch.org/whl/cu121`

**"CUDA out of memory" error:**
Your GPU doesn't have enough VRAM for the current model + compute type. Options:
1. Switch to a smaller model: `ASR_MODEL=medium` or `ASR_MODEL=small`
2. Use more aggressive quantization: `ASR_COMPUTE_TYPE=int8`
3. Close other GPU applications (games, other AI models)

### PostgreSQL issues

**"Connection refused" error:**
PostgreSQL is not running. Start it:
- Windows: Open Services → `postgresql-x64-16` → Start
- macOS: `brew services start postgresql@16`

**"Authentication failed" error:**
The user/password doesn't match. Recreate: `psql -U postgres -c "ALTER USER voxscript WITH PASSWORD 'voxscript';"`

---

## Project Structure

```
voxscript-poc/
├── backend/
│   ├── config.py                 # Settings loaded from .env
│   ├── database.py               # Async SQLAlchemy engine + session
│   ├── models.py                 # Job ORM model (22 columns)
│   ├── schemas.py                # Pydantic API schemas (12 models)
│   ├── preprocessor.py           # ffmpeg audio conversion + validation
│   ├── transcriber.py            # faster-whisper ASR engine wrapper
│   ├── postprocessor.py          # Output formatters (TXT, SRT, VTT, JSON)
│   ├── pipeline.py               # Pipeline orchestrator with WebSocket progress
│   ├── main.py                   # FastAPI app (9 routes + 1 WebSocket)
│   ├── verify_setup.py           # Environment verification script
│   ├── alembic.ini               # Alembic migration config
│   ├── pyproject.toml            # Python dependencies
│   ├── .env                      # Environment variables (not committed)
│   ├── migrations/
│   │   ├── env.py                # Alembic environment
│   │   └── versions/
│   │       └── 001_create_jobs.py
│   └── data/                     # Runtime data (not committed)
│       ├── uploads/              # Uploaded audio files
│       └── outputs/              # Transcription results
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx        # Root layout
│   │   │   ├── globals.css       # Global styles
│   │   │   └── page.tsx          # Main page (state machine)
│   │   ├── lib/
│   │   │   ├── types.ts          # TypeScript interfaces
│   │   │   ├── api.ts            # REST API client
│   │   │   ├── websocket.ts      # WebSocket hook
│   │   │   └── utils.ts          # Tailwind utilities
│   │   └── components/
│   │       ├── upload-zone.tsx    # Drag-and-drop upload
│   │       ├── processing-view.tsx # Live progress display
│   │       ├── transcript-view.tsx # Audio player + transcript
│   │       ├── stats-bar.tsx     # Metrics display
│   │       ├── export-panel.tsx  # Format tabs + download
│   │       ├── job-history.tsx   # Past transcriptions panel
│   │       └── ui/              # shadcn/ui components
│   ├── public/
│   │   └── sample.wav            # Sample audio for demo
│   ├── package.json
│   ├── next.config.mjs           # API proxy config
│   ├── tailwind.config.ts
│   └── tsconfig.json
│
├── .gitignore
└── README.md
```

---

## Tech Stack

### Backend

| Technology | Purpose | Why this choice |
|-----------|---------|----------------|
| **FastAPI** | Web framework | Async-native, WebSocket support, auto-generated API docs |
| **faster-whisper** | ASR engine | 4x faster than OpenAI whisper, 50% less VRAM via CTranslate2 |
| **PostgreSQL** | Database | Production-grade, UUID support, timezone-aware timestamps |
| **SQLAlchemy 2.0** | ORM | Async support, type-safe queries, migration support |
| **asyncpg** | DB driver | Fastest async PostgreSQL driver for Python |
| **Alembic** | Migrations | Standard SQLAlchemy migration tool |
| **ffmpeg** | Audio processing | Universal format conversion + EBU R128 loudness normalization |
| **Pydantic** | Validation | Request/response schema validation + serialization |
| **Uvicorn** | ASGI server | Production-grade async server |

### Frontend

| Technology | Purpose | Why this choice |
|-----------|---------|----------------|
| **Next.js** | Framework | Built-in API proxy, file routing, TypeScript support |
| **React 18** | UI library | Component model, hooks, ecosystem |
| **TypeScript** | Type safety | Catches backend/frontend schema mismatches at compile time |
| **Tailwind CSS** | Styling | Utility-first, consistent design, fast iteration |
| **shadcn/ui** | Components | Accessible, customizable, owned (not a dependency) |
| **wavesurfer.js** | Audio player | Waveform visualization, seek, playback speed control |
| **lucide-react** | Icons | Clean icon set, tree-shakeable |

---

## License

<!-- Add your license here. Common choices for open-source: MIT, Apache 2.0, GPL 3.0 -->

MIT License — see [LICENSE](LICENSE) for details.
