# Engram — Full Project Spec for Claude Code

> Personal AI knowledge assistant. Fully local, privacy-first.
> Everything you save becomes searchable and chattable via a local LLM.

---

## Context & Decisions Already Made

This is a personal developer tool / AI-ML portfolio project. Key decisions:

- **LLM runtime**: Ollama (local, primary) with Groq API (cloud fallback, free tier)
- **Embeddings**: `nomic-embed-text` via Ollama — always local, never sent to cloud
- **Vector store**: **PostgreSQL + pgvector** (replaces ChromaDB — more production-appropriate, better resume story, self-hostable)
- **Knowledge storage**: Obsidian vault (plain markdown, PARA structure, wikilinks)
- **Primary interface**: CLI (developer-first), then Telegram bot for remote use
- **Voice**: faster-whisper (transcription, local), Piper TTS (speech output, local)
- **Hardware**: Laptop with i7-1255U, 32GB RAM — Llama 3.1 8B is the primary model
- **Target models**: `llama3.1:8b` (chat), `nomic-embed-text` (embeddings)
- **TODO for later** (do NOT implement): Autonomous research agent as a standalone product/SaaS

---

## Project Name Options (not decided yet)
Engram | Exo | Recall | Etch — use `Engram` as the working name in all code.

---

## Full Directory Structure

```
engram/
├── config/
│   ├── __init__.py
│   └── settings.py                  # Pydantic settings, all config via .env
│
├── core/
│   ├── __init__.py
│   ├── llm.py                       # Ollama + Groq unified OpenAI-compatible client
│   ├── rag.py                       # RAG pipeline: retrieve → augment → generate
│   ├── vector_store.py              # pgvector wrapper (replaces ChromaDB)
│   └── memory.py                   # Conversation memory (stored in postgres)
│
├── db/
│   ├── __init__.py
│   ├── connection.py                # PostgreSQL connection pool (psycopg2)
│   ├── migrations/
│   │   └── 001_initial.sql          # Schema: documents, chunks, conversations, memory
│   └── models.py                   # Dataclass models mirroring DB tables
│
├── ingestion/
│   ├── __init__.py
│   ├── pipeline.py                  # Orchestrates: parse → chunk → embed → store + vault
│   ├── parsers/
│   │   ├── __init__.py
│   │   └── content.py               # PDF, web, YouTube, audio, text parsers
│   └── chunkers/
│       ├── __init__.py
│       └── strategies.py            # fixed, sentence, recursive, code-aware (Tree-sitter)
│
├── connectors/
│   ├── __init__.py
│   ├── registry.py                  # Central connector registry + sync runner
│   ├── github/
│   │   ├── __init__.py
│   │   └── ingest.py                # Repos (function-level chunked), issues, PRs
│   └── selfhosted/
│       ├── __init__.py
│       ├── base.py                  # BaseConnector abstract class (adapter pattern)
│       ├── nextcloud.py             # WebDAV ingestion
│       ├── bookstack.py             # REST API ingestion
│       └── obsidian_sync.py         # Sync existing vault notes → vector store
│
├── research/
│   ├── __init__.py
│   ├── agent.py                     # Async research pipeline (Phase 3)
│   ├── web_search.py                # DuckDuckGo / SearXNG search
│   ├── synthesizer.py               # Multi-source synthesis → structured note
│   └── scheduler.py                 # Background task runner (asyncio)
│
├── voice/
│   ├── __init__.py
│   ├── mic.py                       # Mic recording + Whisper transcription
│   ├── tts.py                       # Piper TTS / pyttsx3 fallback
│   └── assistant.py                 # Hands-free voice Q&A loop
│
├── vault/
│   ├── __init__.py
│   └── writer.py                    # Obsidian markdown note writer (PARA structure)
│
├── interfaces/
│   ├── __init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   └── __main__.py              # Full CLI (all commands)
│   ├── telegram/
│   │   ├── __init__.py
│   │   └── bot.py                   # Telegram bot (voice, text, files, commands)
│   └── web/
│       ├── __init__.py
│       ├── app.py                   # FastAPI app (Phase 4)
│       ├── routes/
│       │   ├── chat.py
│       │   ├── ingest.py
│       │   └── search.py
│       └── static/                  # Simple React or plain HTML frontend
│           ├── index.html
│           └── app.jsx
│
├── search/
│   ├── __init__.py
│   ├── hybrid.py                    # BM25 + pgvector cosine hybrid search (Phase 4)
│   └── reranker.py                  # FlashRank cross-encoder re-ranking (Phase 4)
│
├── tests/
│   ├── test_ingestion.py
│   ├── test_rag.py
│   ├── test_vector_store.py
│   └── test_chunkers.py
│
├── scripts/
│   ├── setup_db.py                  # Run migrations, create extensions
│   └── benchmark.py                 # Compare Q4 vs Q8 models, chunking strategies
│
├── docker-compose.yml               # Postgres + pgvector
├── .env.example
├── requirements.txt
└── README.md
```

---

## Database Schema

### `db/migrations/001_initial.sql`

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table: one row per ingested source
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,              -- uuid5 of source URL or file path
    title       TEXT NOT NULL,
    source_type TEXT NOT NULL,                 -- pdf | article | youtube | github | voice_note | etc.
    source_url  TEXT,
    file_path   TEXT,
    para_category TEXT DEFAULT 'Resources',    -- Projects | Areas | Resources | Archive
    tags        TEXT[],
    metadata    JSONB DEFAULT '{}',
    vault_note  TEXT,                          -- path to Obsidian note
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    summary     TEXT                           -- auto-generated summary (Phase 4)
);

-- Chunks table: one row per text chunk with its embedding
CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,              -- doc_id + __chunk_N
    doc_id      TEXT REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(768),                   -- nomic-embed-text = 768 dims
    metadata    JSONB DEFAULT '{}'
);

-- HNSW index for fast approximate nearest-neighbour search
-- Much faster than exact search at scale
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text search index (for BM25 hybrid search, Phase 4)
CREATE INDEX IF NOT EXISTS chunks_content_fts
    ON chunks USING gin(to_tsvector('english', content));

-- Conversations table: stores chat sessions
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    title       TEXT,                          -- auto-generated from first message
    metadata    JSONB DEFAULT '{}'
);

-- Messages table: conversation history
CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,             -- user | assistant | system
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'         -- citations, chunk_ids, etc.
);

-- Research notes: AI-generated research from voice notes / tasks (Phase 3)
CREATE TABLE IF NOT EXISTS research_notes (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    title           TEXT NOT NULL,
    trigger_text    TEXT,                      -- the voice note or message that triggered this
    content         TEXT NOT NULL,             -- full markdown research note
    vault_note      TEXT,                      -- path in Obsidian vault
    status          TEXT DEFAULT 'pending',    -- pending | processing | complete | error
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}'
);
```

---

## Core Module Implementations

### `config/settings.py`

```python
from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Literal


class Settings(BaseSettings):

    APP_NAME: str = "Engram"
    VERSION: str = "0.1.0"

    # ── LLM ───────────────────────────────────────────────────────────────
    LLM_PROVIDER: Literal["ollama", "groq"] = "ollama"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    # ── PostgreSQL + pgvector ─────────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "engram"
    POSTGRES_USER: str = "engram"
    POSTGRES_PASSWORD: str = "engram"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ── Obsidian Vault ────────────────────────────────────────────────────
    VAULT_PATH: Path = Path("~/Documents/Engram-Vault").expanduser()

    # ── Whisper ───────────────────────────────────────────────────────────
    WHISPER_MODEL: str = "base"          # tiny | base | small | medium | large
    WHISPER_DEVICE: str = "cpu"

    # ── Chunking ──────────────────────────────────────────────────────────
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    CHUNK_STRATEGY: Literal["fixed", "sentence", "recursive", "code"] = "recursive"

    # ── Embedding dims — must match your model ────────────────────────────
    # nomic-embed-text = 768, mxbai-embed-large = 1024, all-minilm = 384
    EMBED_DIMS: int = 768

    # ── GitHub ────────────────────────────────────────────────────────────
    GITHUB_TOKEN: str = ""
    GITHUB_USERNAME: str = ""

    # ── Telegram ──────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ALLOWED_USER_ID: str = ""

    # ── Self-hosted connectors ────────────────────────────────────────────
    NEXTCLOUD_URL: str = ""
    NEXTCLOUD_USERNAME: str = ""
    NEXTCLOUD_PASSWORD: str = ""
    NEXTCLOUD_FOLDER: str = "/"

    BOOKSTACK_URL: str = ""
    BOOKSTACK_TOKEN_ID: str = ""
    BOOKSTACK_TOKEN_SECRET: str = ""

    # ── Web Search (Phase 3) ──────────────────────────────────────────────
    SEARCH_PROVIDER: Literal["duckduckgo", "searxng"] = "duckduckgo"
    SEARXNG_URL: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
