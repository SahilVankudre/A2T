"""
ASR engine — loads faster-whisper model, runs inference, returns structured results.

The model is loaded lazily on the first transcribe() call and stays in GPU
memory for all subsequent calls. On RTX 4050 (6GB VRAM) with int8_float16,
large-v3-turbo uses ~3.5GB leaving room for inference.

Depends on:  config.py (B01) — asr_model, asr_device, asr_compute_type
Depended by: pipeline.py (B08)
"""

import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from config import get_settings

logger = logging.getLogger(__name__)

# Type alias for progress callback: (progress: 0.0-1.0, message: str) -> None
ProgressCallback = Callable[[float, str], None]


# ── Data classes (match schemas.py WordSchema / SegmentSchema) ──

@dataclass
class WordInfo:
    """Single word with timing and confidence."""
    word: str
    start: float
    end: float
    probability: float


@dataclass
class Segment:
    """One transcription segment with optional word-level detail."""
    id: int
    start: float
    end: float
    text: str
    words: list[WordInfo] = field(default_factory=list)
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0


@dataclass
class TranscriptionResult:
    """Complete output of a transcription run."""
    text: str
    segments: list[Segment]
    language: str
    language_probability: float
    duration: float          # Audio duration in seconds
    processing_time: float   # Wall-clock inference time
    model_name: str

    @property
    def rtf(self) -> float:
        """Real-Time Factor: < 1 means faster than real-time."""
        return self.processing_time / self.duration if self.duration > 0 else 0.0


# ── Transcriber ─────────────────────────────────────────────

class Transcriber:
    """
    Wraps faster-whisper with lazy model loading and progress reporting.

    Usage:
        transcriber = Transcriber()
        transcriber.load_model()          # Explicit load (or auto-loads on first transcribe)
        result = transcriber.transcribe("audio.wav")
    """

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ):
        settings = get_settings()
        self.model_name = model_name or settings.asr_model
        self.device = device or settings.asr_device
        self.compute_type = compute_type or settings.asr_compute_type
        self._model = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load_model(self) -> float:
        """
        Load the Whisper model into GPU/CPU memory.
        Returns the time taken in seconds.
        Skips if already loaded.
        """
        if self._model is not None:
            logger.info("Model already loaded, skipping")
            return 0.0

        from faster_whisper import WhisperModel

        logger.info(
            "Loading ASR model: %s (device=%s, compute=%s)",
            self.model_name, self.device, self.compute_type,
        )
        start = time.perf_counter()

        self._model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
        )

        elapsed = time.perf_counter() - start
        logger.info("Model loaded in %.1fs", elapsed)
        return elapsed

    def unload_model(self) -> None:
        """Release the model from memory."""
        if self._model is not None:
            del self._model
            self._model = None
            # Clear CUDA cache if available
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
            logger.info("Model unloaded")

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        language: Optional[str] = None,
        beam_size: int = 5,
        vad_filter: bool = True,
        word_timestamps: bool = True,
        initial_prompt: Optional[str] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> TranscriptionResult:
        """
        Transcribe an audio file and return structured results.

        Args:
            audio_path:       Path to preprocessed 16kHz mono WAV.
            language:         Language code ("en", "es", etc.) or None for auto-detect.
            beam_size:        Beam width for decoding. 5 is the sweet spot.
            vad_filter:       Skip silent regions (strongly recommended).
            word_timestamps:  Enable per-word timing (needed for click-to-seek).
            initial_prompt:   Domain vocabulary hint for the decoder.
            on_progress:      Optional callback(progress: float, message: str)
                              called as each segment completes. progress is 0.0-1.0.

        Returns:
            TranscriptionResult with full text, segments, timing, and metadata.
        """
        if self._model is None:
            self.load_model()

        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        logger.info("Transcribing: %s", audio_path.name)
        start = time.perf_counter()

        # faster-whisper returns a generator + info object.
        # Segments are yielded lazily — inference runs as we iterate.
        raw_segments, info = self._model.transcribe(
            str(audio_path),
            language=language,
            beam_size=beam_size,
            vad_filter=vad_filter,
            vad_parameters={"min_silence_duration_ms": 500, "threshold": 0.5},
            word_timestamps=word_timestamps,
            initial_prompt=initial_prompt,
            condition_on_previous_text=True,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        )

        total_duration = info.duration

        # Consume the generator, collecting segments and reporting progress
        segments: list[Segment] = []
        text_parts: list[str] = []

        for i, seg in enumerate(raw_segments):
            words = [
                WordInfo(
                    word=w.word,
                    start=round(w.start, 3),
                    end=round(w.end, 3),
                    probability=round(w.probability, 4),
                )
                for w in (seg.words or [])
            ]

            segment = Segment(
                id=i,
                start=round(seg.start, 3),
                end=round(seg.end, 3),
                text=seg.text.strip(),
                words=words,
                avg_logprob=round(seg.avg_logprob, 4),
                no_speech_prob=round(seg.no_speech_prob, 4),
            )
            segments.append(segment)
            text_parts.append(seg.text.strip())

            # Report progress based on how far into the audio we've transcribed
            if on_progress and total_duration > 0:
                progress = min(seg.end / total_duration, 1.0)
                on_progress(progress, f"Segment {i + 1}: {seg.text.strip()[:50]}")

        processing_time = time.perf_counter() - start

        result = TranscriptionResult(
            text=" ".join(text_parts),
            segments=segments,
            language=info.language,
            language_probability=round(info.language_probability, 4),
            duration=round(total_duration, 2),
            processing_time=round(processing_time, 2),
            model_name=self.model_name,
        )

        logger.info(
            "Transcription complete: %.1fs audio in %.1fs (RTF=%.3f, lang=%s, segments=%d)",
            result.duration, result.processing_time,
            result.rtf, result.language, len(result.segments),
        )

        return result


