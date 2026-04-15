"""
Hybrid search: BM25 (PostgreSQL full-text) + pgvector cosine similarity.
Results merged via Reciprocal Rank Fusion (RRF).

RRF formula: score(d) = Σ 1 / (k + rank_i(d))
where k=60 is the standard constant that dampens the impact of high ranks.
"""
from db.connection import get_cursor
from core.llm import embed


_RRF_K = 60


def hybrid_search(
    query: str,
    n_results: int = 5,
    semantic_weight: float = 1.0,
    bm25_weight: float = 1.0,
) -> list[dict]:
    """
    Combine BM25 full-text and semantic vector search via RRF.

    Args:
        query: The search query
        n_results: Number of final results to return
        semantic_weight: Multiplier for semantic RRF scores
        bm25_weight: Multiplier for BM25 RRF scores

    Returns:
        List of {text, metadata, score, doc_id, chunk_id} sorted by RRF score desc
    """
    # Pull more candidates from each source so RRF has room to rerank
    pool = max(n_results * 3, 20)

    semantic_hits = _semantic_search(query, pool)
    bm25_hits = _bm25_search(query, pool)

    return _rrf_merge(
        semantic_hits, bm25_hits,
        n_results=n_results,
        semantic_weight=semantic_weight,
        bm25_weight=bm25_weight,
    )


def _semantic_search(query: str, n_results: int) -> list[dict]:
    """Standard pgvector cosine similarity search."""
    vector = embed(query)
    sql = """
        SELECT
            id,
            doc_id,
            content,
            metadata,
            1 - (embedding <=> %s::vector) AS score
        FROM chunks
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (vector, vector, n_results))
        rows = cur.fetchall()

    return [
        {
            "chunk_id": row["id"],
            "doc_id": row["doc_id"],
            "text": row["content"],
            "metadata": row["metadata"],
            "score": float(row["score"]),
        }
        for row in rows
    ]


def _bm25_search(query: str, n_results: int) -> list[dict]:
    """
    PostgreSQL full-text search using tsvector + GIN index.
    Falls back gracefully to empty list if query produces no ts_query.
    """
    sql = """
        SELECT
            id,
            doc_id,
            content,
            metadata,
            ts_rank_cd(
                to_tsvector('english', content),
                plainto_tsquery('english', %s)
            ) AS score
        FROM chunks
        WHERE to_tsvector('english', content) @@ plainto_tsquery('english', %s)
        ORDER BY score DESC
        LIMIT %s
    """
    try:
        with get_cursor() as cur:
            cur.execute(sql, (query, query, n_results))
            rows = cur.fetchall()
    except Exception:
        return []

    return [
        {
            "chunk_id": row["id"],
            "doc_id": row["doc_id"],
            "text": row["content"],
            "metadata": row["metadata"],
            "score": float(row["score"]),
        }
        for row in rows
    ]


def _rrf_merge(
    semantic_hits: list[dict],
    bm25_hits: list[dict],
    n_results: int,
    semantic_weight: float,
    bm25_weight: float,
) -> list[dict]:
    """Merge two ranked lists via Reciprocal Rank Fusion."""
    scores: dict[str, float] = {}
    chunks: dict[str, dict] = {}

    for rank, hit in enumerate(semantic_hits, start=1):
        cid = hit["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + semantic_weight / (_RRF_K + rank)
        chunks[cid] = hit

    for rank, hit in enumerate(bm25_hits, start=1):
        cid = hit["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + bm25_weight / (_RRF_K + rank)
        if cid not in chunks:
            chunks[cid] = hit

    sorted_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)

    results = []
    for cid in sorted_ids[:n_results]:
        hit = dict(chunks[cid])
        hit["score"] = scores[cid]
        results.append(hit)

    return results
