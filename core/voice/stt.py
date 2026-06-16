"""Speech-to-text for JARVIS.

Auto-routes to **Groq** (`whisper-large-v3`, fast cloud) when `GROQ_API_KEY` is
set, otherwise falls back to **local faster-whisper** (offline). The brain/voice
loop just call transcribe_array / transcribe_bytes and get whichever is active.
"""
from __future__ import annotations

import io
import os
import tempfile
import threading
import wave

import numpy as np
from dotenv import load_dotenv

try:
    load_dotenv()  # ensure GROQ_API_KEY is available regardless of import order
except Exception:
    pass

_GROQ_MODEL = "whisper-large-v3"
_LOCAL_MODEL = "base"


def use_groq() -> bool:
    return bool(os.environ.get("GROQ_API_KEY"))


def backend_name() -> str:
    return "groq" if use_groq() else "local-whisper"


# ── Groq (cloud) ─────────────────────────────────────────────────────────────
def _groq_bytes(data: bytes, filename: str) -> str:
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    r = client.audio.transcriptions.create(
        file=(filename, data),
        model=_GROQ_MODEL,
        response_format="text",
    )
    return (r if isinstance(r, str) else getattr(r, "text", "")).strip()


def _float32_to_wav(audio: np.ndarray, sr: int = 16000) -> bytes:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


# ── Local faster-whisper (lazy; only imported if actually used) ──────────────
_lock = threading.Lock()
_model = None


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from faster_whisper import WhisperModel

                _model = WhisperModel(_LOCAL_MODEL, device="auto", compute_type="int8")
    return _model


def _local(audio, language: str) -> str:
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


# ── Public API (auto-routes) ─────────────────────────────────────────────────
def transcribe_array(audio: np.ndarray, language: str = "en") -> str:
    """Transcribe a float32 mono 16kHz numpy array (live mic capture)."""
    if use_groq():
        return _groq_bytes(_float32_to_wav(audio), "command.wav")
    return _local(audio, language)


def transcribe_bytes(data: bytes, filename: str = "audio.webm", language: str = "en") -> str:
    """Transcribe raw audio bytes (e.g. webm from the browser)."""
    if use_groq():
        return _groq_bytes(data, filename)
    suffix = os.path.splitext(filename)[1] or ".webm"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        tmp.close()
        return _local(tmp.name, language)
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass


def transcribe_file(path: str, language: str = "en") -> str:
    if use_groq():
        with open(path, "rb") as f:
            return _groq_bytes(f.read(), os.path.basename(path))
    return _local(path, language)
