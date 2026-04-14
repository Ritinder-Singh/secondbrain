"""
pgvector-backed vector store.
Uses HNSW index for fast ANN search with cosine similarity.
"""
from typing import Optional

from db.connection import get_cursor
from core.llm import embed, embed_batch


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
                    SET content   = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata  = EXCLUDED.metadata
                """,
                (chunk_id, doc_id, chunk_index, text, vector, metadata or {}),
            )

    def add_batch(self, chunks: list[dict]) -> None:
        """
        Bulk insert chunks using a single embed_batch() call.
        Each chunk dict: {id, doc_id, chunk_index, text, metadata}
        """
        if not chunks:
            return

        # One HTTP call to Ollama for all texts
        texts = [c["text"] for c in chunks]
        vectors = embed_batch(texts)

        rows = [
            (
                chunk["id"],
                chunk["doc_id"],
                chunk["chunk_index"],
                chunk["text"],
                vector,
                chunk.get("metadata", {}),
            )
            for chunk, vector in zip(chunks, vectors)
        ]

        with get_cursor() as cur:
            cur.executemany(
                """
                INSERT INTO chunks (id, doc_id, chunk_index, content, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                    SET content   = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata  = EXCLUDED.metadata
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
        Returns list of {text, metadata, score, doc_id, chunk_id}.
        Optionally filter by metadata JSONB keys.
        """
        vector = embed(query)

        where_clause = ""
        filter_params: list = []

        if filter_metadata:
            conditions = [f"metadata->>'{key}' = %s" for key in filter_metadata]
            filter_params = list(filter_metadata.values())
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
        params = [vector] + filter_params + [vector, n_results]

        with get_cursor() as cur:
            cur.execute(sql, params)
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
            cur.execute("SELECT COUNT(*) AS n FROM chunks")
            return cur.fetchone()["n"]

    def upsert_document(self, doc: dict) -> None:
        """Insert or update a document record."""
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents
                    (id, title, source_type, source_url, file_path,
                     para_category, tags, metadata, vault_note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title      = EXCLUDED.title,
                    metadata   = EXCLUDED.metadata,
                    vault_note = EXCLUDED.vault_note
                """,
                (
                    doc["id"],
                    doc["title"],
                    doc["source_type"],
                    doc.get("source_url", ""),
                    doc.get("file_path", ""),
                    doc.get("para_category", "Resources"),
                    doc.get("tags", []),
                    doc.get("metadata", {}),
                    doc.get("vault_note", ""),
                ),
            )


vector_store = VectorStore()
