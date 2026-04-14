"""
RAG Pipeline: query → retrieve → format context → generate answer.
Supports streaming, conversation history, and metadata filtering.
"""
from typing import Optional, Generator

from core.vector_store import vector_store
from core.llm import chat
from core.memory import save_message, get_history

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
    use_hybrid: bool = False,   # Phase 4: BM25 + semantic
    rerank: bool = False,       # Phase 4: cross-encoder reranking
) -> dict | Generator:
    """
    Run a RAG query against the knowledge base.

    Args:
        query: The user's question
        conversation_id: Optional — attaches conversation history and saves turns
        filter_metadata: Optional JSONB metadata filter for retrieval
        stream: If True, returns a generator of text chunks instead of a full dict
        n_results: Number of chunks to retrieve
        use_hybrid: Phase 4 flag — BM25 + semantic hybrid search
        rerank: Phase 4 flag — cross-encoder re-ranking

    Returns:
        dict {answer, citations, chunks} or a Generator when stream=True
    """
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
    messages.append({
        "role": "user",
        "content": f"Context:\n\n{context}\n\nQuestion: {query}",
    })

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
            "index":       i,
            "title":       c["metadata"].get("title", "Untitled"),
            "source_type": c["metadata"].get("source_type", "unknown"),
            "source_url":  c["metadata"].get("source_url", ""),
            "file_path":   c["metadata"].get("file_path", ""),
            "score":       c.get("score", 0),
        }
        for i, c in enumerate(chunks, 1)
    ]
