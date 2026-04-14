-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Documents table: one row per ingested source
CREATE TABLE IF NOT EXISTS documents (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    source_type   TEXT NOT NULL,          -- pdf | article | youtube | github | voice_note | etc.
    source_url    TEXT,
    file_path     TEXT,
    para_category TEXT DEFAULT 'Resources', -- Projects | Areas | Resources | Archive
    tags          TEXT[],
    metadata      JSONB DEFAULT '{}',
    vault_note    TEXT,                   -- path to Obsidian note
    ingested_at   TIMESTAMPTZ DEFAULT NOW(),
    summary       TEXT                    -- auto-generated summary (Phase 4)
);

-- Chunks table: one row per text chunk with its embedding
CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,         -- doc_id + __chunk_N
    doc_id      TEXT REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content     TEXT NOT NULL,
    embedding   vector(768),              -- nomic-embed-text = 768 dims
    metadata    JSONB DEFAULT '{}'
);

-- HNSW index for fast approximate nearest-neighbour search
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text search index (for BM25 hybrid search, Phase 4)
CREATE INDEX IF NOT EXISTS chunks_content_fts
    ON chunks USING gin(to_tsvector('english', content));

-- Conversations table: stores chat sessions
CREATE TABLE IF NOT EXISTS conversations (
    id         TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    title      TEXT,
    metadata   JSONB DEFAULT '{}'
);

-- Messages table: conversation history
CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,        -- user | assistant | system
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'   -- citations, chunk_ids, etc.
);

-- Research notes: AI-generated research from voice notes / tasks (Phase 3)
CREATE TABLE IF NOT EXISTS research_notes (
    id           TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    title        TEXT NOT NULL,
    trigger_text TEXT,
    content      TEXT NOT NULL,
    vault_note   TEXT,
    status       TEXT DEFAULT 'pending', -- pending | processing | complete | error
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    metadata     JSONB DEFAULT '{}'
);
