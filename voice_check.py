# jarvis_voice.py
# Simple wake word detection using SpeechRecognition + faster-whisper
#
# Install:
#   pip install SpeechRecognition faster-whisper pyaudio numpy
#   Linux:  sudo apt-get install portaudio19-dev
#   Mac:    brew install portaudio

import speech_recognition as sr
import numpy as np
from faster_whisper import WhisperModel

# ── Config (edit these) ──────────────────────────────────
# The keyword to listen for, along with common mishearings by the Whisper model
WAKE_WORDS = [
    "jarvis", "javis", "garvis", "travis", "jervis", 
    "arvis", "jarv is", "charles", "dervis", "chavis", 
    "jawis", "jarrus", "harvis", "charvis", "jar vis", 
    "service", "tervis", "nervous", "gervis", "jourvis",
    "chavez", "javas", "tarvis", "darvis"
]
LANGUAGE   = "en"
# ─────────────────────────────────────────────────────────

print("Loading models...")
wake_model = WhisperModel("base", device="auto", compute_type="int8")  # fast, for wake word
cmd_model  = WhisperModel("base", device="auto", compute_type="int8")  # accurate, for commands

r = sr.Recognizer()
r.pause_threshold  = 0.5   # decreased from 0.8 for snappier response
r.energy_threshold = 300   # mic sensitivity — raise if false triggers, lower if not hearing you

def to_numpy(audio: sr.AudioData) -> np.ndarray:
    raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

def transcribe(audio: sr.AudioData, model: WhisperModel) -> str:
    segments, _ = model.transcribe(
        to_numpy(audio),
        beam_size=1,
        language=LANGUAGE,
        vad_filter=True,   # built-in silence filter
        condition_on_previous_text=False, # speeds up transcription
        without_timestamps=True # skips computing timestamps
    )
    return " ".join(s.text for s in segments).strip().lower()

def on_command(text: str):
    """Your handler — replace with LLM call."""
    print(f"\n💬 Command: '{text}'")
    # e.g: response = your_llm_pipeline(text)
    # speak(response)

def wait_for_wake_word(source=None) -> bool:
    """
    Listens until the wake word is detected.
    Returns True when heard, or False if interrupted.
    """
    print(f"\n✅ Ready — say '{WAKE_WORDS[0]}' to activate\n")
    
    if source is None:
        with sr.Microphone(sample_rate=16000) as src:
            r.adjust_for_ambient_noise(src, duration=1)
            return _listen_for_wake_word(src)
    else:
        return _listen_for_wake_word(source)

def _listen_for_wake_word(source) -> bool:
    while True:
        try:
            audio = r.listen(source, phrase_time_limit=4)
            text  = transcribe(audio, wake_model)
            print(f"\r[idle] heard: {text[:50]:<50}", end="")

            if any(word in text for word in WAKE_WORDS):
                print(f"\n🟢 Activated!")
                return True
        except KeyboardInterrupt:
            print("\n\nStopped.")
            return False
        except Exception as e:
            print(f"\n[error] {e}")

def get_command(source=None) -> str:
    """Listens for and transcribes a spoken command."""
    print("🎙️  Speak your command...\n")
    if source is None:
        with sr.Microphone(sample_rate=16000) as src:
            return _listen_for_command(src)
    else:
        return _listen_for_command(source)

def _listen_for_command(source) -> str:
    try:
        audio = r.listen(source, timeout=8, phrase_time_limit=20)
        return transcribe(audio, cmd_model)
    except sr.WaitTimeoutError:
        return ""
    except Exception as e:
        print(f"\n[error] {e}")
        return ""

# ── Main loop ────────────────────────────────────────────
if __name__ == "__main__":
    # We initialize the microphone once here to avoid delays between listening phases
    with sr.Microphone(sample_rate=16000) as main_source:
        r.adjust_for_ambient_noise(main_source, duration=1)
        
        while True:
            if wait_for_wake_word(main_source):
                command = get_command(main_source)
                if command:
                    on_command(command)
                
                print(f"\n💤 Back to sleep — say '{WAKE_WORDS[0]}' again\n")
            else:
                break