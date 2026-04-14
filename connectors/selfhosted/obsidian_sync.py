"""
Obsidian vault sync connector.
Walks VAULT_PATH and ingests all .md files into the knowledge base.
Skips Engram-generated notes (identified by 'source_type' frontmatter key)
to avoid recursive ingestion loops.
"""
import re
from pathlib import Path

from connectors.selfhosted.base import BaseConnector
from config.settings import settings

# Frontmatter key that marks a note as Engram-generated — skip these
_ENGRAM_MARKER = re.compile(r"^source_type:\s*\S+", re.MULTILINE)
_FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def _is_engram_note(text: str) -> bool:
    """Return True if the note was written by Engram (has source_type frontmatter)."""
    match = _FRONTMATTER.match(text)
    if match:
        return bool(_ENGRAM_MARKER.search(match.group(0)))
    return False


class ObsidianSyncConnector(BaseConnector):

    def fetch_documents(self) -> list[dict]:
        vault = settings.VAULT_PATH
        if not vault.exists():
            print(f"[ObsidianSync] Vault not found at {vault}")
            return []

        docs = []
        md_files = list(vault.rglob("*.md"))
        print(f"[ObsidianSync] Found {len(md_files)} .md files in {vault}")

        for path in md_files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if not text.strip():
                    continue
                if _is_engram_note(text):
                    continue  # skip notes Engram already wrote

                # Strip YAML frontmatter before indexing (keep body only)
                body = _FRONTMATTER.sub("", text).strip()
                if len(body) < 50:
                    continue  # skip near-empty notes

                docs.append({
                    "source":        str(path),
                    "para_category": _para_from_path(path, vault),
                    "tags":          ["obsidian", "vault"],
                })
            except Exception as e:
                print(f"  [warn] Skipped {path.name}: {e}")

        return docs

    def sync(self, dry_run: bool = False) -> dict:
        """Override to use ingest_parsed for cleaner vault note handling."""
        from ingestion.pipeline import ingest

        docs = self.fetch_documents()
        ingested, skipped, errors = 0, 0, []

        for doc in docs:
            if dry_run:
                print(f"  [dry-run] would ingest: {doc['source']}")
                skipped += 1
                continue
            try:
                ingest(
                    doc["source"],
                    para_category=doc.get("para_category", "Resources"),
                    tags=doc.get("tags", []),
                )
                ingested += 1
            except Exception as e:
                errors.append({"source": doc["source"], "error": str(e)})

        return {
            "connector": "ObsidianSync",
            "ingested":  ingested,
            "skipped":   skipped,
            "errors":    errors,
        }


def _para_from_path(path: Path, vault: Path) -> str:
    """Infer PARA category from the note's folder."""
    try:
        parts = path.relative_to(vault).parts
        if parts[0] in ("Projects", "Areas", "Resources", "Archive", "Research"):
            return parts[0]
    except ValueError:
        pass
    return "Resources"
