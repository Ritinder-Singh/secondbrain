"""
Conversation memory backed by PostgreSQL.
Stores all chat history — conversations are persistent across sessions.
"""
import uuid
from typing import Optional

from db.connection import get_cursor


def create_conversation(title: str = None) -> str:
    """Create a new conversation and return its ID."""
    cid = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (id, title) VALUES (%s, %s)",
            (cid, title or "New conversation"),
        )
    return cid


def save_message(
    conversation_id: str,
    role: str,
    content: str,
    metadata: dict = None,
) -> str:
    """Append a message to a conversation. Returns message ID."""
    mid = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO messages (id, conversation_id, role, content, metadata)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (mid, conversation_id, role, content, metadata or {}),
        )
    return mid


def get_history(conversation_id: str, limit: int = 10) -> list[dict]:
    """Return last N messages as OpenAI-format dicts {role, content}."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT role, content FROM messages
            WHERE conversation_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (conversation_id, limit),
        )
        rows = cur.fetchall()
    # Reverse so oldest message is first (chronological order for LLM context)
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def list_conversations(limit: int = 20) -> list[dict]:
    """Return recent conversations with their first message preview."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                c.id,
                c.title,
                c.created_at,
                (
                    SELECT content FROM messages
                    WHERE conversation_id = c.id
                    ORDER BY created_at
                    LIMIT 1
                ) AS first_message
            FROM conversations c
            ORDER BY c.created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()
