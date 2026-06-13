import speech_recognition as sr
import numpy as np
from faster_whisper import WhisperModel

WAKE_WORDS = [
    "jarvis", "javis", "garvis", "travis", "jervis", 
    "arvis", "jarv is", "charles", "dervis", "chavis", 
    "jawis", "jarrus", "harvis", "charvis", "jar vis", 
    "service", "tervis", "nervous", "gervis", "jourvis",
    "chavez", "javas", "tarvis", "darvis"
]

print("Loading...")
wake_model = WhisperModel("base", device="auto", compute_type="int8")

r = sr.Recognizer()
r.pause_threshold = 0.5
r.energy_threshold = 300

def to_numpy(audio: sr.AudioData) -> np.ndarray:
    raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

def transcribe(audio: sr.AudioData) -> str:
    segments, _ = wake_model.transcribe(
        to_numpy(audio),
        beam_size=1,
        language="en",
        vad_filter=True,
        condition_on_previous_text=False,
        without_timestamps=True
    )
    return " ".join(s.text for s in segments).strip().lower()

def wait_for_wake_word(source=None) -> bool:
    if source is None:
        with sr.Microphone(sample_rate=16000) as src:
            r.adjust_for_ambient_noise(src, duration=1)
            return _listen_for_wake_word(src)
    return _listen_for_wake_word(source)

def _listen_for_wake_word(source) -> bool:
    while True:
        try:
            audio = r.listen(source, phrase_time_limit=4)
            text  = transcribe(audio)

            if any(word in text for word in WAKE_WORDS):
                return True
        except (KeyboardInterrupt, Exception):
            return False

if __name__ == "__main__":
    wait_for_wake_word()