"""Always-on voice assistant loop for JARVIS.

    greet -> wait for "Hey Jarvis" -> record the command -> transcribe ->
    orchestrate -> speak the answer -> back to listening.

Runs in a daemon thread inside the FastAPI brain. It publishes its live state
to module-level STATE, which `GET /api/voice/state` returns so the UI can mirror
it (orb reacts, transcript + answer appear in chat). All audio stays local:
sounddevice (mic) + openWakeWord (wake) + faster-whisper (STT) + pyttsx3 (TTS).
"""
from __future__ import annotations

import threading
import time

import numpy as np
import sounddevice as sd

WAKE_PHRASE = "Hey Jarvis"

# ── Published state (read by the API / UI) ───────────────────────────────────
_lock = threading.Lock()
STATE: dict = {
    "enabled": False,
    "running": False,
    "state": "offline",  # offline | idle | listening | processing | thinking | speaking
    "wake_phrase": WAKE_PHRASE,
    "user_turn": 0,
    "user_text": "",
    "answer_turn": 0,
    "answer_text": "",
    "answer_domain": "general",
    "error": None,
}


def get_state() -> dict:
    with _lock:
        return dict(STATE)


def _set(**kw) -> None:
    with _lock:
        STATE.update(kw)


# ── Audio params ─────────────────────────────────────────────────────────────
SR = 16000
FRAME = 1280  # 80 ms @ 16 kHz — the chunk size openWakeWord expects
WAKE_THRESHOLD = 0.5
SILENCE_RMS = 0.012  # below this (float32) counts as silence
MAX_SILENCE = 1.2  # seconds of trailing silence ends a command
MAX_COMMAND = 12.0  # hard cap on a single command


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x * x)) + 1e-9)


def _record_command(stream: "sd.InputStream") -> np.ndarray:
    """Read from an open stream until trailing silence (or max). Returns float32."""
    chunks: list[np.ndarray] = []
    silent = 0.0
    spoken = False
    start = time.time()
    while True:
        block, _ = stream.read(FRAME)
        mono = block[:, 0]
        chunks.append(mono.copy())
        if _rms(mono) > SILENCE_RMS:
            spoken = True
            silent = 0.0
        elif spoken:
            silent += FRAME / SR
        if spoken and silent >= MAX_SILENCE:
            break
        if time.time() - start > MAX_COMMAND:
            break
    return np.concatenate(chunks) if chunks else np.zeros(0, dtype="float32")


def _handle_turn(stream, stt, speaker, orchestrator) -> None:
    _set(state="listening")
    audio = _record_command(stream)
    if audio.shape[0] < SR * 0.4:  # too short — probably a false wake
        _set(state="idle")
        return

    _set(state="processing")
    try:
        text = stt.transcribe_array(audio).strip()
    except Exception as e:
        _set(state="idle", error=f"stt: {e}")
        return
    if not text:
        _set(state="idle")
        return

    _set(state="thinking", user_turn=STATE["user_turn"] + 1, user_text=text)
    try:
        res = orchestrator.orchestrate(text)
        domain = res.get("domain", "general")
        answer = res.get("answer")
        if not answer:
            result = res.get("result") or {}
            if isinstance(result, dict):
                answer = (result.get("synthesis") or {}).get("answer")
        answer = answer or res.get("error") or "Done."
    except Exception as e:
        domain, answer = "general", f"Something went wrong: {e}"

    _set(state="speaking", answer_turn=STATE["answer_turn"] + 1, answer_text=answer, answer_domain=domain)
    speaker.speak(answer)
    _set(state="idle")


def run() -> None:
    """Blocking voice loop — start in a daemon thread."""
    # Heavy imports kept out of brain startup.
    from core.voice import stt, speaker
    from core.agents import orchestrator

    _set(enabled=True, state="offline", error=None)

    try:
        import openwakeword
        from openwakeword.model import Model

        try:
            openwakeword.utils.download_models()
        except Exception:
            pass  # already present / offline
        oww = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
    except Exception as e:
        _set(state="offline", error=f"wake-word init failed: {e}")
        print(f"[voice] wake-word init failed: {e}")
        return

    print(f"[voice] STT backend: {stt.backend_name()}")

    # Greeting (shown in chat + spoken).
    _set(
        running=True,
        state="idle",
        answer_turn=STATE["answer_turn"] + 1,
        answer_text="Systems online. Say 'Hey Jarvis' whenever you need me.",
        answer_domain="general",
    )
    speaker.speak("Systems online. I'm ready.")

    def wake_score(int16_frame: np.ndarray) -> float:
        preds = oww.predict(int16_frame)
        return max((v for k, v in preds.items() if "jarvis" in k.lower()), default=0.0)

    try:
        with sd.InputStream(samplerate=SR, channels=1, dtype="float32", blocksize=FRAME) as stream:
            while True:
                block, _ = stream.read(FRAME)
                mono = block[:, 0]
                int16 = (np.clip(mono, -1.0, 1.0) * 32767).astype(np.int16)
                if wake_score(int16) >= WAKE_THRESHOLD:
                    oww.reset()
                    _handle_turn(stream, stt, speaker, orchestrator)
                    # Discard audio buffered during the turn/TTS so JARVIS doesn't
                    # hear itself, then reset the detector.
                    try:
                        avail = stream.read_available
                        if avail:
                            stream.read(avail)
                    except Exception:
                        pass
                    oww.reset()
    except Exception as e:
        _set(state="offline", error=str(e))
        print(f"[voice] loop error: {e}")
