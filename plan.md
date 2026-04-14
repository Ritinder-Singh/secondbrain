# Engram — Implementation Plan

## Overview

Four sequential phases. Each phase is independently usable — Phase 1 alone gives you a working RAG system.
Hardware target: i7-1255U, 32GB RAM. Primary model: llama3.1:8b via Ollama.

---

## Phase 1 — Core RAG Pipeline (Foundation)

**Goal:** Working knowledge base. Ingest anything → ask questions → get cited answers from your own notes.

### Step 1.1 — Project Setup
- [ ] Create `engram/` package (all `__init__.py` files)
- [ ] Write `config/settings.py` — Pydantic settings from `.env`
- [ ] Write `.env.example`
- [ ] Write `requirements.txt`
- [ ] Write `docker-compose.yml` (postgres + pgvector image)

### Step 1.2 — Database Layer
- [ ] Write `db/migrations/001_initial.sql` — all 5 tables + HNSW + GIN indexes
- [ ] Write `db/connection.py` — threaded psycopg2 pool + pgvector registration
- [ ] Write `db/models.py` — dataclasses for Document, Chunk, Message
- [ ] Write `scripts/setup_db.py` — run migration on fresh DB

### Step 1.3 — LLM + Embeddings
- [ ] Write `core/llm.py` — unified OpenAI-compatible client (Ollama / Groq toggle)
- [ ] `embed()` always uses Ollama regardless of `LLM_PROVIDER`
- [ ] `chat()` supports both streaming and non-streaming

### Step 1.4 — Vector Store
- [ ] Write `core/vector_store.py` — `VectorStore` class
  - `add()` — embed single chunk + insert
  - `add_batch()` — bulk insert
  - `search()` — cosine similarity + optional metadata filter
  - `delete_document()` — cascade delete
  - `upsert_document()` — idempotent document insert
  - `count()` — total indexed chunks

### Step 1.5 — Chunking Strategies
- [ ] Write `ingestion/chunkers/strategies.py`
  - `chunk_fixed()` — character-level with overlap
  - `chunk_sentence()` — sentence boundary aware
  - `chunk_recursive()` — paragraph → sentence → word fallback (default)
  - `chunk_code()` — function/class boundary via regex (Python, JS, TS, Go, Rust)
  - `get_chunks()` — dispatcher

### Step 1.6 — Content Parsers
- [ ] Write `ingestion/parsers/content.py`
  - `parse_pdf()` — PyMuPDF
  - `parse_url()` — trafilatura (article extraction)
  - `parse_youtube()` — yt-dlp + faster-whisper transcription
  - `parse_audio_file()` — faster-whisper
  - `parse_text_file()` — plain text / markdown
  - `parse()` — auto-detect dispatcher

### Step 1.7 — Ingestion Pipeline
- [ ] Write `ingestion/pipeline.py` — `ingest(source)` orchestrator
  - parse → select chunking strategy → chunk → embed → upsert to pgvector → write vault note
  - Deterministic doc_id via `uuid5` (deduplicates re-ingestion)

### Step 1.8 — Conversation Memory
- [ ] Write `core/memory.py`
  - `create_conversation()` — returns UUID
  - `save_message()` — append user/assistant turn
  - `get_history()` — last N turns as OpenAI-format list
  - `list_conversations()` — for CLI/UI listing

### Step 1.9 — RAG Pipeline
- [ ] Write `core/rag.py` — `ask(query, conversation_id, ...)` function
  - Retrieve → format context with [N] citations → build messages → generate → save to memory
  - Streaming support
  - Hooks for hybrid search + reranking (Phase 4 flags, but not wired yet)

### Step 1.10 — Obsidian Vault Writer
- [ ] Write `vault/writer.py`
  - `setup_vault()` — create PARA folders (Projects, Areas, Resources, Archive, Research)
  - `write_source_note()` — write ingested source as markdown with frontmatter
  - `write_research_note()` — write AI-generated research note

### Step 1.11 — CLI (Phase 1 commands)
- [ ] Write `interfaces/cli/__main__.py`
  - `init` — setup DB + vault + print next steps
  - `add <source>` — ingest a source
  - `ask <query>` — RAG query with streaming
  - `search <query>` — raw vector search (no LLM)
  - `list` — list ingested documents
  - `stats` — chunk count

**Phase 1 complete when:** `python -m interfaces.cli ask "What is X?"` returns a cited answer from ingested content.

---

## Phase 2 — Connectors + Telegram + Voice

**Goal:** Ingest from GitHub / Nextcloud / BookStack. Chat via Telegram. Use voice input/output.

### Step 2.1 — Base Connector
- [ ] Write `connectors/selfhosted/base.py` — `BaseConnector` abstract class
  - `fetch_documents()` → list of raw content dicts
  - `sync()` — fetch + ingest all

### Step 2.2 — GitHub Connector
- [ ] Write `connectors/github/ingest.py`
  - Ingest repo files at function-level granularity (code chunker)
  - Ingest issues and PRs as text
  - Filter by file extensions

### Step 2.3 — Nextcloud Connector
- [ ] Write `connectors/selfhosted/nextcloud.py`
  - WebDAV file listing + download
  - Filter by folder + file types