```

---

### `db/connection.py`

```python
"""
PostgreSQL connection pool using psycopg2.
pgvector registers its types on connection.
"""
import psycopg2
import psycopg2.pool
from psycopg2.extras import RealDictCursor
from pgvector.psycopg2 import register_vector
from contextlib import contextmanager
from config.settings import settings

_pool = None


def get_pool():
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=settings.DATABASE_URL,
        )
    return _pool


@contextmanager
def get_conn():
    """Context manager that checks out and returns a connection from the pool."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        register_vector(conn)        # register pgvector types
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def get_cursor(cursor_factory=RealDictCursor):
    """Convenience: context manager yielding a cursor."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=cursor_factory) as cur:
            yield cur
```

---

### `db/models.py`

```python
"""Dataclass mirrors of DB tables for type safety."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Document:
    id: str
    title: str
    source_type: str
    source_url: str = ""
    file_path: str = ""
    para_category: str = "Resources"
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    vault_note: str = ""
    ingested_at: Optional[datetime] = None
    summary: str = ""


@dataclass
class Chunk:
    id: str
    doc_id: str
    chunk_index: int
    content: str
    embedding: list          # list[float], 768 dims
    metadata: dict = field(default_factory=dict)


@dataclass
class Message:
    id: str
    conversation_id: str
    role: str                # user | assistant
    content: str
    created_at: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)
```

---

### `core/vector_store.py`

```python
"""
pgvector-backed vector store.
Replaces ChromaDB. Uses HNSW index for fast ANN search.
Cosine similarity (inner product on normalized vectors).
"""
import numpy as np
from db.connection import get_cursor
from core.llm import embed
from config.settings import settings
from typing import Optional


class VectorStore:

    def add(self, doc_id: str, chunk_id: str, chunk_index: int,
            text: str, metadata: dict = None) -> None:
        """Embed one chunk and insert into postgres."""
        vector = embed(text)
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO chunks (id, doc_id, chunk_index, content, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                    SET content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata
                """,
                (chunk_id, doc_id, chunk_index, text, vector, metadata or {}),
            )

    def add_batch(self, chunks: list[dict]) -> None:
        """
        Bulk insert chunks. Each chunk:
        {"id": str, "doc_id": str, "chunk_index": int, "text": str, "metadata": dict}
        """
        rows = []
        for chunk in chunks:
            vector = embed(chunk["text"])
            rows.append((
                chunk["id"],
                chunk["doc_id"],
                chunk["chunk_index"],
                chunk["text"],
                vector,
                chunk.get("metadata", {}),
            ))

        with get_cursor() as cur:
            # Use executemany for batch insert
            cur.executemany(
                """
                INSERT INTO chunks (id, doc_id, chunk_index, content, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                    SET content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata
                """,
                rows,
            )

    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[dict] = None,
    ) -> list[dict]:
        """
        Semantic search using pgvector cosine similarity.
        Returns list of {"text", "metadata", "score", "doc_id"}
        Optionally filter by metadata JSONB keys.
        """
        vector = embed(query)

        # Build optional metadata filter
        where_clause = ""
        params = [vector, n_results]

        if filter_metadata:
            conditions = []
            for key, value in filter_metadata.items():
                conditions.append(f"metadata->>'{key}' = %s")
                params.insert(-1, str(value))
            where_clause = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT
                id,
                doc_id,
                content,
                metadata,
                1 - (embedding <=> %s::vector) AS score
            FROM chunks
            {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        # Adjust params: vector appears twice (score calc + ORDER BY)
        params_final = [vector] + (
            [v for k, v in filter_metadata.items()] if filter_metadata else []
        ) + [vector, n_results]

        with get_cursor() as cur:
            cur.execute(sql, params_final)
            rows = cur.fetchall()

        return [
            {
                "text": row["content"],
                "metadata": row["metadata"],
                "score": float(row["score"]),
                "doc_id": row["doc_id"],
                "chunk_id": row["id"],
            }
            for row in rows
        ]

    def delete_document(self, doc_id: str) -> None:
        """Delete all chunks for a document (cascades from documents table too)."""
        with get_cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE doc_id = %s", (doc_id,))

    def count(self) -> int:
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) as n FROM chunks")
            return cur.fetchone()["n"]

    def upsert_document(self, doc: dict) -> None:
        """Insert or update a document record."""
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents
                    (id, title, source_type, source_url, file_path,
                     para_category, tags, metadata, vault_note)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    metadata = EXCLUDED.metadata,
                    vault_note = EXCLUDED.vault_note
                """,
                (
                    doc["id"], doc["title"], doc["source_type"],
                    doc.get("source_url", ""), doc.get("file_path", ""),
                    doc.get("para_category", "Resources"),
                    doc.get("tags", []),
                    doc.get("metadata", {}),
                    doc.get("vault_note", ""),
                ),
            )


vector_store = VectorStore()
```

---

### `core/llm.py`

```python
"""
Unified LLM client — Ollama (local) or Groq (cloud fallback).
Single config flag switches providers: LLM_PROVIDER=groq in .env
Both use the OpenAI-compatible API so code is identical for both.
Embeddings ALWAYS use local Ollama regardless of LLM_PROVIDER.
"""
from openai import OpenAI
from typing import Generator
from config.settings import settings


def get_client() -> OpenAI:
    if settings.LLM_PROVIDER == "groq":
        return OpenAI(api_key=settings.GROQ_API_KEY, base_url=settings.GROQ_BASE_URL)
    return OpenAI(api_key="ollama", base_url=f"{settings.OLLAMA_BASE_URL}/v1")


def get_model() -> str:
    return settings.GROQ_MODEL if settings.LLM_PROVIDER == "groq" else settings.OLLAMA_MODEL


def chat(messages: list[dict], stream: bool = False) -> str | Generator:
    client = get_client()
    response = client.chat.completions.create(
        model=get_model(), messages=messages, stream=stream
    )
    if stream:
        def _gen():
            for chunk in response:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        return _gen()
    return response.choices[0].message.content


def embed(text: str) -> list[float]:
    """Always local — embeddings never leave the machine."""
    client = OpenAI(api_key="ollama", base_url=f"{settings.OLLAMA_BASE_URL}/v1")
    response = client.embeddings.create(model=settings.OLLAMA_EMBED_MODEL, input=text)
    return response.data[0].embedding
```

---

### `core/rag.py`

```python
"""
RAG Pipeline: query → retrieve → format context → generate answer.
Supports streaming, conversation history, and metadata filtering.
"""
from core.vector_store import vector_store
from core.llm import chat
from core.memory import save_message, get_history
from typing import Optional, Generator

SYSTEM_PROMPT = """You are Engram, a personal AI knowledge assistant for a software developer.
You answer questions using the developer's own saved knowledge — their notes, code, articles,
GitHub repos, and research. Always cite your sources using [N] notation matching the context
provided. Be concise and technical. If context is insufficient, say so — never hallucinate."""


def ask(
    query: str,
    conversation_id: Optional[str] = None,
    filter_metadata: Optional[dict] = None,
    stream: bool = False,
    n_results: int = 5,
    use_hybrid: bool = False,        # Phase 4: BM25 + semantic
    rerank: bool = False,            # Phase 4: cross-encoder reranking
) -> dict | Generator:

    # 1. Retrieve
    if use_hybrid:
        from search.hybrid import hybrid_search
        chunks = hybrid_search(query, n_results=n_results)
    else:
        chunks = vector_store.search(query, n_results=n_results,
                                     filter_metadata=filter_metadata)

    # 2. Optional re-ranking (Phase 4)
    if rerank and chunks:
        from search.reranker import rerank_chunks
        chunks = rerank_chunks(query, chunks)

    context = _format_context(chunks)
    citations = _build_citations(chunks)

    # 3. Build messages with optional conversation history
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if conversation_id:
        messages.extend(get_history(conversation_id, limit=10))
    messages.append({"role": "user", "content": f"Context:\n\n{context}\n\nQuestion: {query}"})

    # 4. Generate
    answer = chat(messages, stream=stream)

    if stream:
        return answer

    # 5. Persist to conversation memory
    if conversation_id:
        save_message(conversation_id, "user", query)
        save_message(conversation_id, "assistant", answer,
                     metadata={"citations": citations})

    return {"answer": answer, "citations": citations, "chunks": chunks}


def _format_context(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant context found."
    parts = []
    for i, c in enumerate(chunks, 1):
        meta = c["metadata"]
        src = meta.get("title") or meta.get("source_url") or "Unknown"
        parts.append(f"[{i}] {src}\n{c['text']}")
    return "\n\n---\n\n".join(parts)


def _build_citations(chunks: list[dict]) -> list[dict]:
    return [
        {
            "index": i,
            "title": c["metadata"].get("title", "Untitled"),
            "source_type": c["metadata"].get("source_type", "unknown"),
            "source_url": c["metadata"].get("source_url", ""),
            "file_path": c["metadata"].get("file_path", ""),
            "score": c.get("score", 0),
        }
        for i, c in enumerate(chunks, 1)
    ]
```

---

### `core/memory.py`

```python
"""
Conversation memory backed by PostgreSQL.
Stores all chat history — conversations are persistent across sessions.
"""
import uuid
from db.connection import get_cursor
from typing import Optional


def create_conversation(title: str = None) -> str:
    """Create a new conversation, return its ID."""
    cid = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO conversations (id, title) VALUES (%s, %s)",
            (cid, title or "New conversation"),
        )
    return cid


def save_message(conversation_id: str, role: str, content: str,
                 metadata: dict = None) -> str:
    """Append a message to a conversation."""
    mid = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO messages (id, conversation_id, role, content, metadata)
               VALUES (%s, %s, %s, %s, %s)""",
            (mid, conversation_id, role, content, metadata or {}),
        )
    return mid


