import pyttsx3

def text_to_speech(text: str):
    """
    Converts text to audio and automatically plays it 
    through the desktop's default soundbox/speakers.
    """
    if not text:
        return
        
    # Initialize the text-to-speech engine
    engine = pyttsx3.init()
    
    # Optional settings you can tweak:
    # engine.setProperty('rate', 170)    # Speed of speech (default is ~200)
    # engine.setProperty('volume', 1.0)  # Volume (0.0 to 1.0)
    
    # Queue the text and play it
    engine.say(text)
    
    # Block execution until the audio finishes playing
    engine.runAndWait()

if __name__ == "__main__":
    # Test the function
    text_to_speech("Hello, I am Jarvis. All systems are fully operational.")