### Step 2.4 — BookStack Connector
- [ ] Write `connectors/selfhosted/bookstack.py`
  - REST API pagination
  - Fetch books → chapters → pages as markdown

### Step 2.5 — Obsidian Sync Connector
- [ ] Write `connectors/selfhosted/obsidian_sync.py`
  - Walk existing vault directory
  - Ingest all `.md` files (skip auto-generated Engram notes to avoid loops)

### Step 2.6 — Connector Registry
- [ ] Write `connectors/registry.py`
  - Register + run all configured connectors
  - `sync_all()` — used by CLI `sync` command

### Step 2.7 — Voice Input/Output
- [ ] Write `voice/mic.py` — record from mic → WAV → Whisper transcription
- [ ] Write `voice/tts.py` — Piper TTS (primary) / pyttsx3 (fallback)
- [ ] Write `voice/assistant.py` — hands-free loop: listen → transcribe → RAG → speak

### Step 2.8 — Telegram Bot
- [ ] Write `interfaces/telegram/bot.py`
  - Single-user gate (TELEGRAM_ALLOWED_USER_ID)
  - `/ask <query>` — RAG query
  - `/add <url>` — ingest a URL
  - `/voice` — voice note → transcribe → RAG → reply
  - `/research <topic>` — queue async research (Phase 3)
  - `/sync` — run all connectors

### Step 2.9 — CLI additions
- [ ] `sync` command — run all connectors
- [ ] `voice` command — start voice assistant loop
- [ ] `github <repo>` — ingest a specific GitHub repo

---

## Phase 3 — Research Agent

**Goal:** Send a voice note from your phone → come home to a structured research note in your Obsidian vault.

### Step 3.1 — Web Search
- [ ] Write `research/web_search.py`
  - DuckDuckGo (no API key)
  - SearXNG (self-hosted, preferred for privacy)

### Step 3.2 — Research Agent
- [ ] Write `research/agent.py` — `run_research(trigger_text)` async pipeline
  1. LLM extracts topics + questions from trigger text
  2. Search existing knowledge base (pgvector)
  3. Web search for each topic (DuckDuckGo / SearXNG)
  4. Search GitHub-sourced chunks
  5. LLM synthesizes all sources → structured markdown research note
  6. Write note to Obsidian vault
  7. Ingest the research note itself (recursive knowledge growth)
  8. Notify via Telegram when complete

### Step 3.3 — Synthesizer
- [ ] Write `research/synthesizer.py` — isolated synthesis logic (called by agent)

### Step 3.4 — Background Scheduler
- [ ] Write `research/scheduler.py`
  - `queue_research(trigger_text)` — insert pending task in postgres
  - `process_pending()` — pick up and run pending tasks
  - `run_forever(interval=30s)` — asyncio background loop
  - `start_background_scheduler()` — daemonized thread

### Step 3.5 — CLI + Telegram additions
- [ ] `research <text>` CLI command — queue research task
- [ ] `/research` Telegram command — trigger from phone

---

## Phase 4 — Quality + Web UI

**Goal:** Better retrieval quality. Simple web UI accessible from any device on the local network.

### Step 4.1 — Hybrid Search
- [ ] Write `search/hybrid.py`
  - `bm25_search()` — PostgreSQL full-text search (tsvector/tsquery)
  - `hybrid_search()` — Reciprocal Rank Fusion (RRF) combining BM25 + semantic
  - Configurable `alpha` weighting (default 0.5)
- [ ] Wire hybrid search into `core/rag.py` (`use_hybrid=True` flag)

### Step 4.2 — Re-ranking
- [ ] Write `search/reranker.py`
  - FlashRank cross-encoder (`ms-marco-MiniLM-L-12-v2`)
  - Graceful fallback if `flashrank` not installed
- [ ] Wire reranking into `core/rag.py` (`rerank=True` flag)

### Step 4.3 — Auto-summarization
- [ ] Add `summary` field population to ingestion pipeline
  - LLM generates 2-3 sentence summary per document at ingest time
  - Stored in `documents.summary` column

### Step 4.4 — FastAPI Web App
- [ ] Write `interfaces/web/app.py` — FastAPI app
- [ ] Write `interfaces/web/routes/chat.py` — `/api/chat` (streaming SSE)
- [ ] Write `interfaces/web/routes/ingest.py` — `/api/ingest`
- [ ] Write `interfaces/web/routes/search.py` — `/api/search`
- [ ] Write `interfaces/web/static/index.html` — dark-mode chat UI
  - Sidebar: ingest input, hybrid/rerank toggles, chunk stats
  - Main: message thread with citations
  - New conversation button

### Step 4.5 — Benchmarking
- [ ] Write `scripts/benchmark.py`
  - Compare Q4 vs Q8 quantization
  - Compare chunking strategies on retrieval quality
  - Measure latency per component

### Step 4.6 — Tests
- [ ] Write `tests/test_ingestion.py`
- [ ] Write `tests/test_rag.py`
- [ ] Write `tests/test_vector_store.py`
- [ ] Write `tests/test_chunkers.py`

---

## Implementation Order

```
Phase 1 → Phase 2 → Phase 3 → Phase 4
  ↕              ↕
DB/core      Connectors    Research     Search quality
(2-3 days)   (2-3 days)   (1-2 days)   (1-2 days)
```

Start with Phase 1. Each phase delivers standalone value.
