"""
Audio preprocessor — validation, metadata extraction, ffmpeg normalization.

Accepts any common audio format from the user, validates it, extracts
metadata via ffprobe, and converts to 16kHz mono WAV (what Whisper expects)
with EBU R128 volume normalization.

Depends on:  config.py (B01) — max_file_size_mb, max_audio_duration_minutes
Depended by: pipeline.py (B08)

System requirement: ffmpeg + ffprobe must be installed and on PATH.
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from config import get_settings

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".wav", ".mp3", ".flac", ".m4a", ".ogg",
    ".opus", ".wma", ".aac", ".webm", ".mp4",
}

TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1


@dataclass
class AudioInfo:
    """Metadata extracted from an audio file via ffprobe."""
    duration_sec: float
    sample_rate: int
    channels: int
    codec: str
    format_name: str
    file_size_bytes: int

    @property
    def needs_conversion(self) -> bool:
        """True if the file isn't already in Whisper-compatible format."""
        return (
            self.sample_rate != TARGET_SAMPLE_RATE
            or self.channels != TARGET_CHANNELS
            or self.codec not in ("pcm_s16le", "pcm_s16be")
        )


def check_ffmpeg() -> bool:
    """Verify ffmpeg and ffprobe are installed and reachable."""
    for cmd in ["ffmpeg", "ffprobe"]:
        try:
            subprocess.run(
                [cmd, "-version"],
                capture_output=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    return True


def get_audio_info(file_path: Path) -> AudioInfo:
    """
    Extract audio metadata using ffprobe.
    Raises RuntimeError if ffprobe fails or file has no audio stream.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "ffprobe not found. Install ffmpeg: https://www.gyan.dev/ffmpeg/builds/"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timed out reading {file_path.name}")

    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {file_path.name}: {result.stderr.strip()}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"ffprobe returned invalid JSON for {file_path.name}")

    # Find the first audio stream
    audio_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            audio_stream = stream
            break

    if audio_stream is None:
        raise RuntimeError(f"No audio stream found in {file_path.name}")

    fmt = data.get("format", {})

    # Duration: prefer format-level (more accurate), fall back to stream-level
    duration = float(fmt.get("duration", 0)) or float(audio_stream.get("duration", 0))
    if duration <= 0:
        raise RuntimeError(f"Could not determine duration of {file_path.name}")

    return AudioInfo(
        duration_sec=duration,
        sample_rate=int(audio_stream.get("sample_rate", 0)),
        channels=int(audio_stream.get("channels", 0)),
        codec=audio_stream.get("codec_name", "unknown"),
        format_name=fmt.get("format_name", "unknown"),
        file_size_bytes=file_path.stat().st_size,
    )


def validate_audio_file(file_path: Path) -> tuple[bool, str]:
    """
    Validate an audio file before processing.
    Returns (is_valid, message). Message is "OK" or a human-readable error.
    """
    settings = get_settings()

    if not file_path.exists():
        return False, f"File not found: {file_path}"

    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return False, (
            f"Unsupported format: {file_path.suffix}. "
            f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > settings.max_file_size_mb:
        return False, f"File too large: {size_mb:.0f}MB (max {settings.max_file_size_mb}MB)"

    if file_path.stat().st_size == 0:
        return False, "File is empty (0 bytes)"

    # Probe for audio stream and duration
    try:
        info = get_audio_info(file_path)
    except RuntimeError as e:
        return False, str(e)

    max_seconds = settings.max_audio_duration_minutes * 60
    if info.duration_sec > max_seconds:
        return False, (
            f"Audio too long: {info.duration_sec / 60:.0f} min "
            f"(max {settings.max_audio_duration_minutes} min)"
        )

    if info.duration_sec < 0.1:
        return False, "Audio too short (< 0.1 seconds)"

    return True, "OK"


def preprocess_audio(input_path: Path, output_path: Path) -> AudioInfo:
    """
    Convert audio to Whisper-compatible format:
    - Resample to 16kHz
    - Mix to mono
    - Normalize volume (EBU R128)
    - Output as 16-bit PCM WAV

    Returns AudioInfo of the converted file.
    Raises RuntimeError if ffmpeg conversion fails.
    """
    logger.info(f"Preprocessing: {input_path.name} → {output_path.name}")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-ar", str(TARGET_SAMPLE_RATE),
        "-ac", str(TARGET_CHANNELS),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:a", "pcm_s16le",
        "-y",  # Overwrite without asking
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg not found. Install ffmpeg: https://www.gyan.dev/ffmpeg/builds/"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffmpeg timed out processing {input_path.name}")

    if result.returncode != 0:
        # Extract the last meaningful error line from ffmpeg stderr
        err_lines = [l for l in result.stderr.strip().split("\n") if l.strip()]
        err_msg = err_lines[-1] if err_lines else "Unknown ffmpeg error"
        raise RuntimeError(f"ffmpeg conversion failed: {err_msg}")

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("ffmpeg produced empty output file")

    return get_audio_info(output_path)


# ── Self-test ──────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile
    import numpy as np

    print("=" * 50)
    print("  preprocessor.py — self-test")
    print("=" * 50)

    # 1. Check ffmpeg
    if check_ffmpeg():
        print("[OK] ffmpeg + ffprobe found")
    else:
        print("[FAIL] ffmpeg/ffprobe not found on PATH")
        exit(1)

    # 2. Create a test WAV file (3 seconds of a 440Hz sine wave)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        import soundfile as sf
        sr = 44100
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        # Write as stereo 44.1kHz to test conversion
        sf.write(str(tmp_path), np.column_stack([audio, audio]), sr)
        print(f"[OK] Test file created: {tmp_path.name} (stereo, 44100Hz, {duration}s)")
    except ImportError:
        print("[SKIP] soundfile not installed, skipping audio generation test")
        exit(0)

    # 3. Validate
    is_valid, msg = validate_audio_file(tmp_path)
    print(f"[OK] Validation: {msg}")

    # 4. Get info
    info = get_audio_info(tmp_path)
    print(f"[OK] Info: {info.duration_sec:.1f}s, {info.sample_rate}Hz, {info.channels}ch, {info.codec}")
    print(f"[OK] Needs conversion: {info.needs_conversion}")

    # 5. Preprocess
    out_path = tmp_path.with_name("test_preprocessed.wav")
    try:
        out_info = preprocess_audio(tmp_path, out_path)
        print(f"[OK] Preprocessed: {out_info.sample_rate}Hz, {out_info.channels}ch, {out_info.codec}")
        assert out_info.sample_rate == 16000, f"Expected 16000Hz, got {out_info.sample_rate}"
        assert out_info.channels == 1, f"Expected mono, got {out_info.channels}ch"
        print("[OK] Output is 16kHz mono — correct!")
    finally:
        tmp_path.unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)

    print("\n[OK] All preprocessor tests passed!")