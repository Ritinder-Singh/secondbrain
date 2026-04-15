"""
Cross-encoder reranker using FlashRank.
Reranks retrieved chunks by relevance score from a lightweight MS-MARCO model.

Model: ms-marco-MiniLM-L-12-v2 (~34MB, CPU-friendly, no GPU needed)
Falls back to original order if flashrank is not installed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

_ranker = None


def _get_ranker():
    global _ranker
    if _ranker is None:
        try:
            from flashrank import Ranker
            _ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="/tmp/flashrank")
        except ImportError:
            _ranker = None
    return _ranker


def rerank_chunks(query: str, chunks: list[dict], top_n: int = None) -> list[dict]:
    """
    Rerank chunks by cross-encoder relevance to query.

    Args:
        query: The user's original search query
        chunks: List of {text, metadata, score, doc_id, chunk_id} from retrieval
        top_n: Return top N chunks after reranking. If None, returns all reranked.

    Returns:
        Chunks sorted by rerank score descending, with 'score' updated to rerank score.
    """
    ranker = _get_ranker()

    if ranker is None:
        # flashrank not installed — return original order unchanged
        return chunks[:top_n] if top_n else chunks

    try:
        from flashrank import RerankRequest

        passages = [
            {"id": i, "text": chunk["text"]}
            for i, chunk in enumerate(chunks)
        ]
        request = RerankRequest(query=query, passages=passages)
        results = ranker.rerank(request)

        # results is a list of dicts with 'id' (original index) and 'score'
        scored = []
        for r in results:
            chunk = dict(chunks[r["id"]])
            chunk["score"] = float(r["score"])
            scored.append(chunk)

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_n] if top_n else scored

    except Exception:
        # Any rerank failure — degrade gracefully
        return chunks[:top_n] if top_n else chunks