# ── Self-test ───────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import tempfile
    import numpy as np

    print("=" * 50)
    print("  transcriber.py — self-test")
    print("=" * 50)

    # 1. Create transcriber
    transcriber = Transcriber()
    print(f"[OK] Transcriber created: model={transcriber.model_name}, "
          f"device={transcriber.device}, compute={transcriber.compute_type}")

    # 2. Load model
    print("[..] Loading model (10-30 seconds on first run)...")
    load_time = transcriber.load_model()
    print(f"[OK] Model loaded in {load_time:.1f}s")

    # Check GPU memory if available
    try:
        import torch
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            print(f"[OK] GPU memory: {allocated:.1f}GB allocated, {reserved:.1f}GB reserved")
    except ImportError:
        pass

    # 3. Generate a 5-second test audio (speech-like: mix of frequencies)
    print("[..] Generating test audio...")
    try:
        import soundfile as sf
    except ImportError:
        print("[FAIL] soundfile not installed: pip install soundfile")
        sys.exit(1)

    sr = 16000
    duration = 5.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Mix of frequencies that vaguely resemble speech formants
    audio = (
        0.3 * np.sin(2 * np.pi * 250 * t)
        + 0.2 * np.sin(2 * np.pi * 500 * t)
        + 0.1 * np.sin(2 * np.pi * 1000 * t)
    ).astype(np.float32)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        sf.write(tmp.name, audio, sr)
        tmp_path = Path(tmp.name)

    print(f"[OK] Test audio: {duration}s, {sr}Hz, mono")

    # 4. Transcribe with progress
    progress_calls = []

    def on_progress(p, msg):
        progress_calls.append(p)
        print(f"     Progress: {p:.0%} — {msg[:60]}")

    try:
        print("[..] Running transcription...")
        result = transcriber.transcribe(
            tmp_path,
            beam_size=1,  # Fast for testing
            vad_filter=True,
            on_progress=on_progress,
        )

        print(f"[OK] Language: {result.language} ({result.language_probability:.0%})")
        print(f"[OK] Duration: {result.duration:.1f}s")
        print(f"[OK] Processing: {result.processing_time:.1f}s")
        print(f"[OK] RTF: {result.rtf:.3f}")
        print(f"[OK] Segments: {len(result.segments)}")
        print(f"[OK] Text: '{result.text[:100]}{'...' if len(result.text) > 100 else ''}'")

        # Verify structure
        if result.segments:
            seg = result.segments[0]
            print(f"[OK] First segment: [{seg.start:.2f}s-{seg.end:.2f}s] "
                  f"logprob={seg.avg_logprob:.2f}, words={len(seg.words)}")

        print(f"[OK] Progress callbacks received: {len(progress_calls)}")

    finally:
        tmp_path.unlink(missing_ok=True)
        transcriber.unload_model()

    print(f"\n[OK] All transcriber tests passed!")