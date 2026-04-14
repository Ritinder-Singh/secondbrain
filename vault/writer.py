"""
Obsidian vault writer.
Creates and maintains the PARA folder structure and writes markdown notes
with YAML frontmatter for every ingested source.
"""
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import settings

PARA_FOLDERS = ["Projects", "Areas", "Resources", "Archive", "Research"]


def setup_vault() -> None:
    """Create the PARA folder structure inside VAULT_PATH."""
    vault = settings.VAULT_PATH
    vault.mkdir(parents=True, exist_ok=True)
    for folder in PARA_FOLDERS:
        (vault / folder).mkdir(exist_ok=True)
    print(f"✓ Vault ready at {vault}")


def _slugify(text: str) -> str:
    """Convert a title to a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:80]


def write_source_note(
    parsed: dict,
    para_category: str = "Resources",
    tags: Optional[list] = None,
) -> Path:
    """
    Write an ingested source as an Obsidian markdown note.

    Args:
        parsed: Output dict from ingestion/parsers/content.py
        para_category: PARA folder to place the note in
        tags: List of tag strings

    Returns:
        Path to the written note
    """
    vault = settings.VAULT_PATH
    folder = vault / para_category
    folder.mkdir(parents=True, exist_ok=True)

    slug = _slugify(parsed["title"])
    note_path = folder / f"{slug}.md"

    tags_yaml = ""
    if tags:
        tags_yaml = "\ntags:\n" + "\n".join(f"  - {t}" for t in tags)

    source_url = parsed.get("source_url") or ""
    file_path = parsed.get("file_path") or ""
    ingested_at = datetime.now().strftime("%Y-%m-%d")

    # Content snippet (first 800 chars) for quick reference in the vault
    snippet = parsed.get("text", "")[:800].strip()
    if len(parsed.get("text", "")) > 800:
        snippet += "…"

    meta = parsed.get("metadata", {})
    meta_lines = "\n".join(f"  {k}: {v}" for k, v in meta.items() if v)
    meta_block = f"\n## Metadata\n```\n{meta_lines}\n```" if meta_lines else ""

    content = f"""---
title: "{parsed['title'].replace('"', "'")}"
source_type: {parsed['source_type']}
source_url: {source_url}
file_path: {file_path}
para_category: {para_category}
ingested_at: {ingested_at}{tags_yaml}
---

## Summary

> *Auto-generated summary will appear here in Phase 4.*

## Content

{snippet}
{meta_block}

## Source

{"[" + parsed['title'] + "](" + source_url + ")" if source_url else file_path or "—"}
"""

    note_path.write_text(content, encoding="utf-8")
    return note_path


def write_research_note(
    topic: str,
    content: str,
    source_note: Optional[str] = None,
) -> Path:
    """
    Write an AI-generated research note to the Research PARA folder.
    Implemented in Phase 3 — stub raises NotImplementedError for now.
    """
    raise NotImplementedError("Research note writing is implemented in Phase 3")
