"""
VoxScript POC — Configuration
All settings loaded from environment variables or .env file.
"""

from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).parent


class Settings(BaseSettings):
    # App
    app_name: str = "voxscript-poc"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "postgresql+asyncpg://voxscript:voxscript@localhost:5432/voxscript"
    # Sync URL for Alembic migrations (asyncpg doesn't work with Alembic directly)
    database_url_sync: str = "postgresql://voxscript:voxscript@localhost:5432/voxscript"

    # ASR Model — adjust if your GPU can't handle the defaults
    asr_model: str = "large-v3-turbo"
    asr_device: str = "cuda"
    asr_compute_type: str = "int8_float16"  # Critical for 6GB VRAM

    # Transcription defaults
    default_beam_size: int = 5
    default_vad_filter: bool = True
    default_word_timestamps: bool = True

    # File paths
    upload_dir: Path = BASE_DIR / "data" / "uploads"
    output_dir: Path = BASE_DIR / "data" / "outputs"

    # Limits
    max_file_size_mb: int = 500
    max_audio_duration_minutes: int = 120

    # CORS
    frontend_origin: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


MODEL_PRESETS = {
    "large-v3-turbo": {
        "name": "large-v3-turbo",
        "compute_type": "int8_float16",
        "vram_gb": 3.5,
        "description": "Best accuracy (recommended)",
    },
    "medium": {
        "name": "medium",
        "compute_type": "int8_float16",
        "vram_gb": 2.5,
        "description": "Good accuracy, faster",
    },
    "small": {
        "name": "small",
        "compute_type": "float16",
        "vram_gb": 1.5,
        "description": "Fast, moderate accuracy",
    },
}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    return settings
