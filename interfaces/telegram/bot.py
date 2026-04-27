"""
Engram Telegram bot.
Handles voice messages, text queries, file ingestion, and research commands.
Only responds to TELEGRAM_ALLOWED_USER_ID — all other messages are silently ignored.
"""
import asyncio
import os
import tempfile

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config.settings import settings


# ── Auth guard ────────────────────────────────────────────────────────────────

def _allowed(update: Update) -> bool:
    if not settings.TELEGRAM_ALLOWED_USER_ID:
        return False
    return str(update.effective_user.id) == str(settings.TELEGRAM_ALLOWED_USER_ID)


async def _reject(update: Update) -> None:
    await update.message.reply_text("Unauthorized.")


# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    await update.message.reply_text(
        "Engram is running.\n\n"
        "Send a message or voice note to query your knowledge base.\n\n"
        "/help — show all commands"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    await update.message.reply_text(
        "*Engram Commands*\n\n"
        "Just send a message → RAG query\n"
        "Send a voice note → transcribe + RAG query\n"
        "Send a PDF or audio file → ingest it\n\n"
        "/add <url> — ingest a URL or YouTube link\n"
        "/search <query> — raw vector search (no LLM)\n"
        "/research <topic> — queue a background research task\n"
        "/list — recent documents in knowledge base\n"
        "/stats — knowledge base stats\n"
        "/help — this message",
        parse_mode="Markdown",
    )


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /add <url or file path>")
        return

    source = context.args[0]
    msg = await update.message.reply_text(f"Ingesting {source}...")

    try:
        from ingestion.pipeline import ingest
        result = await asyncio.to_thread(ingest, source)
        await msg.edit_text(
            f"Ingested: *{result['title']}*\n{result['chunks']} chunks",
            parse_mode="Markdown",
        )
    except Exception as e:
        await msg.edit_text(f"Failed: {e}")


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /search <query>")
        return

    query = " ".join(context.args)
    msg = await update.message.reply_text("Searching...")

    try:
        from core.vector_store import vector_store
        results = await asyncio.to_thread(vector_store.search, query, 5)
        if not results:
            await msg.edit_text("No results found.")
            return

        lines = []
        for i, r in enumerate(results, 1):
            title = r["metadata"].get("title", "Untitled")
            score = r["score"]
            snippet = r["text"][:120].strip().replace("\n", " ")
            lines.append(f"*[{i}] {title}* ({score:.2f})\n{snippet}...")

        await msg.edit_text("\n\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"Search failed: {e}")


async def cmd_research(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /research <topic or question>")
        return

    trigger = " ".join(context.args)
    msg = await update.message.reply_text(f"Queuing research: _{trigger}_...", parse_mode="Markdown")

    try:
        from research.scheduler import queue_research
        rid = await queue_research(trigger)
        await msg.edit_text(
            f"Research queued (ID: `{rid[:8]}`)\n"
            f"I'll notify you when it's done.",
            parse_mode="Markdown",
        )
    except Exception as e:
        await msg.edit_text(f"Failed to queue research: {e}")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return

    try:
        from db.connection import get_cursor
        with get_cursor() as cur:
            cur.execute(
                "SELECT title, source_type, ingested_at FROM documents "
                "ORDER BY ingested_at DESC LIMIT 15"
            )
            rows = cur.fetchall()

        if not rows:
            await update.message.reply_text("Knowledge base is empty.")
            return

        lines = []
        for r in rows:
            date = str(r["ingested_at"])[:10] if r["ingested_at"] else "—"
            lines.append(f"• {r['title']} _({r['source_type']}, {date})_")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return

    try:
        from core.vector_store import vector_store
        from db.connection import get_cursor

        total_chunks = await asyncio.to_thread(vector_store.count)
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM documents")
            total_docs = cur.fetchone()["n"]

        await update.message.reply_text(
            f"*Engram KB*\nDocuments: {total_docs}\nChunks: {total_chunks}",
            parse_mode="Markdown",
        )
    except Exception as e:
        await update.message.reply_text(f"Failed: {e}")


# ── Message handlers ──────────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return

    query = update.message.text.strip()
    msg = await update.message.reply_text("Thinking...")

    try:
        conversation_id = _conversation_id(update)
        from core.rag import ask
        result = await asyncio.to_thread(ask, query, conversation_id)
        reply = _format_answer(result)
        await msg.edit_text(reply, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"Error: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return

    msg = await update.message.reply_text("Transcribing voice note...")

    try:
        voice = update.message.voice or update.message.audio
        file = await context.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name

        await file.download_to_drive(tmp_path)

        from voice.mic import transcribe_file
        transcript = await asyncio.to_thread(transcribe_file, tmp_path)
        os.unlink(tmp_path)

        if not transcript:
            await msg.edit_text("Could not transcribe audio.")
            return

        await msg.edit_text(f"_{transcript}_\n\nThinking...", parse_mode="Markdown")

        conversation_id = _conversation_id(update)
        from core.rag import ask
        result = await asyncio.to_thread(ask, transcript, conversation_id)
        reply = f"_{transcript}_\n\n" + _format_answer(result)
        await msg.edit_text(reply, parse_mode="Markdown")

    except Exception as e:
        await msg.edit_text(f"Voice error: {e}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _allowed(update):
        return

    doc = update.message.document
    if not doc:
        return

    name = doc.file_name or "file"
    msg = await update.message.reply_text(f"Ingesting {name}...")

    try:
        file = await context.bot.get_file(doc.file_id)
        suffix = os.path.splitext(name)[1] or ".bin"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name

        await file.download_to_drive(tmp_path)

        from ingestion.pipeline import ingest
        result = await asyncio.to_thread(ingest, tmp_path)
        os.unlink(tmp_path)

        await msg.edit_text(
            f"Ingested: *{result['title']}*\n{result['chunks']} chunks",
            parse_mode="Markdown",
        )
    except Exception as e:
        await msg.edit_text(f"Ingest failed: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _conversation_id(update: Update) -> str:
    """Stable conversation ID per Telegram chat."""
    return f"telegram_{update.effective_chat.id}"


def _format_answer(result: dict) -> str:
    answer = result["answer"]
    citations = result.get("citations", [])
    if not citations:
        return answer

    sources = "\n".join(
        f"[{c['index']}] {c['title']} ({c['score']:.2f})"
        for c in citations
    )
    return f"{answer}\n\n*Sources:*\n{sources}"


# ── Entry point ───────────────────────────────────────────────────────────────

def run() -> None:
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in .env")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("research", cmd_research))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("stats", cmd_stats))

    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Engram bot is running. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)
