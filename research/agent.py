"""
Research Agent — Phase 3.

Triggered by a voice note or CLI command. Autonomously:
  1. Extracts topics + questions from the trigger text
  2. Searches the existing knowledge base (pgvector)
  3. Searches GitHub-sourced chunks specifically
  4. Web searches each topic via SearXNG / DuckDuckGo
  5. Synthesizes all findings into a structured Obsidian research note
  6. Ingests the research note into the KB (recursive knowledge growth)
  7. Sends a push notification via ntfy.sh when complete

"Away from home" feature: trigger research on the go,
come home to a ready-to-use note in your vault.
"""
import asyncio
import json
import re
import uuid

from config.settings import settings
from core.rag import ask
from core.llm import chat
from db.connection import get_cursor
from research.web_search import web_search
from research.synthesizer import synthesize
from vault.writer import write_research_note


async def run_research(trigger_text: str, research_id: str = None) -> dict:
    """
    Run the full research pipeline asynchronously.

    Args:
        trigger_text: The voice note transcript or typed query
        research_id: Optional — used when resuming a queued task

    Returns:
        {research_id, topics, vault_note, summary}
    """
    research_id = research_id or str(uuid.uuid4())
    _update_status(research_id, "processing")
    print(f"\n[Research] Starting: {trigger_text[:80]}...")

    # 1. Extract intent
    intent = await asyncio.to_thread(_extract_intent, trigger_text)
    print(f"[Research] Topics  : {intent['topics']}")
    print(f"[Research] Questions: {intent['questions']}")

    # 2. Search own knowledge base
    print("[Research] Searching knowledge base...")
    kb_results = await asyncio.to_thread(ask, trigger_text, None, None, False, 8)

    # 3. Web search per topic (top 3 topics, up to 6 results each)
    print("[Research] Running web searches...")
    web_results: dict[str, list] = {}
    for topic in intent["topics"][:3]:
        results = await asyncio.to_thread(web_search, topic, 6)
        web_results[topic] = results
        print(f"  '{topic}' → {len(results)} results")

    # 4. Search GitHub-sourced chunks specifically
    print("[Research] Searching GitHub knowledge...")
    github_results = await asyncio.to_thread(
        _search_github_knowledge, " ".join(intent["topics"])
    )

    # 5. Synthesize
    print("[Research] Synthesizing...")
    content = await asyncio.to_thread(
        synthesize, trigger_text, intent, kb_results, web_results, github_results
    )

    # 6. Write to Obsidian vault
    primary_topic = intent["topics"][0] if intent["topics"] else "Research"
    note_path = write_research_note(
        topic=primary_topic,
        content=content,
        source_note=trigger_text[:200],
    )
    print(f"[Research] Note written: {note_path}")

    # 7. Ingest the research note into the KB
    from ingestion.pipeline import ingest
    await asyncio.to_thread(
        ingest, str(note_path), "Research", ["research", "ai-generated"]
    )

    _update_status(research_id, "complete", str(note_path))

    result = {
        "research_id": research_id,
        "topics":      intent["topics"],
        "vault_note":  str(note_path),
        "summary":     content[:500] + "..." if len(content) > 500 else content,
    }

    # 8. Push notification via ntfy.sh
    await asyncio.to_thread(_notify, primary_topic, str(note_path))

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_intent(text: str) -> dict:
    """Use LLM to extract research topics and questions from trigger text."""
    response = chat([{
        "role": "user",
        "content": (
            "Extract research intent from this text. Reply ONLY with valid JSON:\n"
            '{"topics": ["topic1", "topic2"], '
            '"questions": ["question1", "question2"], '
            '"intent": "brief description of what to research"}\n\n'
            f"Text: {text}"
        ),
    }])
    clean = re.sub(r"```json|```", "", response).strip()
    try:
        return json.loads(clean)
    except Exception:
        return {"topics": [text[:50]], "questions": [text], "intent": text}


def _search_github_knowledge(query: str) -> list[dict]:
    """Search only GitHub-sourced chunks in the knowledge base."""
    from core.vector_store import vector_store
    return vector_store.search(
        query,
        n_results=5,
        filter_metadata={"source_type": "github"},
    )


def _update_status(research_id: str, status: str, vault_note: str = None) -> None:
    """Update research task status in postgres."""
    try:
        with get_cursor() as cur:
            if status == "processing":
                cur.execute(
                    """
                    INSERT INTO research_notes (id, title, trigger_text, content, status)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status
                    """,
                    (research_id, f"Research {research_id[:8]}", "", "", status),
                )
            else:
                cur.execute(
                    """
                    UPDATE research_notes
                    SET status = %s, vault_note = %s, completed_at = NOW()
                    WHERE id = %s
                    """,
                    (status, vault_note, research_id),
                )
    except Exception as e:
        print(f"[Research] Status update failed: {e}")


def _notify(topic: str, note_path: str) -> None:
    """Send push notification via ntfy.sh when research is complete."""
    if not settings.NTFY_TOPIC:
        return
    try:
        import requests
        requests.post(
            f"{settings.NTFY_URL}/{settings.NTFY_TOPIC}",
            data=f"Research complete: {topic}".encode("utf-8"),
            headers={
                "Title": "Engram Research Done",
                "Priority": "default",
                "Tags": "brain,white_check_mark",
            },
            timeout=5,
        )
        print(f"[Research] Notification sent to ntfy.sh/{settings.NTFY_TOPIC}")
    except Exception as e:
        print(f"[Research] ntfy notification failed: {e}")
