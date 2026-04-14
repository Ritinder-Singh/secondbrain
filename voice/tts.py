"""
Text-to-speech.
Uses pyttsx3 (offline, no download needed) as the default engine.
Piper TTS can be swapped in for higher quality if installed.
"""


def speak(text: str) -> None:
    """Speak text aloud using the best available TTS engine."""
    try:
        _speak_pyttsx3(text)
    except Exception as e:
        print(f"[TTS] Error: {e}")
        print(f"[TTS] {text}")   # fallback: just print


def _speak_pyttsx3(text: str) -> None:
    import pyttsx3
    engine = pyttsx3.init()
    engine.setProperty("rate", 175)    # words per minute
    engine.setProperty("volume", 0.9)
    engine.say(text)
    engine.runAndWait()
    engine.stop()