def get_history(conversation_id: str, limit: int = 10) -> list[dict]:
    """Return last N messages as OpenAI-format dicts."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT role, content FROM messages
               WHERE conversation_id = %s
               ORDER BY created_at DESC LIMIT %s""",
            (conversation_id, limit),
        )
        rows = cur.fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def list_conversations(limit: int = 20) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """SELECT id, title, created_at,
                      (SELECT content FROM messages WHERE conversation_id = c.id
                       ORDER BY created_at LIMIT 1) as first_message
               FROM conversations c
               ORDER BY created_at DESC LIMIT %s""",
            (limit,),
        )
        return cur.fetchall()
```

---

### `ingestion/chunkers/strategies.py`

```python
"""
Four chunking strategies. Strategy is auto-selected based on content type
but can be overridden. Chunking quality directly affects retrieval quality.

Key insight for interviews: pure character chunking destroys sentence
boundaries; recursive splitting preserves semantic units; code needs
function-level boundaries to be useful.
"""
import re
from config.settings import settings


def chunk_fixed(text: str, size: int = None, overlap: int = None) -> list[str]:
    size = size or settings.CHUNK_SIZE
    overlap = overlap or settings.CHUNK_OVERLAP
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start:start + size].strip())
        start += size - overlap
    return [c for c in chunks if c]


def chunk_sentence(text: str, max_size: int = None) -> list[str]:
    max_size = max_size or settings.CHUNK_SIZE
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) > max_size and current:
            chunks.append(current.strip())
            current = s
        else:
            current += " " + s
    if current.strip():
        chunks.append(current.strip())
    return chunks


def chunk_recursive(text: str, size: int = None, overlap: int = None) -> list[str]:
    """
    Split on natural boundaries: paragraphs → sentences → words → chars.
    Best general-purpose strategy.
    """
    size = size or settings.CHUNK_SIZE
    overlap = overlap or settings.CHUNK_OVERLAP
    separators = ["\n\n", "\n", ". ", " ", ""]

    def _split(text, seps):
        if not seps:
            return [text]
        sep = seps[0]
        splits = text.split(sep) if sep else list(text)
        chunks, current = [], ""
        for split in splits:
            candidate = current + (sep if current else "") + split
            if len(candidate) <= size:
                current = candidate
            else:
                if current:
                    chunks.append(current.strip())
                chunks.extend(_split(split, seps[1:]) if len(split) > size else [split])
                current = ""
        if current.strip():
            chunks.append(current.strip())
        return chunks

    raw = _split(text, separators)
    if not overlap:
        return raw
    overlapped = []
    for i, chunk in enumerate(raw):
        if i > 0:
            chunk = raw[i - 1][-overlap:] + " " + chunk
        overlapped.append(chunk.strip())
    return overlapped


def chunk_code(text: str, language: str = "python") -> list[str]:
    """
    Split code at function/class boundaries.
    Falls back to recursive for large functions.
    TODO: Replace regex with Tree-sitter for production-grade AST parsing.
    """
    patterns = {
        "python": r'(?=\n(?:def |class |async def ))',
        "javascript": r'(?=\n(?:function |const |class |export |async ))',
        "typescript": r'(?=\n(?:function |const |class |export |interface |type ))',
        "go": r'(?=\nfunc )',
        "rust": r'(?=\nfn |impl )',
    }
    pattern = patterns.get(language)
    if not pattern:
        return chunk_recursive(text)

    splits = re.split(pattern, text)
    chunks = []
    for split in splits:
        if len(split) <= settings.CHUNK_SIZE:
            chunks.append(split.strip())
        else:
            chunks.extend(chunk_recursive(split))
    return [c for c in chunks if c]


def get_chunks(text: str, strategy: str = None, **kwargs) -> list[str]:
    strategy = strategy or settings.CHUNK_STRATEGY
    return {
        "fixed": chunk_fixed,
        "sentence": chunk_sentence,
        "recursive": chunk_recursive,
        "code": chunk_code,
    }.get(strategy, chunk_recursive)(text, **kwargs)
```

---

### `ingestion/parsers/content.py`

```python
"""
Content parsers. Each returns a standard dict:
{title, text, source_type, source_url, file_path, metadata}
Single parse(source) function auto-detects type.
"""
import re
from pathlib import Path
from datetime import datetime


def parse_pdf(path) -> dict:
    import fitz
    doc = fitz.open(str(path))
    pages = [{"page": i+1, "text": p.get_text()} for i, p in enumerate(doc)]
    return {
        "title": doc.metadata.get("title") or Path(path).stem,
        "text": "\n\n".join(p["text"] for p in pages),
        "source_type": "pdf",
        "source_url": None,
        "file_path": str(Path(path).resolve()),
        "metadata": {"author": doc.metadata.get("author",""), "pages": len(doc)},
    }


