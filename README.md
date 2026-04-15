# Engram

Personal AI knowledge assistant — fully local, privacy-first.
Everything you save becomes searchable and chattable via a local LLM.

---

## Stack

| Layer | Choice |
|---|---|
| LLM | Ollama (`llama3.1:8b`) + Groq fallback |
| Embeddings | `nomic-embed-text` via Ollama — always local |
| Vector store | PostgreSQL + pgvector |
| Knowledge | Obsidian vault (PARA structure) |
| Interface | CLI, Voice |

---

## Setup

### 1. Prerequisites

- [Docker](https://docker.com) — for PostgreSQL
- [Ollama](https://ollama.com) — for local embeddings
- [uv](https://docs.astral.sh/uv/) — Python package manager

```bash
ollama pull nomic-embed-text   # embeddings (always local)
ollama pull llama3.1:8b        # chat (or use Groq — see below)
```

### 2. Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Start & initialize

```bash
docker compose up -d
uv sync
uv run python scripts/setup_db.py
uv run python -m interfaces.cli init
```

---

## Usage

```bash
engram add <url-or-file>        # ingest anything
engram ask "your question"      # RAG query
engram search "keyword"         # raw vector search
engram list                     # show ingested documents
engram stats                    # chunk count
engram sync                     # sync GitHub + Obsidian vault
engram github <owner/repo>      # ingest a specific repo
engram voice                    # start hands-free voice assistant
engram note                     # record + ingest a voice note
engram research "topic"         # research a topic (foreground)
engram research "topic" -b      # queue research in background
engram research --list          # list recent research tasks
```

---

## SearXNG Setup (Phase 3)

Run alongside Engram on your Raspberry Pi:

```bash
docker run -d \
  --name searxng \
  -p 8888:8080 \
  -v $(pwd)/searxng:/etc/searxng \
  searxng/searxng
```

Then set in `.env`:
```bash
SEARCH_PROVIDER=searxng
SEARXNG_URL=http://localhost:8888
```

---

## ntfy Setup (Phase 3) — Self-hosted

Push notifications to your phone when background research completes.

### 1. Run ntfy on your Raspberry Pi

Add to your `docker-compose.yml` (or run separately):

```yaml
ntfy:
  image: binwiederhier/ntfy
  container_name: ntfy
  command: serve
  ports:
    - "8080:80"
  volumes:
    - ./ntfy/cache:/var/cache/ntfy
    - ./ntfy/etc:/etc/ntfy
  restart: unless-stopped
```

Or standalone:

```bash
docker run -d \
  --name ntfy \
  -p 8080:80 \
  -v $(pwd)/ntfy/cache:/var/cache/ntfy \
  binwiederhier/ntfy \
  serve
```

### 2. Configure

Set in `.env`:

```bash
NTFY_URL=https://ntfy.yourdomain.com   # your self-hosted instance (or http://rpi-ip:8080)
NTFY_TOPIC=engram                      # topic name
```

### 3. Subscribe on your phone

1. Install the [ntfy app](https://ntfy.sh) (iOS / Android)
2. In the app: **Settings → Default server** → set to your instance URL
3. Subscribe to the `engram` topic

---

## GitHub Token Permissions

Two use cases, one token is fine if you give it both sets of permissions.

Go to: **GitHub → Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens**

### For ingesting repos / issues / PRs (`GITHUB_TOKEN`)

| Permission | Level |
|---|---|
| Contents | Read |
| Issues | Read |
| Pull requests | Read |
| Metadata | Read (auto-selected) |

Set **Repository access** to: _Only select repositories_ → pick the repos you want to ingest.

### For Obsidian vault git sync (`GITHUB_TOKEN` — same token, additional permission)

| Permission | Level |
|---|---|
| Contents | **Read and write** |

Set **Repository access** to include your vault repo (e.g. `username/engram-vault`).

### `.env` settings

```bash
GITHUB_TOKEN=github_pat_xxxx
GITHUB_USERNAME=your-username
VAULT_REPO_URL=https://github.com/your-username/engram-vault
```

> The vault repo URL is used for auto-committing notes after ingestion.
> Leave `VAULT_REPO_URL` empty to disable git sync (notes still written locally).

---

## LLM Configuration

### Local (default)

```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

### Groq (cloud fallback, free tier)

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_xxxx
GROQ_MODEL=llama-3.1-8b-instant
```

Embeddings **always** use local Ollama regardless of `LLM_PROVIDER`.

---

## Phases

| Phase | Status | Features |
|---|---|---|
| 1 | ✅ Done | Core RAG — ingest, chunk, embed, ask |
| 2 | 🔨 In progress | GitHub + Obsidian connectors, Voice |
| 3 | Planned | Research agent (voice note → vault note) |
| 4 | Planned | Hybrid search, reranking, Web UI |
