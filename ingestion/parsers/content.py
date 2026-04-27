"""
Content parsers. Each returns a standard dict:
  {title, text, source_type, source_url, file_path, metadata}
Single parse(source) function auto-detects the source type.
"""
import re
from pathlib import Path
from datetime import datetime


def parse_pdf(path) -> dict:
    import fitz
    doc = fitz.open(str(path))
    text = "\n\n".join(page.get_text() for page in doc)
    return {
        "title": doc.metadata.get("title") or Path(path).stem,
        "text": text,
        "source_type": "pdf",
        "source_url": None,
        "file_path": str(Path(path).resolve()),
        "metadata": {
            "author": doc.metadata.get("author", ""),
            "pages": len(doc),
        },
    }


def parse_url(url: str) -> dict:
    import trafilatura
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise ValueError(f"Could not fetch: {url}")
    text = trafilatura.extract(downloaded, include_tables=True) or ""
    meta = trafilatura.extract_metadata(downloaded)
    return {
        "title": (meta.title if meta else None) or url.split("/")[-1],
        "text": text,
        "source_type": "article",
        "source_url": url,
        "file_path": None,
        "metadata": {
            "author": meta.author if meta else "",
            "date": meta.date if meta else "",
            "sitename": meta.sitename if meta else "",
        },
    }


def parse_youtube(url: str) -> dict:
    import yt_dlp
    import tempfile
    import os
    from config.settings import settings

    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        outtmpl = os.path.join(tmpdir, "audio.%(ext)s")
        with yt_dlp.YoutubeDL({
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
            "quiet": True,
        }) as ydl:
            ydl.download([url])

        # find the actual output file (yt-dlp may vary the name)
        candidates = [f for f in os.listdir(tmpdir) if f.endswith(".mp3")]
        if not candidates:
            raise RuntimeError(f"yt-dlp produced no mp3 in {tmpdir}: {os.listdir(tmpdir)}")
        audio_path = os.path.join(tmpdir, candidates[0])

        transcript = _transcribe_youtube(audio_path, settings)

    return {
        "title": info.get("title", "Unknown"),
        "text": transcript,
        "source_type": "youtube",
        "source_url": url,
        "file_path": None,
        "metadata": {
            "channel": info.get("channel", ""),
            "duration_seconds": info.get("duration", 0),
            "transcribed_at": datetime.now().isoformat(),
            "transcriber": "groq" if _settings_has_groq() else "local",
        },
    }


def _settings_has_groq() -> bool:
    from config.settings import settings
    return bool(settings.GROQ_API_KEY)


def _transcribe_youtube(audio_path: str, settings) -> str:
    """Groq Whisper for YouTube (public content). Falls back to local if no key."""
    if settings.GROQ_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=settings.GROQ_API_KEY,
                base_url="https://api.groq.com/openai/v1",
            )
            with open(audio_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    model=settings.GROQ_WHISPER_MODEL,
                    file=f,
                )
            return result.text
        except Exception as e:
            print(f"[YouTube] Groq transcription failed ({e}), falling back to local Whisper")

    from faster_whisper import WhisperModel
    model = WhisperModel(settings.WHISPER_MODEL, device=settings.WHISPER_DEVICE)
    segments, _ = model.transcribe(audio_path, beam_size=5)
    return " ".join(s.text for s in segments)


def parse_audio_file(path) -> dict:
    from faster_whisper import WhisperModel
    from config.settings import settings
    path = Path(path)
    model = WhisperModel(settings.WHISPER_MODEL, device=settings.WHISPER_DEVICE)
    segments, info = model.transcribe(str(path), beam_size=5)
    return {
        "title": path.stem,
        "text": " ".join(s.text for s in segments),
        "source_type": "audio",
        "source_url": None,
        "file_path": str(path.resolve()),
        "metadata": {
            "duration": info.duration,
            "language": info.language,
        },
    }


def parse_text_file(path) -> dict:
    path = Path(path)
    return {
        "title": path.stem,
        "text": path.read_text(encoding="utf-8", errors="ignore"),
        "source_type": "markdown" if path.suffix == ".md" else "text",
        "source_url": None,
        "file_path": str(path.resolve()),
        "metadata": {},
    }


def _unsupported(path) -> dict:
    raise ValueError(f"Unsupported file type: {Path(path).suffix}")


_EXTENSION_MAP = {
    ".pdf": parse_pdf,
    ".md":  parse_text_file,
    ".txt": parse_text_file,
    ".mp3": parse_audio_file,
    ".wav": parse_audio_file,
    ".m4a": parse_audio_file,
    ".ogg": parse_audio_file,
}


def parse(source: str) -> dict:
    """Auto-detect and parse any supported source."""
    if source.startswith("http"):
        if "youtube.com" in source or "youtu.be" in source:
            return parse_youtube(source)
        return parse_url(source)
    path = Path(source)
    parser = _EXTENSION_MAP.get(path.suffix.lower(), _unsupported)
    return parser(path)