def parse_url(url: str) -> dict:
    import trafilatura
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise ValueError(f"Could not fetch: {url}")
    text = trafilatura.extract(downloaded, include_tables=True) or ""
    meta = trafilatura.extract_metadata(downloaded)
    return {
        "title": meta.title if meta else url.split("/")[-1],
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
    import yt_dlp, tempfile, os
    from faster_whisper import WhisperModel
    from config.settings import settings

    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")
        with yt_dlp.YoutubeDL({
            "format": "bestaudio/best", "outtmpl": audio_path,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
            "quiet": True,
        }) as ydl:
            ydl.download([url])

        model = WhisperModel(settings.WHISPER_MODEL, device=settings.WHISPER_DEVICE)
        segments, _ = model.transcribe(audio_path, beam_size=5)
        transcript = " ".join(s.text for s in segments)

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
        },
    }


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
        "metadata": {"duration": info.duration, "language": info.language},
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


def parse(source: str) -> dict:
    """Auto-detect and parse any supported source."""
    if source.startswith("http"):
        if "youtube.com" in source or "youtu.be" in source:
            return parse_youtube(source)
        return parse_url(source)
    path = Path(source)
    return {
        ".pdf": parse_pdf,
        ".md": parse_text_file, ".txt": parse_text_file,
        ".mp3": parse_audio_file, ".wav": parse_audio_file,
        ".m4a": parse_audio_file, ".ogg": parse_audio_file,
    }.get(path.suffix.lower(), lambda p: (_ for _ in ()).throw(
        ValueError(f"Unsupported: {path.suffix}"))
    )(path)
```

---

### `ingestion/pipeline.py`

```python
"""
Ingestion pipeline: parse → chunk → embed → postgres + obsidian vault.
Single ingest(source) call handles everything.
"""
import uuid
from datetime import datetime
from pathlib import Path
from ingestion.parsers.content import parse
from ingestion.chunkers.strategies import get_chunks
from core.vector_store import vector_store
from vault.writer import write_source_note


def ingest(source: str, para_category: str = "Resources", tags: list = None) -> dict:
    print(f"[1/4] Parsing: {source}")
    parsed = parse(source)

    print(f"[2/4] Chunking '{parsed['title']}' ({len(parsed['text'])} chars)")
    strategy = {
        "pdf": "recursive", "article": "sentence", "youtube": "sentence",
        "audio": "sentence", "github": "code", "markdown": "recursive",
    }.get(parsed["source_type"], "recursive")

    chunks = [c for c in get_chunks(parsed["text"], strategy=strategy) if len(c.strip()) > 30]
    print(f"       {len(chunks)} chunks")

    doc_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        parsed.get("source_url") or parsed.get("file_path") or parsed["title"]
    ))

    print(f"[3/4] Embedding + storing in pgvector...")
    vector_store.upsert_document({
        "id": doc_id, "title": parsed["title"],
        "source_type": parsed["source_type"],
        "source_url": parsed.get("source_url") or "",
        "file_path": parsed.get("file_path") or "",
        "para_category": para_category,
        "tags": tags or [],
        "metadata": parsed.get("metadata", {}),
    })

    chunk_records = [
        {
            "id": f"{doc_id}__chunk_{i}",
            "doc_id": doc_id,
            "chunk_index": i,
            "text": text,
            "metadata": {
                "title": parsed["title"],
                "source_type": parsed["source_type"],
                "source_url": parsed.get("source_url") or "",
                "file_path": parsed.get("file_path") or "",
                "para_category": para_category,
                "tags": ",".join(tags or []),
                "ingested_at": datetime.now().isoformat(),
            },
        }
        for i, text in enumerate(chunks)
    ]
    vector_store.add_batch(chunk_records)

    print(f"[4/4] Writing Obsidian note...")
    note_path = write_source_note(parsed, para_category=para_category, tags=tags)

    # Update vault_note path in documents table
    vector_store.upsert_document({
        "id": doc_id, "title": parsed["title"],
        "source_type": parsed["source_type"],
        "source_url": parsed.get("source_url") or "",
        "vault_note": str(note_path),
        "para_category": para_category,
        "tags": tags or [],
        "metadata": parsed.get("metadata", {}),
    })

    print(f"\n✓ '{parsed['title']}' — {len(chunks)} chunks\n")
    return {
        "title": parsed["title"],
        "source_type": parsed["source_type"],
        "chunks": len(chunks),
        "doc_id": doc_id,
        "vault_note": str(note_path),
    }
```

---

## Phase 3 — Research Agent

### `research/web_search.py`

```python
"""
Web search provider. DuckDuckGo requires no API key.
SearXNG is a self-hostable meta-search engine (preferred for privacy).
"""
from config.settings import settings


def web_search(query: str, max_results: int = 8) -> list[dict]:
    """Returns list of {"title", "url", "snippet"}"""
    if settings.SEARCH_PROVIDER == "searxng" and settings.SEARXNG_URL:
        return _searxng_search(query, max_results)
    return _ddg_search(query, max_results)


def _ddg_search(query: str, n: int) -> list[dict]:
    from duckduckgo_search import DDGS
    results = []
    with DDGS() as ddg:
        for r in ddg.text(query, max_results=n):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            })
    return results


def _searxng_search(query: str, n: int) -> list[dict]:
    import requests
    resp = requests.get(
        f"{settings.SEARXNG_URL}/search",
        params={"q": query, "format": "json", "categories": "general"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {"title": r.get("title",""), "url": r.get("url",""), "snippet": r.get("content","")}
        for r in data.get("results", [])[:n]
    ]
```

---

### `research/agent.py`

```python
"""
Research Agent — Phase 3.

Triggered by a voice note or Telegram message.
Autonomously:
  1. Extracts topics + questions from the input
  2. Searches existing knowledge base (pgvector)
  3. Searches GitHub repos for related code
  4. Performs web searches for external context
  5. Synthesizes all findings into a structured Obsidian research note
  6. Notifies via Telegram when complete

This is the "away from home" feature: send a voice note on the go,
come home to a ready-to-use research note in your vault.

NOTE: The full autonomous research product concept is a TODO for later.
This implementation is scoped to personal use only.
"""
import asyncio
import uuid
from datetime import datetime
from config.settings import settings
from core.rag import ask
from core.llm import chat
from research.web_search import web_search
from vault.writer import write_research_note
from db.connection import get_cursor


async def run_research(trigger_text: str, research_id: str = None) -> dict:
    """
    Full async research pipeline from a trigger text (voice note transcript
    or Telegram message).

    Returns the research note path and summary.
    """
    research_id = research_id or str(uuid.uuid4())
    _update_status(research_id, "processing")

    print(f"[Research] Starting: {trigger_text[:80]}...")

    # 1. Extract research intent from trigger text
    intent = await asyncio.to_thread(_extract_intent, trigger_text)
    print(f"[Research] Topics: {intent['topics']}")
    print(f"[Research] Questions: {intent['questions']}")

    # 2. Search existing knowledge base
    print("[Research] Searching knowledge base...")
    kb_results = await asyncio.to_thread(
        ask, trigger_text, n_results=8
    )

    # 3. Web searches for each topic
    print("[Research] Running web searches...")
    web_results = {}
    for topic in intent["topics"][:3]:   # limit to top 3 topics
        results = await asyncio.to_thread(web_search, topic, 5)
        web_results[topic] = results

    # 4. Check GitHub repos for related code
    print("[Research] Checking GitHub repos...")
    github_results = await asyncio.to_thread(
        _search_github_knowledge, " ".join(intent["topics"])
    )

    # 5. Synthesize everything
    print("[Research] Synthesizing...")
    synthesis = await asyncio.to_thread(
        _synthesize, trigger_text, intent, kb_results, web_results, github_results
    )

    # 6. Write to Obsidian vault
    note_path = write_research_note(
        topic=intent["topics"][0] if intent["topics"] else "Research",
        content=synthesis,
        source_note=research_id,
    )

    # 7. Ingest the research note itself
    from ingestion.pipeline import ingest
    await asyncio.to_thread(
        ingest, str(note_path), "Research", ["research", "ai-generated"]
    )

    _update_status(research_id, "complete", str(note_path))

    result = {
        "research_id": research_id,
        "topics": intent["topics"],
        "vault_note": str(note_path),
        "summary": synthesis[:500] + "..." if len(synthesis) > 500 else synthesis,
    }

    # 8. Notify via Telegram if configured
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_ALLOWED_USER_ID:
        await asyncio.to_thread(_notify_telegram, result)

    return result


def _extract_intent(text: str) -> dict:
    """Use LLM to extract topics, questions, and intent from trigger text."""
    response = chat([{
        "role": "user",
        "content": (
            "Extract research intent from this text. Reply ONLY with JSON:\n"
            '{"topics": ["topic1", "topic2"], '
            '"questions": ["question1", "question2"], '
            '"intent": "brief description of what to research"}\n\n'
            f"Text: {text}"
        ),
    }])
    import json, re
    clean = re.sub(r"```json|```", "", response).strip()
    try:
        return json.loads(clean)
    except Exception:
        # Fallback: treat full text as the topic
        return {"topics": [text[:50]], "questions": [text], "intent": text}


def _search_github_knowledge(query: str) -> list[dict]:
    """Search only GitHub-sourced chunks in the knowledge base."""
    from core.vector_store import vector_store
    return vector_store.search(
        query,
        n_results=5,
        filter_metadata={"source_type": "github"},
    )


def _synthesize(trigger, intent, kb_results, web_results, github_results) -> str:
    """Synthesize all research sources into a structured markdown note."""

    # Build context for LLM
    context_parts = ["## Knowledge Base\n"]
    for c in kb_results.get("chunks", []):
        context_parts.append(f"- {c['metadata'].get('title','?')}: {c['text'][:200]}")

    context_parts.append("\n## Web Research\n")
    for topic, results in web_results.items():
        context_parts.append(f"### {topic}")
        for r in results[:3]:
            context_parts.append(f"- [{r['title']}]({r['url']}): {r['snippet'][:150]}")

    context_parts.append("\n## Related Code\n")
    for r in github_results[:3]:
        context_parts.append(f"- {r['metadata'].get('title','?')}: {r['text'][:200]}")

    context = "\n".join(context_parts)

    response = chat([{
        "role": "user",
        "content": (
            f"Create a structured research note in Markdown based on this trigger:\n\n"
            f"**Trigger:** {trigger}\n\n"
            f"**Intent:** {intent.get('intent', '')}\n\n"
            f"**Research context:**\n{context}\n\n"
            "Format the note with these sections:\n"
            "## Summary\n## Key Findings\n## Potential Problems\n"
            "## Suggested Solutions\n## Related Code\n## Resources\n## Next Steps\n\n"
            "Be specific and developer-focused. Include code snippets where relevant."
        ),
    }])
    return response


def _notify_telegram(result: dict) -> None:
    import requests
    msg = (
        f"🔬 *Research complete!*\n\n"
        f"📌 Topics: {', '.join(result['topics'])}\n"
        f"📝 Note: `{result['vault_note'].split('/')[-1]}`\n\n"
        f"{result['summary'][:300]}..."
    )
    requests.post(
        f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": settings.TELEGRAM_ALLOWED_USER_ID,
            "text": msg,
            "parse_mode": "Markdown",
        },
        timeout=10,
    )


