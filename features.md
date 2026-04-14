# Engram — Feature Breakdown

## Core Features

### Knowledge Ingestion
| Feature | Source Types | Parser | Status |
|---|---|---|---|
| PDF ingestion | `.pdf` | PyMuPDF (`fitz`) | Phase 1 |
| Web article | `http://`, `https://` | trafilatura | Phase 1 |
| YouTube video | `youtube.com`, `youtu.be` | yt-dlp + faster-whisper | Phase 1 |
| Audio file | `.mp3`, `.wav`, `.m4a`, `.ogg` | faster-whisper | Phase 1 |
| Markdown / text | `.md`, `.txt` | plain read | Phase 1 |
| GitHub repos | repos, issues, PRs | PyGithub + code chunker | Phase 2 |
| Nextcloud files | WebDAV | webdavclient3 | Phase 2 |
| BookStack pages | REST API | requests | Phase 2 |
| Existing Obsidian vault | directory walk | plain read | Phase 2 |

### Chunking Strategies
| Strategy | Best for | Key property |
|---|---|---|
| `recursive` (default) | prose, markdown | paragraph → sentence → word fallback |
| `sentence` | articles, transcripts | preserves sentence boundaries |
| `fixed` | uniform indexing | simple, predictable size |
| `code` | source code | function/class boundary splitting via regex |

### Search & Retrieval
| Feature | Implementation | Phase |
|---|---|---|
| Semantic search | pgvector cosine similarity + HNSW index | 1 |
| Metadata filtering | JSONB WHERE clause on chunks | 1 |
| Keyword search (BM25) | PostgreSQL tsvector/tsquery + GIN index | 4 |
| Hybrid search | BM25 + semantic via Reciprocal Rank Fusion | 4 |
| Cross-encoder reranking | FlashRank `ms-marco-MiniLM-L-12-v2` | 4 |

### RAG Pipeline
- Source-cited answers using `[N]` notation
- Conversation memory persisted in PostgreSQL
- Streaming responses (token-by-token)
- Configurable context window (number of retrieved chunks)
- Optional hybrid search and reranking flags

---

## LLM Configuration
| Setting | Options | Default |
|---|---|---|
| Provider | `ollama` (local), `groq` (cloud) | `ollama` |
| Chat model | `llama3.1:8b` (Ollama), `llama-3.1-8b-instant` (Groq) | llama3.1:8b |
| Embedding model | `nomic-embed-text` (768 dims) | always Ollama |
| Embedding dims | 768 (nomic), 1024 (mxbai-embed-large), 384 (all-minilm) | 768 |

Embeddings **always** run locally via Ollama, regardless of `LLM_PROVIDER`. Privacy guarantee.

---

## Interfaces

### CLI (Phase 1+)
```
python -m interfaces.cli init             # setup DB + vault
python -m interfaces.cli add <source>     # ingest any source
python -m interfaces.cli ask "<query>"    # RAG query (streaming)
python -m interfaces.cli search "<query>" # raw vector search
python -m interfaces.cli list             # list documents
python -m interfaces.cli stats            # chunk count
python -m interfaces.cli sync             # run all connectors (Phase 2)
python -m interfaces.cli voice            # voice assistant loop (Phase 2)
python -m interfaces.cli github <repo>    # ingest GitHub repo (Phase 2)
python -m interfaces.cli research "<text>"# queue research task (Phase 3)
python -m interfaces.cli serve            # start web UI (Phase 4)
```

### Telegram Bot (Phase 2+)
```
/ask <query>     — RAG query
/add <url>       — ingest a URL
/voice           — voice note → transcribe → RAG → reply
/research <text> — queue async research task
/sync            — run all connectors
```
Single-user gated by `TELEGRAM_ALLOWED_USER_ID`.

### Web UI — FastAPI + plain HTML (Phase 4)
- Dark-mode chat interface
- Sidebar: ingest input box, hybrid search toggle, rerank toggle, chunk stats
- Message thread with source citations
- Streaming responses via SSE
- REST API: `/api/chat`, `/api/ingest`, `/api/search`, `/api/conversations`, `/api/stats`, `/api/research`

---

## Voice Features (Phase 2)

| Feature | Implementation |
|---|---|
| Mic recording | `sounddevice` + `soundfile` |
| Transcription | `faster-whisper` (local, configurable model size) |
| Text-to-speech | Piper TTS (primary) / pyttsx3 (fallback) |
| Hands-free loop | record → transcribe → RAG → speak |

Whisper model sizes: `tiny`, `base`, `small`, `medium`, `large` (configured via `WHISPER_MODEL`).

---

## Research Agent (Phase 3)

Triggered by voice note or Telegram message. Runs asynchronously in the background.

**Pipeline:**
1. LLM extracts topics + questions from trigger text
2. Search existing knowledge base (semantic retrieval)
3. Web search (DuckDuckGo or self-hosted SearXNG) for each topic
4. Search GitHub-sourced knowledge chunks specifically
5. LLM synthesizes all sources into a structured Obsidian research note
6. Note ingested into the knowledge base (recursive knowledge growth)
7. Telegram notification when complete

**Queue mechanism:** Tasks stored in `research_notes` postgres table with status `pending → processing → complete | error`. Processed by asyncio background loop (no Celery/Redis needed).

**Use case:** "Send a voice note from your phone while commuting → come home to a complete research note in your vault."

---

## Self-hosted Connectors (Phase 2)

| Connector | Protocol | Use case |
|---|---|---|
| GitHub | REST API via PyGithub | Ingest your repos, issues, PRs |
| Nextcloud | WebDAV | Sync cloud documents |
| BookStack | REST API | Sync wiki/documentation pages |
| Obsidian | Directory walk | Sync existing vault notes |

All connectors implement `BaseConnector` (adapter pattern). `connectors/registry.py` runs all configured connectors via `sync_all()`.

---

## Data Model

### Documents
One row per ingested source. Tracks: title, source type, URL/path, PARA category, tags, metadata, Obsidian vault note path, ingestion timestamp, auto-summary (Phase 4).

### Chunks
One row per text chunk. Each has a 768-dimensional embedding vector. Linked to parent document by `doc_id`. HNSW index enables fast approximate nearest-neighbor search.

### Conversations + Messages
Persistent chat history. Each conversation stores all turns. History fed back to LLM as context (last 10 messages by default).

### Research Notes
Tracks async research tasks: trigger text, status, generated content, vault note path, timestamps.

---

## Obsidian Vault Structure (PARA)

```
Engram-Vault/
├── Projects/       ← active project notes
├── Areas/          ← ongoing responsibilities
├── Resources/      ← ingested articles, PDFs, videos (default)
├── Archive/        ← completed/old notes
└── Research/       ← AI-generated research notes (Phase 3)
```

Every ingested source gets an Obsidian markdown note with:
- YAML frontmatter (source_type, url, tags, ingested_at)
- Auto-generated summary
- Wikilink-compatible title

---

## Privacy Guarantees

- Embeddings always local (Ollama / nomic-embed-text) — never sent to cloud
- Groq fallback only affects chat completions, never embeddings
- All data stored locally: PostgreSQL + Obsidian vault on disk
- No telemetry, no external services required (DuckDuckGo for research is the only external call)
- SearXNG self-hosted option for fully air-gapped web search

---

## Not Implemented (By Design)

- Multi-user support / SaaS features
- Authentication / authorization (personal tool only)
- ChromaDB (replaced by pgvector)
- LangChain (custom chunking is intentional — better control, cleaner resume story)
- Tree-sitter AST parsing (marked as TODO in code chunker — regex is sufficient for now)
- Autonomous research as a product (scoped to personal use only)
