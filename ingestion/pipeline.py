"""
Ingestion pipeline: parse → chunk → embed → postgres + obsidian vault.
Single ingest(source) call handles everything end-to-end.
"""
import uuid
from datetime import datetime
from pathlib import Path

from ingestion.parsers.content import parse
from ingestion.chunkers.strategies import get_chunks
from core.vector_store import vector_store
from vault.writer import write_source_note

# Chunk strategy to use per source type
_STRATEGY_MAP = {
    "pdf":      "recursive",
    "article":  "sentence",
    "youtube":  "sentence",
    "audio":    "sentence",
    "github":   "code",
    "markdown": "recursive",
    "text":     "recursive",
}


def ingest(source: str, para_category: str = "Resources", tags: list = None) -> dict:
    """
    Ingest any supported source into the knowledge base.

    Steps:
      1. Parse source (PDF, URL, YouTube, audio, markdown, text)
      2. Chunk text using the appropriate strategy
      3. Embed all chunks in one batch call + store in pgvector
      4. Write an Obsidian markdown note

    Args:
        source: URL, file path, or YouTube URL
        para_category: PARA folder (Projects | Areas | Resources | Archive)
        tags: Optional list of tag strings

    Returns:
        dict with title, source_type, chunks count, doc_id, vault_note path
    """
    tags = tags or []

    print(f"[1/4] Parsing: {source}")
    parsed = parse(source)

    print(f"[2/4] Chunking '{parsed['title']}' ({len(parsed['text'])} chars)")
    strategy = _STRATEGY_MAP.get(parsed["source_type"], "recursive")
    chunks = [c for c in get_chunks(parsed["text"], strategy=strategy) if len(c.strip()) > 30]
    print(f"       {len(chunks)} chunks")

    # Deterministic doc_id via uuid5 — deduplicates re-ingestion of the same source
    doc_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        parsed.get("source_url") or parsed.get("file_path") or parsed["title"],
    ))

    print(f"[3/4] Embedding + storing {len(chunks)} chunks in pgvector...")
    vector_store.upsert_document({
        "id":           doc_id,
        "title":        parsed["title"],
        "source_type":  parsed["source_type"],
        "source_url":   parsed.get("source_url") or "",
        "file_path":    parsed.get("file_path") or "",
        "para_category": para_category,
        "tags":         tags,
        "metadata":     parsed.get("metadata", {}),
    })

    chunk_records = [
        {
            "id":          f"{doc_id}__chunk_{i}",
            "doc_id":      doc_id,
            "chunk_index": i,
            "text":        text,
            "metadata": {
                "title":        parsed["title"],
                "source_type":  parsed["source_type"],
                "source_url":   parsed.get("source_url") or "",
                "file_path":    parsed.get("file_path") or "",
                "para_category": para_category,
                "tags":         ",".join(tags),
                "ingested_at":  datetime.now().isoformat(),
            },
        }
        for i, text in enumerate(chunks)
    ]
    vector_store.add_batch(chunk_records)

    print(f"[4/4] Writing Obsidian note...")
    note_path = write_source_note(parsed, para_category=para_category, tags=tags)

    # Update vault_note path on the document record
    vector_store.upsert_document({
        "id":          doc_id,
        "title":       parsed["title"],
        "source_type": parsed["source_type"],
        "source_url":  parsed.get("source_url") or "",
        "file_path":   parsed.get("file_path") or "",
        "vault_note":  str(note_path),
        "para_category": para_category,
        "tags":        tags,
        "metadata":    parsed.get("metadata", {}),
    })

    print(f"\n✓ '{parsed['title']}' — {len(chunks)} chunks indexed\n")
    return {
        "title":       parsed["title"],
        "source_type": parsed["source_type"],
        "chunks":      len(chunks),
        "doc_id":      doc_id,
        "vault_note":  str(note_path),
    }
