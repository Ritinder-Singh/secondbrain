"""
Microphone recording + Whisper transcription.
Records until silence or Ctrl+C, transcribes locally via faster-whisper.
"""
import io
import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from config.settings import settings

# Recording config
SAMPLE_RATE = 16_000   # Whisper expects 16kHz
CHANNELS = 1
DTYPE = "int16"
SILENCE_THRESHOLD = 500        # RMS below this = silence
SILENCE_DURATION_S = 2.0       # seconds of silence before auto-stop
CHUNK_DURATION_S = 0.5         # process chunks of this length


def record_until_silence(max_seconds: int = 120) -> np.ndarray:
    """
    Record from microphone until silence is detected or max_seconds reached.
    Returns audio as a numpy array (int16, 16kHz mono).
    """
    print("🎙  Recording... (speak now, stops after 2s of silence or Ctrl+C)")

    chunk_samples = int(SAMPLE_RATE * CHUNK_DURATION_S)
    silence_chunks_needed = int(SILENCE_DURATION_S / CHUNK_DURATION_S)

    frames = []
    silence_count = 0
    total_chunks = int(max_seconds / CHUNK_DURATION_S)

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE) as stream:
        for _ in range(total_chunks):
            chunk, _ = stream.read(chunk_samples)
            frames.append(chunk.copy())

            rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2))
            if rms < SILENCE_THRESHOLD:
                silence_count += 1
                if silence_count >= silence_chunks_needed:
                    break
            else:
                silence_count = 0

    audio = np.concatenate(frames, axis=0).flatten()
    print(f"  Recorded {len(audio) / SAMPLE_RATE:.1f}s")
    return audio


def transcribe(audio: np.ndarray) -> str:
    """Transcribe a numpy audio array using local faster-whisper."""
    from faster_whisper import WhisperModel

    model = WhisperModel(settings.WHISPER_MODEL, device=settings.WHISPER_DEVICE)
    audio_f32 = audio.astype(np.float32) / 32768.0

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        sf.write(f.name, audio_f32, SAMPLE_RATE)
        segments, _ = model.transcribe(f.name, beam_size=5)
        transcript = " ".join(s.text for s in segments).strip()
        Path(f.name).unlink(missing_ok=True)

    return transcript


def transcribe_file(path: str) -> str:
    """Transcribe an audio file path using local faster-whisper. Used for voice notes."""
    from faster_whisper import WhisperModel

    model = WhisperModel(settings.WHISPER_MODEL, device=settings.WHISPER_DEVICE)
    segments, _ = model.transcribe(path, beam_size=5)
    return " ".join(s.text for s in segments).strip()


def record_and_transcribe(max_seconds: int = 120) -> str:
    """Convenience: record from mic and return transcript."""
    audio = record_until_silence(max_seconds)
    print("  Transcribing...")
    text = transcribe(audio)
    print(f"  Transcript: {text}")
    return text


def ingest_voice_note(max_seconds: int = 120) -> dict | None:
    """
    Record a voice note, transcribe it, and ingest it into the knowledge base.
    Returns ingest result dict or None if nothing was recorded.
    """
    from ingestion.pipeline import ingest_parsed
    from vault.writer import write_source_note
    from datetime import datetime

    text = record_and_transcribe(max_seconds)
    if not text:
        print("  Nothing transcribed.")
        return None

    now = datetime.now()
    parsed = {
        "title":       f"Voice Note {now.strftime('%Y-%m-%d %H:%M')}",
        "text":        text,
        "source_type": "voice_note",
        "source_url":  None,
        "file_path":   None,
        "metadata":    {"recorded_at": now.isoformat()},
    }

    result = ingest_parsed(parsed, para_category="Resources", tags=["voice-note"])
    note_path = write_source_note(parsed, para_category="Resources", tags=["voice-note"])
    result["vault_note"] = str(note_path)

    print(f"\n✓ Voice note ingested → {note_path}")
    return result
