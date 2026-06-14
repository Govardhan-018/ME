import os
import time
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wavfile
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

def listen_and_transcribe() -> str:
    SAMPLE_RATE = 16000
    CHANNELS = 1
    SILENCE_THRESHOLD = 300  
    MAX_SILENCE_DURATION = 2.0  
    
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    
    audio_data = []
    is_recording = True
    silent_chunks = 0
    
    chunk_duration = 0.1
    chunk_samples = int(SAMPLE_RATE * chunk_duration)
    max_silent_chunks = int(MAX_SILENCE_DURATION / chunk_duration)

    def audio_callback(indata, frames, time_info, status):
        nonlocal is_recording, silent_chunks
        
        if not is_recording:
            return
            
        audio_data.append(indata.copy())
        rms = np.sqrt(np.mean(indata**2))
        
        if rms < SILENCE_THRESHOLD:
            silent_chunks += 1
        else:
            silent_chunks = 0
            
        if silent_chunks >= max_silent_chunks:
            is_recording = False
            raise sd.CallbackStop()

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE, 
            channels=CHANNELS, 
            dtype="int16",
            blocksize=chunk_samples,
            callback=audio_callback
        ):
            while is_recording:
                time.sleep(0.1)
                
    except sd.CallbackStop:
        pass
    except Exception:
        return ""

    if not audio_data:
        return ""

    audio_np = np.concatenate(audio_data, axis=0)

    if audio_np.shape[0] < SAMPLE_RATE * 0.5:
        return ""

    try:
        temp_path = "temp_recording.wav"
        wavfile.write(temp_path, SAMPLE_RATE, audio_np)

        with open(temp_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=("temp_recording.wav", f.read()),
                model="whisper-large-v3",
                response_format="text",
            )

        try:
            os.remove(temp_path)
        except OSError:
            pass

        return transcription.strip() if transcription else ""

    except Exception:
        return ""

if __name__ == "__main__":
    text = listen_and_transcribe()
    if text:
        print(text)