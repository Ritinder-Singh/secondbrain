"""
Obsidian vault writer.
Creates and maintains the PARA folder structure and writes markdown notes
with YAML frontmatter for every ingested source.
Optionally auto-commits and pushes to a GitHub repo after every write.
"""
import re
import subprocess
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
    _git_sync(vault, f"add: {parsed['title'][:60]}")
    return note_path


def _git_sync(vault: Path, commit_msg: str) -> None:
    """
    Auto-commit and push vault changes to GitHub.
    Silently skips if VAULT_REPO_URL is not configured or git fails.
    Uses token-authenticated HTTPS remote.
    """
    if not settings.VAULT_REPO_URL or not settings.VAULT_GITHUB_TOKEN:
        return

    # Inject token into remote URL: https://<token>@github.com/user/repo
    url = settings.VAULT_REPO_URL
    if "https://" in url and "@" not in url:
        url = url.replace("https://", f"https://{settings.VAULT_GITHUB_TOKEN}@")

    try:
        env = {"GIT_TERMINAL_PROMPT": "0"}  # never prompt for credentials
        run = lambda cmd: subprocess.run(
            cmd, cwd=vault, capture_output=True, text=True, env={**__import__("os").environ, **env}
        )

        # Init repo if first time
        if not (vault / ".git").exists():
            run(["git", "init"])
            run(["git", "remote", "add", "origin", url])
        else:
            # Update remote URL with fresh token (token may have changed)
            run(["git", "remote", "set-url", "origin", url])

        run(["git", "add", "-A"])
        result = run(["git", "commit", "-m", commit_msg])
        if result.returncode == 0:
            run(["git", "push", "-u", "origin", "HEAD"])
            print(f"  ↑ Vault synced to GitHub")
    except Exception as e:
        print(f"  [vault sync] skipped: {e}")


def write_research_note(
    topic: str,
    content: str,
    source_note: Optional[str] = None,
) -> Path:
    """
    Write an AI-generated research note to the Research PARA folder.

    Args:
        topic: Primary research topic (used as note title + filename)
        content: Full markdown body of the research note
        source_note: Optional trigger text or voice note ID for reference

    Returns:
        Path to the written note
    """
    vault = settings.VAULT_PATH
    folder = vault / "Research"
    folder.mkdir(parents=True, exist_ok=True)

    slug = _slugify(topic)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    note_path = folder / f"{timestamp}-{slug}.md"

    source_line = f"\n**Triggered by:** {source_note}" if source_note else ""

    note = f"""---
title: "{topic.replace('"', "'")}"
source_type: research_note
para_category: Research
tags:
  - research
  - ai-generated
generated_at: {datetime.now().strftime("%Y-%m-%d %H:%M")}
---

> AI-generated research note.{source_line}

{content}
"""

    note_path.write_text(note, encoding="utf-8")
    _git_sync(vault, f"research: {topic[:60]}")
    return note_path
