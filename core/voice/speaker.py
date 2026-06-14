"""Local text-to-speech via pyttsx3 (Windows SAPI, offline). Blocking.

A fresh engine per call avoids the well-known pyttsx3 reuse/hang issues.
"""
from __future__ import annotations

import pyttsx3

_VOICE_HINT = "david"  # prefer the male SAPI voice; falls back to default


def speak(text: str) -> None:
    if not text:
        return
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", 180)
        for v in engine.getProperty("voices"):
            if _VOICE_HINT in (getattr(v, "name", "") or "").lower():
                engine.setProperty("voice", v.id)
                break
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:  # never let TTS crash the voice loop
        print(f"[voice] TTS error: {e}")
