"""Local text-to-speech via ElevenLabs API and playsound. Blocking."""
from __future__ import annotations

import os
import requests
import tempfile

def speak(text: str) -> None:
    if not text:
        return
        
    api_key = os.getenv("ELEVENLABS_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    
    if not api_key:
        print("[voice] ElevenLabs API key not set, fallback to print:", text)
        return
        
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }
    data = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.5}
    }
    
    try:
        from playsound3 import playsound
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        
        # Save to temp file and play
        fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        with os.fdopen(fd, "wb") as f:
            f.write(response.content)
            
        playsound(temp_path)
        
        try:
            os.remove(temp_path)
        except OSError:
            pass # Windows sometimes holds a lock temporarily
    except Exception as e:
        print(f"[voice] TTS error: {e}")
