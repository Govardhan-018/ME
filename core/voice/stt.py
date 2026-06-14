"""Local speech-to-text via faster-whisper (offline, no cloud, no API key).

Model loads lazily on first use so it never slows brain startup. Decoding of
browser audio blobs (webm/opus) is handled by faster-whisper via PyAV.
"""
from __future__ import annotations

import threading

from faster_whisper import WhisperModel

_MODEL_NAME = "base"  # fast + accurate enough for commands; bump to "small"/"medium" if you want
_lock = threading.Lock()
_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = WhisperModel(_MODEL_NAME, device="auto", compute_type="int8")
    return _model


def transcribe_file(path: str, language: str = "en") -> str:
    """Transcribe an audio file (any format PyAV can decode) to text."""
    return _run(path, language)


def transcribe_array(audio, language: str = "en") -> str:
    """Transcribe a float32 mono 16kHz numpy array (e.g. live mic capture)."""
    return _run(audio, language)


def _run(audio, language: str) -> str:
    model = _get_model()
    segments, _ = model.transcribe(
        audio,
        beam_size=1,
        language=language,
        vad_filter=True,
        condition_on_previous_text=False,
        without_timestamps=True,
    )
    return " ".join(seg.text for seg in segments).strip()