def _update_status(research_id: str, status: str, vault_note: str = None) -> None:
    with get_cursor() as cur:
        if vault_note:
            cur.execute(
                "UPDATE research_notes SET status=%s, vault_note=%s, completed_at=NOW() WHERE id=%s",
                (status, vault_note, research_id),
            )
        else:
            cur.execute(
                "UPDATE research_notes SET status=%s WHERE id=%s",
                (status, research_id),
            )
```

---

### `research/scheduler.py`

```python
"""
Background task scheduler for async research jobs.
Uses asyncio — no Celery/Redis needed for personal use.
Tasks are queued in postgres and processed in background.
"""
import asyncio
import uuid
from datetime import datetime
from db.connection import get_cursor
from research.agent import run_research


async def queue_research(trigger_text: str) -> str:
    """Add a research task to the queue. Returns research_id."""
    rid = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO research_notes (id, title, trigger_text, content, status)
               VALUES (%s, %s, %s, %s, 'pending')""",
            (rid, f"Research {datetime.now().strftime('%Y-%m-%d %H:%M')}", trigger_text, ""),
        )
    return rid


async def process_pending() -> None:
    """Process all pending research tasks."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, trigger_text FROM research_notes WHERE status = 'pending' LIMIT 5"
        )
        pending = cur.fetchall()

    for task in pending:
        try:
            await run_research(task["trigger_text"], research_id=task["id"])
        except Exception as e:
            print(f"[Scheduler] Error on {task['id']}: {e}")
            with get_cursor() as cur:
                cur.execute(
                    "UPDATE research_notes SET status='error' WHERE id=%s", (task["id"],)
                )


async def run_forever(interval_seconds: int = 30) -> None:
    """Background loop that processes the research queue continuously."""
    print(f"[Scheduler] Running — checking every {interval_seconds}s")
    while True:
        await process_pending()
        await asyncio.sleep(interval_seconds)


def start_background_scheduler():
    """Start the scheduler in a background thread."""
    import threading
    def _run():
        asyncio.run(run_forever())
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t
```

---

## Phase 4 — Quality + Web UI

### `search/hybrid.py`

```python
"""
Hybrid search: BM25 (keyword) + pgvector (semantic) combined.

Why hybrid over pure semantic:
- Semantic search misses exact technical terms (function names, error codes, etc.)
- BM25 misses conceptual/paraphrase matches
- Hybrid gets both: "AuthenticationError" (exact) + "login failed" (semantic)

Reciprocal Rank Fusion (RRF) merges the two ranked lists.
"""
from core.vector_store import vector_store
from db.connection import get_cursor
from config.settings import settings


def bm25_search(query: str, n_results: int = 10) -> list[dict]:
    """Full-text search using PostgreSQL's built-in tsvector/tsquery."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, doc_id, content, metadata,
                   ts_rank(to_tsvector('english', content),
                           plainto_tsquery('english', %s)) AS score
            FROM chunks
            WHERE to_tsvector('english', content) @@ plainto_tsquery('english', %s)
            ORDER BY score DESC
            LIMIT %s
            """,
            (query, query, n_results),
        )
        rows = cur.fetchall()
    return [
        {
            "chunk_id": r["id"],
            "doc_id": r["doc_id"],
            "text": r["content"],
            "metadata": r["metadata"],
            "score": float(r["score"]),
        }
        for r in rows
    ]


def hybrid_search(query: str, n_results: int = 5, alpha: float = 0.5) -> list[dict]:
    """
    Combine BM25 and semantic results using Reciprocal Rank Fusion.
    alpha: weight of semantic vs BM25 (0.5 = equal weight)
    """
    semantic = vector_store.search(query, n_results=n_results * 2)
    keyword = bm25_search(query, n_results=n_results * 2)

    # RRF: score = 1 / (k + rank) for each list, sum across lists
    k = 60   # standard RRF constant
    scores = {}

    for rank, result in enumerate(semantic):
        cid = result["chunk_id"]
        scores[cid] = scores.get(cid, {"result": result, "score": 0})
        scores[cid]["score"] += alpha * (1 / (k + rank + 1))

    for rank, result in enumerate(keyword):
        cid = result["chunk_id"]
        if cid not in scores:
            scores[cid] = {"result": result, "score": 0}
        scores[cid]["score"] += (1 - alpha) * (1 / (k + rank + 1))

    # Sort by combined RRF score and return top N
    sorted_results = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    final = [item["result"] for item in sorted_results[:n_results]]

    # Attach RRF score
    for i, item in enumerate(sorted_results[:n_results]):
        final[i]["score"] = item["score"]

    return final
```

---

### `search/reranker.py`

```python
"""
Cross-encoder re-ranking using FlashRank.
After retrieval, re-ranks top-N chunks by actual relevance to the query.
More accurate than vector similarity alone — uses a full attention model
to score (query, chunk) pairs.
Install: pip install flashrank
"""


