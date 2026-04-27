# CLAUDE.md — Engram Project Context

## What is this?

**Engram** is a personal AI knowledge assistant — fully local, privacy-first.
Everything you save (articles, PDFs, YouTube videos, voice notes, GitHub repos, markdown files)
gets embedded, indexed in pgvector, and becomes searchable and "chattable" via a local LLM.

Working name: **Engram**. Other candidates: Exo, Recall, Etch.

---

## Architecture in one sentence

> CLI/Telegram/Web → RAG pipeline → pgvector (PostgreSQL) + Obsidian vault ← Ollama (local LLM)

---

## Key decisions (non-negotiable)

| Decision | Choice | Reason |
|---|---|---|
| LLM runtime | Ollama only (strictly local) | Privacy-first — no cloud calls |
| Embeddings | `nomic-embed-text` via Ollama | Always local — never sent to cloud |
| Vector store | PostgreSQL + pgvector | Production-appropriate, self-hostable, resume story |
| Knowledge storage | Obsidian vault (PARA structure, plain markdown) | Human-readable, portable |
| Primary model | `llama3.1:8b` | Fits in 32GB RAM on i7-1255U laptop |
| Primary interface | CLI, then Telegram bot | Developer-first |
| Voice | faster-whisper (STT) + Piper TTS | Local, no API |

**Do NOT implement:** Autonomous research SaaS / multi-user product. Scoped to personal use only.

---

## Project root

```
secondBrain/
├── engram/          ← all source code lives here
├── CLAUDE.md        ← this file
├── plan.md          ← phased implementation plan
├── features.md      ← feature breakdown
└── ENGRAM_CLAUDE_CODE.md  ← original full spec (source of truth)
```

---

## Module map

| Module | Purpose |
|---|---|
| `config/settings.py` | Pydantic settings, all config via `.env` |
| `core/llm.py` | Ollama client (strictly local, OpenAI-compatible API) |
| `core/rag.py` | RAG pipeline: retrieve → augment → generate |
| `core/vector_store.py` | pgvector wrapper — semantic search |
| `core/memory.py` | Persistent conversation memory in PostgreSQL |
| `db/connection.py` | Psycopg2 thread-safe connection pool |
| `db/migrations/001_initial.sql` | Schema: documents, chunks, conversations, messages, research_notes |
| `db/models.py` | Dataclass mirrors of DB tables |
| `ingestion/pipeline.py` | Orchestrates: parse → chunk → embed → store + vault |
| `ingestion/parsers/content.py` | PDF, web, YouTube, audio, text/markdown parsers |
| `ingestion/chunkers/strategies.py` | fixed, sentence, recursive, code-aware chunking |
| `connectors/registry.py` | Central connector registry + sync runner |
| `connectors/github/ingest.py` | GitHub repos (function-level), issues, PRs |
| `connectors/selfhosted/` | Nextcloud (WebDAV), BookStack (REST), Obsidian sync |
| `research/agent.py` | Async research pipeline (Phase 3) |
| `research/web_search.py` | Self-hosted SearXNG (requires SEARXNG_URL in .env) |
| `research/synthesizer.py` | Multi-source synthesis → structured note |
| `research/scheduler.py` | asyncio-based background task runner |
| `voice/mic.py` | Mic recording + Whisper transcription |
| `voice/tts.py` | Piper TTS / pyttsx3 fallback |
| `voice/assistant.py` | Hands-free voice Q&A loop |
| `vault/writer.py` | Obsidian markdown note writer (PARA structure) |
| `interfaces/cli/__main__.py` | Full CLI (all commands) |
| `interfaces/telegram/bot.py` | Telegram bot (voice, text, files, commands) |
| `interfaces/web/app.py` | FastAPI app (Phase 4) |
| `search/hybrid.py` | BM25 + pgvector cosine hybrid search (Phase 4) |
| `search/reranker.py` | FlashRank cross-encoder re-ranking (Phase 4) |

---

## Database schema (summary)

- **documents** — one row per ingested source (PDF, article, repo, etc.)
- **chunks** — one row per text chunk + 768-dim embedding (nomic-embed-text)
- **conversations** — chat sessions
- **messages** — conversation history (user/assistant turns)
- **research_notes** — AI-generated research triggered by voice notes / Telegram

HNSW index on `chunks.embedding` for fast ANN search.
GIN index on `chunks.content` for BM25 full-text search (Phase 4).

---

## Running locally

```bash
# 1. Start postgres
docker compose up -d

# 2. Setup DB schema
python scripts/setup_db.py

# 3. Pull models
ollama pull llama3.1:8b && ollama pull nomic-embed-text

# 4. Init vault + DB
python -m interfaces.cli init

# 5. Ingest something
python -m interfaces.cli add https://example.com/article

# 6. Ask a question
python -m interfaces.cli ask "What did that article say about X?"

# 7. Web UI (Phase 4)
uvicorn interfaces.web.app:app --reload --port 8000
```

---

## Coding conventions

- Python 3.11+, type hints everywhere
- Pydantic for settings/validation
- `psycopg2` + connection pool (not SQLAlchemy) — keep it simple
- pgvector types registered per-connection via `register_vector(conn)`
- Embeddings always via local Ollama
- Async only where necessary (research agent, Telegram bot, FastAPI routes)
- No Celery/Redis — asyncio + postgres queue is enough for personal use
- Rich for CLI output formatting
- Source IDs: `uuid5(NAMESPACE_URL, source_url_or_path)` — deterministic, deduplicates re-ingestion
- Chunk IDs: `{doc_id}__chunk_{index}`

---

## What NOT to do

- Do NOT mock the DB in tests — use real postgres (learned from past divergence issues)
- Do NOT implement multi-user auth, SaaS features, or rate limiting
- Do NOT use ChromaDB — replaced by pgvector
- Do NOT replace the chunking strategies with LangChain's text splitter — custom is intentional
- Do NOT add Tree-sitter yet (marked as TODO in `chunk_code`) — regex patterns are sufficient for now
