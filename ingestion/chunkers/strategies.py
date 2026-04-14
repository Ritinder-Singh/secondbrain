"""
Four chunking strategies. Strategy is auto-selected based on content type
but can be overridden via CHUNK_STRATEGY in .env.

Key insight: pure character chunking destroys sentence boundaries;
recursive splitting preserves semantic units; code needs function-level
boundaries to be useful for retrieval.
"""
import re
from config.settings import settings


def chunk_fixed(text: str, size: int = None, overlap: int = None) -> list[str]:
    """Split at fixed character intervals with overlap."""
    size = size or settings.CHUNK_SIZE
    overlap = overlap or settings.CHUNK_OVERLAP
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + size].strip())
        start += size - overlap
    return [c for c in chunks if c]


def chunk_sentence(text: str, max_size: int = None) -> list[str]:
    """Split on sentence boundaries, merging until max_size is reached."""
    max_size = max_size or settings.CHUNK_SIZE
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) > max_size and current:
            chunks.append(current.strip())
            current = s
        else:
            current += (" " if current else "") + s
    if current.strip():
        chunks.append(current.strip())
    return chunks


def chunk_recursive(text: str, size: int = None, overlap: int = None) -> list[str]:
    """
    Split on natural boundaries: paragraphs → sentences → words → chars.
    Best general-purpose strategy — preserves semantic units.
    """
    size = size or settings.CHUNK_SIZE
    overlap = overlap or settings.CHUNK_OVERLAP
    separators = ["\n\n", "\n", ". ", " ", ""]

    def _split(text: str, seps: list[str]) -> list[str]:
        if not seps:
            return [text]
        sep = seps[0]
        splits = text.split(sep) if sep else list(text)
        chunks, current = [], ""
        for part in splits:
            candidate = current + (sep if current else "") + part
            if len(candidate) <= size:
                current = candidate
            else:
                if current:
                    chunks.append(current.strip())
                if len(part) > size:
                    chunks.extend(_split(part, seps[1:]))
                else:
                    chunks.append(part)
                current = ""
        if current.strip():
            chunks.append(current.strip())
        return chunks

    raw = _split(text, separators)
    if not overlap:
        return [c for c in raw if c]

    overlapped = []
    for i, chunk in enumerate(raw):
        if i > 0 and raw[i - 1]:
            chunk = raw[i - 1][-overlap:] + " " + chunk
        overlapped.append(chunk.strip())
    return [c for c in overlapped if c]


def chunk_code(text: str, language: str = "python") -> list[str]:
    """
    Split code at function/class boundaries via regex.
    Falls back to recursive for large functions.
    TODO: Replace with Tree-sitter for production-grade AST parsing.
    """
    patterns = {
        "python":     r'(?=\n(?:def |class |async def ))',
        "javascript": r'(?=\n(?:function |const |class |export |async ))',
        "typescript": r'(?=\n(?:function |const |class |export |interface |type ))',
        "go":         r'(?=\nfunc )',
        "rust":       r'(?=\nfn |impl )',
    }
    pattern = patterns.get(language)
    if not pattern:
        return chunk_recursive(text)

    splits = re.split(pattern, text)
    chunks = []
    for split in splits:
        if len(split) <= settings.CHUNK_SIZE:
            if split.strip():
                chunks.append(split.strip())
        else:
            chunks.extend(chunk_recursive(split))
    return chunks


def get_chunks(text: str, strategy: str = None, **kwargs) -> list[str]:
    """Dispatch to the appropriate chunking strategy."""
    strategy = strategy or settings.CHUNK_STRATEGY
    fn = {
        "fixed":     chunk_fixed,
        "sentence":  chunk_sentence,
        "recursive": chunk_recursive,
        "code":      chunk_code,
    }.get(strategy, chunk_recursive)
    return fn(text, **kwargs)
