"""
Background research task scheduler.
Uses asyncio — no Celery/Redis needed for personal use.
Tasks are queued in postgres (research_notes table) and processed in background.
"""
import asyncio
import threading
import uuid
from datetime import datetime

from db.connection import get_cursor
from research.agent import run_research


async def queue_research(trigger_text: str) -> str:
    """
    Add a research task to the postgres queue.
    Returns the research_id — task runs in background.
    """
    rid = str(uuid.uuid4())
    title = f"Research {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO research_notes (id, title, trigger_text, content, status)
            VALUES (%s, %s, %s, %s, 'pending')
            """,
            (rid, title, trigger_text, ""),
        )
    print(f"[Scheduler] Queued research task {rid[:8]}")
    return rid


async def process_pending() -> None:
    """Pick up and run all pending research tasks."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, trigger_text FROM research_notes WHERE status = 'pending' LIMIT 5"
        )
        pending = cur.fetchall()

    for task in pending:
        print(f"[Scheduler] Processing {task['id'][:8]}...")
        try:
            await run_research(task["trigger_text"], research_id=task["id"])
        except Exception as e:
            print(f"[Scheduler] Error on {task['id'][:8]}: {e}")
            with get_cursor() as cur:
                cur.execute(
                    "UPDATE research_notes SET status = 'error' WHERE id = %s",
                    (task["id"],),
                )


async def run_forever(interval_seconds: int = 30) -> None:
    """Background loop that processes the research queue continuously."""
    print(f"[Scheduler] Running — checking every {interval_seconds}s")
    while True:
        try:
            await process_pending()
        except Exception as e:
            print(f"[Scheduler] Loop error: {e}")
        await asyncio.sleep(interval_seconds)


def start_background_scheduler() -> threading.Thread:
    """Start the scheduler in a background daemon thread."""
    def _run():
        asyncio.run(run_forever())

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def list_research_tasks(limit: int = 20) -> list[dict]:
    """Return recent research tasks with their status."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, title, status, trigger_text, vault_note, created_at, completed_at
            FROM research_notes
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()