def rerank_chunks(query: str, chunks: list[dict], top_k: int = 5) -> list[dict]:
    """Re-rank retrieved chunks using a cross-encoder model."""
    try:
        from flashrank import Ranker, RerankRequest
    except ImportError:
        # Graceful fallback: return as-is
        print("[Reranker] flashrank not installed, skipping rerank")
        return chunks[:top_k]

    ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="/tmp/flashrank")

    passages = [{"id": i, "text": c["text"]} for i, c in enumerate(chunks)]
    request = RerankRequest(query=query, passages=passages)
    results = ranker.rerank(request)

    # Map back to original chunk dicts, sorted by rerank score
    reranked = []
    for r in results[:top_k]:
        chunk = chunks[r["id"]].copy()
        chunk["rerank_score"] = r["score"]
        reranked.append(chunk)

    return reranked
```

---

### `interfaces/web/app.py`

```python
"""
FastAPI web interface — Phase 4.
Serves the React/HTML frontend + REST API for chat, ingest, search.
Run: uvicorn interfaces.web.app:app --reload --port 8000
"""
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from pathlib import Path
import asyncio

app = FastAPI(title="Engram", version="0.1.0")

STATIC_DIR = Path(__file__).parent / "static"


# ── Request models ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str
    conversation_id: str | None = None
    use_hybrid: bool = False
    rerank: bool = False
    stream: bool = False


class IngestRequest(BaseModel):
    source: str
    para_category: str = "Resources"
    tags: list[str] = []


class SearchRequest(BaseModel):
    query: str
    n_results: int = 5


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    from core.rag import ask
    from core.memory import create_conversation

    conv_id = req.conversation_id or create_conversation()

    if req.stream:
        def _generate():
            result = ask(req.query, conversation_id=conv_id, stream=True,
                        use_hybrid=req.use_hybrid, rerank=req.rerank)
            for chunk in result:
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(_generate(), media_type="text/event-stream")

    result = ask(req.query, conversation_id=conv_id,
                use_hybrid=req.use_hybrid, rerank=req.rerank)
    return {**result, "conversation_id": conv_id}


@app.post("/api/ingest")
async def ingest_endpoint(req: IngestRequest):
    from ingestion.pipeline import ingest
    result = await asyncio.to_thread(
        ingest, req.source, req.para_category, req.tags
    )
    return result


@app.post("/api/search")
async def search_endpoint(req: SearchRequest):
    from core.vector_store import vector_store
    results = await asyncio.to_thread(
        vector_store.search, req.query, req.n_results
    )
    return {"results": results}


@app.get("/api/conversations")
async def list_conversations():
    from core.memory import list_conversations
    return {"conversations": list_conversations()}


@app.get("/api/stats")
async def stats():
    from core.vector_store import vector_store
    return {"total_chunks": vector_store.count()}


@app.post("/api/research")
async def trigger_research(body: dict):
    """Queue a research task from the web UI."""
    from research.scheduler import queue_research
    trigger = body.get("trigger", "")
    if not trigger:
        raise HTTPException(400, "trigger text required")
    rid = await queue_research(trigger)
    return {"research_id": rid, "status": "queued"}


# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
```

---

### `interfaces/web/static/index.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Engram</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #0d0d0d; color: #e8e8e8; height: 100vh; display: flex; }

    .sidebar { width: 260px; background: #141414; border-right: 1px solid #222;
               padding: 16px; display: flex; flex-direction: column; gap: 12px; }
    .sidebar h1 { font-size: 18px; font-weight: 700; color: #fff; }
    .sidebar input { background: #1e1e1e; border: 1px solid #2a2a2a; color: #e8e8e8;
                     padding: 8px 12px; border-radius: 6px; width: 100%; font-size: 13px; }
    .sidebar button { background: #2a2a2a; border: none; color: #e8e8e8; padding: 8px 12px;
                      border-radius: 6px; cursor: pointer; width: 100%; text-align: left;
                      font-size: 13px; transition: background 0.15s; }
    .sidebar button:hover { background: #333; }
    .sidebar button.primary { background: #5c5fef; color: #fff; }
    .sidebar button.primary:hover { background: #4a4dcf; }

    .main { flex: 1; display: flex; flex-direction: column; }
    .messages { flex: 1; overflow-y: auto; padding: 24px; display: flex;
                flex-direction: column; gap: 16px; }
    .message { max-width: 720px; }
    .message.user { align-self: flex-end; background: #1e3a5f; padding: 12px 16px;
                    border-radius: 12px 12px 2px 12px; }
    .message.assistant { align-self: flex-start; background: #1a1a1a;
                         border: 1px solid #2a2a2a; padding: 12px 16px;
                         border-radius: 12px 12px 12px 2px; }
    .citations { font-size: 11px; color: #666; margin-top: 8px; }

    .input-area { padding: 16px 24px; border-top: 1px solid #1e1e1e;
                  display: flex; gap: 8px; }
    .input-area input { flex: 1; background: #1a1a1a; border: 1px solid #2a2a2a;
                        color: #e8e8e8; padding: 10px 16px; border-radius: 8px;
                        font-size: 14px; outline: none; }
    .input-area input:focus { border-color: #5c5fef; }
    .input-area button { background: #5c5fef; border: none; color: #fff;
                         padding: 10px 20px; border-radius: 8px; cursor: pointer;
                         font-size: 14px; }
    .input-area button:hover { background: #4a4dcf; }

    .label { font-size: 11px; text-transform: uppercase; color: #555;
             letter-spacing: 0.08em; padding: 4px 0; }
  </style>
</head>
<body>
  <div class="sidebar">
    <h1>🧠 Engram</h1>
    <button class="primary" onclick="newChat()">+ New Chat</button>
    <div class="label">Add Knowledge</div>
    <input type="text" id="ingest-input" placeholder="URL or file path…" onkeydown="if(event.key==='Enter') ingestSource()">
    <button onclick="ingestSource()">Ingest →</button>
    <div class="label">Options</div>
    <label style="font-size:13px;display:flex;gap:8px;align-items:center;cursor:pointer">
      <input type="checkbox" id="hybrid-toggle"> Hybrid search
    </label>
    <label style="font-size:13px;display:flex;gap:8px;align-items:center;cursor:pointer">
      <input type="checkbox" id="rerank-toggle"> Re-rank results
    </label>
    <div id="stats" style="font-size:12px;color:#555;margin-top:auto"></div>
  </div>
  <div class="main">
    <div class="messages" id="messages">
      <div class="message assistant">
        <div>Ask me anything about your saved knowledge.</div>
      </div>
    </div>
    <div class="input-area">
      <input type="text" id="query-input" placeholder="Ask a question…" onkeydown="if(event.key==='Enter') sendMessage()">
      <button onclick="sendMessage()">Send</button>
    </div>
  </div>

  <script>
    let conversationId = null;

    async function sendMessage() {
      const input = document.getElementById('query-input');
      const query = input.value.trim();
      if (!query) return;
      input.value = '';
      appendMessage('user', query);

      const msgEl = appendMessage('assistant', '⏳ Thinking...');
      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            query,
            conversation_id: conversationId,
            use_hybrid: document.getElementById('hybrid-toggle').checked,
            rerank: document.getElementById('rerank-toggle').checked,
          }),
        });
        const data = await res.json();
        conversationId = data.conversation_id;
        let citationText = '';
        if (data.citations?.length) {
          citationText = '<div class="citations">Sources: ' +
            data.citations.map(c => `[${c.index}] ${c.title}`).join(' · ') + '</div>';
        }
        msgEl.innerHTML = `<div>${data.answer}</div>${citationText}`;
      } catch (e) {
        msgEl.innerHTML = `<div style="color:#f55">Error: ${e.message}</div>`;
      }
    }

    async function ingestSource() {
      const input = document.getElementById('ingest-input');
      const source = input.value.trim();
      if (!source) return;
      input.value = '';
      appendMessage('assistant', `📥 Ingesting: ${source}...`);
      try {
        const res = await fetch('/api/ingest', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({source}),
        });
        const data = await res.json();
        appendMessage('assistant', `✓ Ingested "${data.title}" — ${data.chunks} chunks`);
        loadStats();
      } catch(e) {
        appendMessage('assistant', `❌ Error: ${e.message}`);
      }
    }

    function appendMessage(role, text) {
      const el = document.createElement('div');
      el.className = `message ${role}`;
      el.innerHTML = `<div>${text}</div>`;
      const container = document.getElementById('messages');
      container.appendChild(el);
      container.scrollTop = container.scrollHeight;
      return el;
    }

    function newChat() {
      conversationId = null;
      document.getElementById('messages').innerHTML =
        '<div class="message assistant"><div>New conversation started.</div></div>';
    }

    async function loadStats() {
      const res = await fetch('/api/stats');
      const data = await res.json();
      document.getElementById('stats').textContent = `${data.total_chunks} chunks indexed`;
    }

    loadStats();
  </script>
</body>
</html>
```

---

## Docker Setup

### `docker-compose.yml`

```yaml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg16     # official pgvector image
    container_name: engram-postgres
    environment:
      POSTGRES_DB: engram
      POSTGRES_USER: engram
      POSTGRES_PASSWORD: engram
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db/migrations:/docker-entrypoint-initdb.d   # runs migrations on first start
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U engram -d engram"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

---

## Environment Variables

### `.env.example`

```bash
# ── LLM ───────────────────────────────────────────────────────────────────────
LLM_PROVIDER=ollama            # ollama | groq
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
OLLAMA_EMBED_MODEL=nomic-embed-text

# ── Groq (cloud fallback) ─────────────────────────────────────────────────────
# Free tier, no credit card: https://console.groq.com
GROQ_API_KEY=
GROQ_MODEL=llama-3.1-8b-instant

# ── PostgreSQL + pgvector ─────────────────────────────────────────────────────
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=engram
POSTGRES_USER=engram
POSTGRES_PASSWORD=engram

# ── Obsidian Vault ────────────────────────────────────────────────────────────
VAULT_PATH=~/Documents/Engram-Vault

# ── Whisper ───────────────────────────────────────────────────────────────────
WHISPER_MODEL=base             # tiny | base | small | medium | large
WHISPER_DEVICE=cpu             # cpu | cuda

# ── Chunking ──────────────────────────────────────────────────────────────────
CHUNK_SIZE=512
CHUNK_OVERLAP=64
CHUNK_STRATEGY=recursive
EMBED_DIMS=768                 # nomic-embed-text = 768

# ── GitHub ────────────────────────────────────────────────────────────────────
# Token: https://github.com/settings/tokens (read:repo scope)
GITHUB_TOKEN=
GITHUB_USERNAME=

# ── Telegram ──────────────────────────────────────────────────────────────────
# Create bot: @BotFather on Telegram
TELEGRAM_BOT_TOKEN=
# Your user ID: @userinfobot on Telegram
TELEGRAM_ALLOWED_USER_ID=

# ── Self-hosted connectors ────────────────────────────────────────────────────
NEXTCLOUD_URL=
NEXTCLOUD_USERNAME=
NEXTCLOUD_PASSWORD=
NEXTCLOUD_FOLDER=/

BOOKSTACK_URL=
BOOKSTACK_TOKEN_ID=
BOOKSTACK_TOKEN_SECRET=

# ── Web Search (Phase 3 Research Agent) ──────────────────────────────────────
# duckduckgo = no key needed | searxng = self-hosted, private
SEARCH_PROVIDER=duckduckgo
SEARXNG_URL=
```

---

## Full Requirements

### `requirements.txt`

```
# ── Core ──────────────────────────────────────────────────────────────────────
openai>=1.0.0
pydantic>=2.0.0
pydantic-settings>=2.0.0

# ── Database ──────────────────────────────────────────────────────────────────
psycopg2-binary>=2.9.0
pgvector>=0.2.0

# ── Ingestion ─────────────────────────────────────────────────────────────────
pymupdf>=1.24.0
trafilatura>=1.8.0
yt-dlp>=2024.1.0
faster-whisper>=1.0.0

# ── GitHub ────────────────────────────────────────────────────────────────────
PyGithub>=2.0.0

# ── Voice ─────────────────────────────────────────────────────────────────────
sounddevice>=0.4.6
soundfile>=0.12.0
numpy>=1.24.0
pyttsx3>=2.90
# piper-tts>=1.0.0            # optional: high quality TTS

# ── Telegram ──────────────────────────────────────────────────────────────────
python-telegram-bot>=20.0

# ── Self-hosted connectors ────────────────────────────────────────────────────
requests>=2.31.0
webdavclient3>=3.14.0
pyyaml>=6.0

# ── Phase 3: Research Agent ───────────────────────────────────────────────────
duckduckgo-search>=5.0.0

# ── Phase 4: Quality ──────────────────────────────────────────────────────────
flashrank>=0.0.9               # cross-encoder re-ranking
fastapi>=0.110.0               # web API
uvicorn>=0.27.0                # ASGI server
python-multipart>=0.0.9        # file upload support

# ── CLI ───────────────────────────────────────────────────────────────────────
rich>=13.0.0
```

---

## Database Setup Script

### `scripts/setup_db.py`

```python
"""
Run this once after starting postgres to create schema.
python scripts/setup_db.py
"""
from pathlib import Path
import psycopg2
from config.settings import settings


def setup():
    print(f"Connecting to {settings.DATABASE_URL}...")
    conn = psycopg2.connect(settings.DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    migration_file = Path(__file__).parent.parent / "db/migrations/001_initial.sql"
    sql = migration_file.read_text()

    cur.execute(sql)
    print("✓ Schema created successfully")
    print("✓ pgvector extension enabled")
    print("✓ HNSW index created on chunks.embedding")

    cur.close()
    conn.close()


if __name__ == "__main__":
    setup()
```

---

## CLI — All Commands

### `interfaces/cli/__main__.py`

```python
"""
Full CLI covering all 4 phases.
python -m interfaces.cli <command>
"""
import argparse


# ── Phase 1 commands ──────────────────────────────────────────────────────────

def cmd_init(args):
    from vault.writer import setup_vault
    from scripts.setup_db import setup
    print("\n🧠 Initializing Engram...")
    setup()
    setup_vault()
    print("\n✓ Done. Next:")
    print("  ollama pull llama3.1:8b && ollama pull nomic-embed-text")
    print("  python -m interfaces.cli add <url>\n")


def cmd_ask(args):
    from core.rag import ask
    query = " ".join(args.query)
    stream = ask(query, stream=True, n_results=args.n,
                 use_hybrid=args.hybrid, rerank=args.rerank)
    print("\n🤖 ", end="", flush=True)
    for chunk in stream:
        print(chunk, end="", flush=True)
    print("\n")
    result = ask(query, n_results=args.n, use_hybrid=args.hybrid, rerank=args.rerank)
    if result["citations"]:
        print("📚 Sources:")
        for c in result["citations"]:
            print(f"  [{c['index']}] {c['title']} ({c['source_type']}) — {c['score']:.2f}")
    print()


def cmd_add(args):
    from ingestion.pipeline import ingest
    tags = args.tags.split(",") if args.tags else []
    result = ingest(args.source, para_category=args.para, tags=tags)
    print(f"✓ '{result['title']}' — {result['chunks']} chunks → {result['vault_note']}\n")


def cmd_github(args):
    from connectors.github.ingest import ingest_repo, ingest_all_repos
    if args.repo == "all":
        for r in ingest_all_repos():
            print(f"  ✓ {r['repo']} ({r['files_ingested']} files, {r['issues_ingested']} issues)")
    else:
        r = ingest_repo(args.repo)
        print(f"  ✓ Files: {r['files_ingested']}, Issues: {r['issues_ingested']}, PRs: {r['prs_ingested']}")


def cmd_search(args):
    from core.vector_store import vector_store
    from search.hybrid import hybrid_search
    query = " ".join(args.query)
    results = hybrid_search(query, args.n) if args.hybrid else vector_store.search(query, args.n)
    for i, r in enumerate(results, 1):
        print(f"[{i}] {r['metadata'].get('title','?')} ({r['metadata'].get('source_type','?')}) — {r['score']:.2f}")
        print(f"    {r['text'][:150].strip()}...\n")


def cmd_list(args):
    from db.connection import get_cursor
    with get_cursor() as cur:
        cur.execute("SELECT title, source_type, ingested_at FROM documents ORDER BY ingested_at DESC LIMIT 50")
        rows = cur.fetchall()
    print(f"\n📦 {len(rows)} documents\n")
    for r in rows:
        print(f"  • {r['title']} ({r['source_type']}) — {str(r['ingested_at'])[:10]}")
    print()


# ── Phase 2 commands ──────────────────────────────────────────────────────────

def cmd_voice(args):
    from voice.assistant import voice_query_loop
    voice_query_loop()


def cmd_note(args):
    from voice.mic import ingest_voice_note
    result = ingest_voice_note()
    if result:
        print(f"\n✓ {result['vault_note']}\n  {result['summary'][:200]}\n")


def cmd_sync(args):
    from connectors.registry import sync_all, get_connector
    import json
    if args.connector:
        result = get_connector(args.connector).ingest_all(dry_run=args.dry_run)
        print(json.dumps(result, indent=2))
    else:
        for r in sync_all(dry_run=args.dry_run):
            print(f"  ✓ {r.get('connector')}: {r.get('ingested', 0)} docs")


def cmd_telegram(args):
    from interfaces.telegram.bot import run
    run()


# ── Phase 3 commands ──────────────────────────────────────────────────────────

def cmd_research(args):
    import asyncio
    from research.agent import run_research
    trigger = " ".join(args.trigger)
    print(f"\n🔬 Starting research: {trigger}\n")
    result = asyncio.run(run_research(trigger))
    print(f"\n✓ Research complete!")
    print(f"  Note: {result['vault_note']}")
    print(f"  Topics: {', '.join(result['topics'])}\n")


# ── Phase 4 commands ──────────────────────────────────────────────────────────

def cmd_serve(args):
    import uvicorn
    print(f"\n🌐 Starting web UI at http://localhost:{args.port}\n")
    uvicorn.run("interfaces.web.app:app", host="0.0.0.0", port=args.port, reload=args.reload)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(prog="engram")
    sub = p.add_subparsers(dest="command")

    # init
    sub.add_parser("init")

    # ask
    a = sub.add_parser("ask")
    a.add_argument("query", nargs="+")
    a.add_argument("-n", type=int, default=5)
    a.add_argument("--hybrid", action="store_true")
    a.add_argument("--rerank", action="store_true")

    # add
    a = sub.add_parser("add")
    a.add_argument("source")
    a.add_argument("--para", default="Resources")
    a.add_argument("--tags", default="")

    # github
    a = sub.add_parser("github")
    a.add_argument("repo")

    # search
    a = sub.add_parser("search")
    a.add_argument("query", nargs="+")
    a.add_argument("-n", type=int, default=5)
    a.add_argument("--hybrid", action="store_true")

    # list
    sub.add_parser("list")

    # voice
    sub.add_parser("voice")
    sub.add_parser("note")

    # sync
    a = sub.add_parser("sync")
    a.add_argument("--connector")
    a.add_argument("--dry-run", action="store_true")

    # telegram
    sub.add_parser("telegram")

    # research
    a = sub.add_parser("research")
    a.add_argument("trigger", nargs="+")

    # serve
    a = sub.add_parser("serve")
    a.add_argument("--port", type=int, default=8000)
    a.add_argument("--reload", action="store_true")

    args = p.parse_args()
    {
        "init": cmd_init, "ask": cmd_ask, "add": cmd_add,
        "github": cmd_github, "search": cmd_search, "list": cmd_list,
        "voice": cmd_voice, "note": cmd_note, "sync": cmd_sync,
        "telegram": cmd_telegram, "research": cmd_research, "serve": cmd_serve,
    }.get(args.command, lambda _: p.print_help())(args)


if __name__ == "__main__":
    main()
```

---

## Build Order for Claude Code

Implement in this exact order to always have a working state:

```
Step 1  docker-compose.yml + db/migrations/001_initial.sql
Step 2  config/settings.py
Step 3  db/connection.py + db/models.py
Step 4  core/llm.py
Step 5  core/vector_store.py (pgvector)
Step 6  core/memory.py
Step 7  ingestion/chunkers/strategies.py
Step 8  ingestion/parsers/content.py
Step 9  ingestion/pipeline.py
Step 10 vault/writer.py
Step 11 core/rag.py
Step 12 interfaces/cli/__main__.py (Phase 1 commands only first)
        ── PHASE 1 COMPLETE — test: init, add, ask, search ──
Step 13 voice/mic.py
Step 14 voice/tts.py
Step 15 voice/assistant.py
Step 16 interfaces/telegram/bot.py
Step 17 connectors/selfhosted/base.py
Step 18 connectors/selfhosted/nextcloud.py
Step 19 connectors/selfhosted/bookstack.py
Step 20 connectors/selfhosted/obsidian_sync.py
Step 21 connectors/registry.py
Step 22 connectors/github/ingest.py
        ── PHASE 2 COMPLETE — test: voice, note, telegram, sync ──
Step 23 research/web_search.py
Step 24 research/agent.py
Step 25 research/scheduler.py
        ── PHASE 3 COMPLETE — test: research <trigger text> ──
Step 26 search/hybrid.py
Step 27 search/reranker.py
Step 28 interfaces/web/app.py
Step 29 interfaces/web/static/index.html
Step 30 scripts/setup_db.py + scripts/benchmark.py
Step 31 tests/
        ── PHASE 4 COMPLETE — test: serve, ask --hybrid --rerank ──
```

---

## Quick Start (once Claude Code builds it)

```bash
# 1. Start Postgres
docker-compose up -d

# 2. Install deps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Pull Ollama models
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# 4. Configure
cp .env.example .env
# Edit .env: set VAULT_PATH, GITHUB_TOKEN, GITHUB_USERNAME at minimum

# 5. Initialize
python -m interfaces.cli init

# 6. Add knowledge
python -m interfaces.cli add https://some-article.com
python -m interfaces.cli add ~/Documents/some.pdf
python -m interfaces.cli github yourusername/your-repo

# 7. Ask questions
python -m interfaces.cli ask "how did I implement auth in my projects?"
python -m interfaces.cli ask --hybrid --rerank "Redis caching patterns"

# 8. Start voice assistant
python -m interfaces.cli voice

# 9. Start Telegram bot (set TELEGRAM_BOT_TOKEN in .env first)
python -m interfaces.cli telegram

# 10. Start web UI
python -m interfaces.cli serve
```

---

## Resume Story

**One-liner:** Built a fully local, privacy-first AI knowledge assistant with RAG, pgvector semantic search, local LLM inference (Ollama), multimodal ingestion (Whisper, PDF, GitHub), and a Telegram bot for remote access.

**Concepts demonstrated:**
- RAG pipeline (retrieval, chunking strategies, re-ranking)
- Local LLM deployment and inference (Ollama, quantized models)
- pgvector + HNSW indexing for production-grade semantic search
- Hybrid search (BM25 + cosine similarity, RRF fusion)
- Multimodal pipelines (text + audio + code as unified knowledge)
- Async research agent with web search + synthesis
- Adapter pattern for heterogeneous data connectors
- Full-stack: FastAPI + PostgreSQL + React frontend

---

## TODO (Deferred — Future Product Idea)

The autonomous research agent as a standalone product/SaaS is on the
backlog. The personal-use implementation in Phase 3 is the foundation.
Key considerations when revisiting:
- Multi-user isolation (separate schemas or databases per user)
- Job queue with proper retry logic (Celery + Redis)
- Rate limiting on web search to avoid blocks
- Research quality scoring and feedback loop
- Knowledge graph with proper entity resolution
