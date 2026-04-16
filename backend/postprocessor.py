"""
Output formatter — converts TranscriptionResult into downloadable files.

Pure functions with zero external dependencies. Takes dataclasses from
transcriber.py as input, returns formatted strings or writes to disk.

Depends on:  nothing (uses transcriber.py types as input, but no import needed)
Depended by: pipeline.py (B08)
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Timestamp formatting ──────────────────────────────────

def _format_ts_srt(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    if ms >= 1000:  # Handle floating point rounding
        ms = 999
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def _format_ts_vtt(seconds: float) -> str:
    """Format seconds as VTT timestamp: HH:MM:SS.mmm"""
    if seconds < 0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    if ms >= 1000:
        ms = 999
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{ms:03d}"


# ── Format converters ─────────────────────────────────────

def to_txt(result: Any) -> str:
    """Plain text — just the words, no timing or metadata."""
    return result.text


def to_srt(result: Any) -> str:
    """
    SRT subtitle format (used by VLC, YouTube, most video tools).

    Format:
        1
        00:00:01,000 --> 00:00:04,500
        The quarterly revenue increased.

        2
        00:00:05,200 --> 00:00:08,100
        We expect continued growth.
    """
    lines = []
    for i, seg in enumerate(result.segments, 1):
        lines.append(str(i))
        lines.append(f"{_format_ts_srt(seg.start)} --> {_format_ts_srt(seg.end)}")
        lines.append(seg.text)
        lines.append("")  # Blank line separator
    return "\n".join(lines)


def to_vtt(result: Any) -> str:
    """
    WebVTT subtitle format (used in HTML5 <track> elements).
    Same as SRT but with dot timestamps and a header line.
    """
    lines = ["WEBVTT", ""]
    for i, seg in enumerate(result.segments, 1):
        lines.append(str(i))
        lines.append(f"{_format_ts_vtt(seg.start)} --> {_format_ts_vtt(seg.end)}")
        lines.append(seg.text)
        lines.append("")
    return "\n".join(lines)


def to_json(result: Any, include_words: bool = True) -> str:
    """
    Full structured JSON with metadata, segments, and word-level timing.
    This is the richest format — the frontend uses it for click-to-seek.
    """
    data = {
        "text": result.text,
        "language": result.language,
        "language_probability": result.language_probability,
        "duration": result.duration,
        "processing_time": result.processing_time,
        "rtf": round(result.rtf, 4),
        "model": result.model_name,
        "segments": [],
    }

    for seg in result.segments:
        seg_data = {
            "id": seg.id,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "avg_logprob": seg.avg_logprob,
            "no_speech_prob": seg.no_speech_prob,
        }
        if include_words and seg.words:
            seg_data["words"] = [
                {
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "probability": w.probability,
                }
                for w in seg.words
            ]
        data["segments"].append(seg_data)

    return json.dumps(data, indent=2, ensure_ascii=False)


# ── Formatter registry ────────────────────────────────────

FORMATTERS = {
    "txt": to_txt,
    "srt": to_srt,
    "vtt": to_vtt,
    "json": to_json,
}

SUPPORTED_FORMATS = set(FORMATTERS.keys())


# ── File writer ───────────────────────────────────────────

def save_format(result: Any, output_dir: Path, job_id: str, fmt: str) -> Path:
    """Save a single format to disk. Returns the output file path."""
    if fmt not in FORMATTERS:
        raise ValueError(f"Unknown format: {fmt}. Supported: {SUPPORTED_FORMATS}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    content = FORMATTERS[fmt](result)
    out_path = output_dir / f"{job_id}.{fmt}"
    out_path.write_text(content, encoding="utf-8")

    logger.info("Saved %s: %s (%d bytes)", fmt, out_path.name, len(content))
    return out_path


def save_all_formats(
    result: Any,
    output_dir: Path,
    job_id: str,
    formats: list[str] | None = None,
) -> dict[str, Path]:
    """
    Save transcription in multiple formats.
    Returns dict mapping format name → file path.

    Args:
        result:     TranscriptionResult from transcriber.py
        output_dir: Directory to write files into
        job_id:     Used as the filename base (e.g., "abc123.srt")
        formats:    List of formats to generate. Default: ["txt", "srt", "json"]
    """
    if formats is None:
        formats = ["txt", "srt", "json"]

    saved = {}
    for fmt in formats:
        saved[fmt] = save_format(result, output_dir, job_id, fmt)

    return saved


# ── Self-test ──────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile
    from dataclasses import dataclass, field

    print("=" * 50)
    print("  postprocessor.py — self-test")
    print("=" * 50)

    # Create mock data matching transcriber.py dataclass structure
    @dataclass
    class MockWord:
        word: str
        start: float
        end: float
        probability: float

    @dataclass
    class MockSegment:
        id: int
        start: float
        end: float
        text: str
        words: list = field(default_factory=list)
        avg_logprob: float = -0.3
        no_speech_prob: float = 0.02

    @dataclass
    class MockResult:
        text: str = ""
        segments: list = field(default_factory=list)
        language: str = "en"
        language_probability: float = 0.97
        duration: float = 12.5
        processing_time: float = 2.1
        model_name: str = "large-v3-turbo"

        @property
        def rtf(self):
            return self.processing_time / self.duration if self.duration > 0 else 0

    mock = MockResult(
        text="Hello world. This is a test of the transcription system.",
        segments=[
            MockSegment(
                id=0, start=0.0, end=2.8,
                text="Hello world.",
                words=[
                    MockWord("Hello", 0.0, 0.8, 0.98),
                    MockWord("world.", 0.9, 2.8, 0.95),
                ],
            ),
            MockSegment(
                id=1, start=3.2, end=7.5,
                text="This is a test of the transcription system.",
                words=[
                    MockWord("This", 3.2, 3.6, 0.97),
                    MockWord("is", 3.65, 3.9, 0.99),
                    MockWord("a", 3.95, 4.1, 0.99),
                    MockWord("test", 4.15, 4.6, 0.96),
                    MockWord("of", 4.65, 4.85, 0.98),
                    MockWord("the", 4.9, 5.1, 0.99),
                    MockWord("transcription", 5.15, 6.2, 0.92),
                    MockWord("system.", 6.25, 7.5, 0.94),
                ],
            ),
        ],
    )

    # 1. Test TXT
    txt = to_txt(mock)
    assert "Hello world" in txt
    print(f"[OK] TXT: {len(txt)} chars")

    # 2. Test SRT
    srt = to_srt(mock)
    assert "1\n00:00:00,000 --> 00:00:02,800\nHello world." in srt
    assert "2\n00:00:03,200 --> 00:00:07,500" in srt
    print(f"[OK] SRT: {srt.count(chr(10))} lines, valid sequence numbers")

    # 3. Test VTT
    vtt = to_vtt(mock)
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:02.800" in vtt
    print(f"[OK] VTT: starts with WEBVTT, dot timestamps")

    # 4. Test JSON
    j = to_json(mock)
    data = json.loads(j)
    assert data["language"] == "en"
    assert len(data["segments"]) == 2
    assert len(data["segments"][1]["words"]) == 8
    assert data["rtf"] > 0
    print(f"[OK] JSON: {len(data['segments'])} segments, {len(data['segments'][1]['words'])} words in seg 2")

    # 5. Test timestamp edge cases
    assert _format_ts_srt(0) == "00:00:00,000"
    assert _format_ts_srt(3661.5) == "01:01:01,500"
    assert _format_ts_srt(86399.999) == "23:59:59,999"
    assert _format_ts_vtt(3661.5) == "01:01:01.500"
    print("[OK] Timestamp formatting: edge cases passed")

    # 6. Test save to disk
    with tempfile.TemporaryDirectory() as tmp_dir:
        saved = save_all_formats(mock, Path(tmp_dir), "test_job", ["txt", "srt", "vtt", "json"])
        assert len(saved) == 4
        for fmt, path in saved.items():
            assert path.exists()
            size = path.stat().st_size
            print(f"[OK] Saved {fmt}: {path.name} ({size} bytes)")

    # 7. Test unsupported format
    try:
        save_format(mock, Path("/tmp"), "x", "pdf")
        print("[FAIL] Should have raised ValueError for 'pdf'")
    except ValueError:
        print("[OK] Unsupported format 'pdf' raises ValueError")

    print(f"\n[OK] All postprocessor tests passed!")