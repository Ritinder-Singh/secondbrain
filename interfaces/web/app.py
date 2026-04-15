"""
Engram FastAPI web UI — Phase 4.
Serves a chat interface and REST API for the knowledge base.

Start: uvicorn interfaces.web.app:app --reload --port 8000
Or:    engram serve
"""
import asyncio
import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Engram", description="Personal AI knowledge assistant", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files if directory exists
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# ── Request / Response models ──────────────────────────────────────────────────

class AskRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None
    n_results: int = 5
    use_hybrid: bool = False
    rerank: bool = False
    stream: bool = False


class IngestRequest(BaseModel):
    source: str                        # URL or file path
    para_category: str = "Resources"
    tags: list[str] = []


class AskResponse(BaseModel):
    answer: str
    citations: list[dict]
    conversation_id: Optional[str] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the chat UI."""
    return _chat_html()


@app.post("/ask")
async def ask_endpoint(req: AskRequest):
    """
    RAG query endpoint.
    Returns JSON normally, or SSE stream if req.stream=True.
    """
    from core.rag import ask

    if req.stream:
        return StreamingResponse(
            _stream_ask(req),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    result = await asyncio.to_thread(
        ask,
        req.query,
        req.conversation_id,
        None,
        False,
        req.n_results,
        req.use_hybrid,
        req.rerank,
    )
    return AskResponse(
        answer=result["answer"],
        citations=result["citations"],
        conversation_id=req.conversation_id,
    )


@app.post("/ingest")
async def ingest_endpoint(req: IngestRequest):
    """Ingest a URL or file path into the knowledge base."""
    from ingestion.pipeline import ingest

    try:
        result = await asyncio.to_thread(
            ingest, req.source, req.para_category, req.tags
        )
        return {
            "success": True,
            "title": result["title"],
            "chunks": result["chunks"],
            "vault_note": result["vault_note"],
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/documents")
async def list_documents(limit: int = 50):
    """List recently ingested documents."""
    from db.connection import get_cursor

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, title, source_type, source_url, para_category, tags, ingested_at
            FROM documents
            ORDER BY ingested_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()

    return {
        "documents": [
            {
                "id": r["id"],
                "title": r["title"],
                "source_type": r["source_type"],
                "source_url": r["source_url"] or "",
                "para_category": r["para_category"],
                "tags": r["tags"] or [],
                "ingested_at": str(r["ingested_at"])[:10] if r["ingested_at"] else None,
            }
            for r in rows
        ]
    }


@app.get("/stats")
async def stats():
    """Return knowledge base statistics."""
    from core.vector_store import vector_store
    from db.connection import get_cursor

    total_chunks = await asyncio.to_thread(vector_store.count)
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM documents")
        total_docs = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM research_notes WHERE status = 'complete'")
        total_research = cur.fetchone()["n"]

    return {
        "documents": total_docs,
        "chunks": total_chunks,
        "research_notes": total_research,
    }


@app.get("/research")
async def list_research(limit: int = 20):
    """List recent research tasks."""
    from research.scheduler import list_research_tasks

    tasks = await asyncio.to_thread(list_research_tasks, limit)
    return {
        "tasks": [
            {
                "id": t["id"],
                "title": t["title"],
                "status": t["status"],
                "trigger_text": t["trigger_text"],
                "vault_note": t["vault_note"] or "",
                "created_at": str(t["created_at"])[:16] if t["created_at"] else None,
                "completed_at": str(t["completed_at"])[:16] if t["completed_at"] else None,
            }
            for t in tasks
        ]
    }


@app.post("/research")
async def trigger_research(body: dict):
    """Queue a background research task."""
    trigger = body.get("trigger", "")
    if not trigger:
        raise HTTPException(status_code=400, detail="trigger text required")

    from research.scheduler import queue_research
    rid = await queue_research(trigger)
    return {"research_id": rid, "status": "queued"}


@app.get("/conversations")
async def list_conversations():
    """List recent conversations."""
    from core.memory import list_conversations
    convos = await asyncio.to_thread(list_conversations)
    return {"conversations": convos}


# ── Streaming helper ───────────────────────────────────────────────────────────

async def _stream_ask(req: AskRequest):
    """
    SSE generator for streaming RAG responses.
    Emits: data: {"token": "..."}\n\n per chunk, then data: {"done": true}\n\n
    """
    from core.rag import ask

    gen = await asyncio.to_thread(
        ask,
        req.query,
        req.conversation_id,
        None,
        True,           # stream=True
        req.n_results,
        req.use_hybrid,
        req.rerank,
    )

    for token in gen:
        payload = json.dumps({"token": token})
        yield f"data: {payload}\n\n"

    yield f"data: {json.dumps({'done': True})}\n\n"


# ── Embedded HTML UI ───────────────────────────────────────────────────────────

def _chat_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Engram</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f0f0f; color: #e0e0e0; height: 100vh; display: flex; flex-direction: column; }
  header { padding: 16px 24px; border-bottom: 1px solid #2a2a2a;
           display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 18px; font-weight: 600; color: #fff; }
  header span { font-size: 13px; color: #666; }
  #chat { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
  .msg { max-width: 800px; width: 100%; }
  .msg.user { align-self: flex-end; }
  .msg.assistant { align-self: flex-start; }
  .bubble { padding: 12px 16px; border-radius: 12px; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
  .msg.user .bubble { background: #1a3a5c; color: #e0e0e0; border-bottom-right-radius: 4px; }
  .msg.assistant .bubble { background: #1e1e1e; color: #e0e0e0; border-bottom-left-radius: 4px; border: 1px solid #2a2a2a; }
  .citations { font-size: 12px; color: #555; margin-top: 6px; padding: 0 4px; }
  #inputbar { padding: 16px 24px; border-top: 1px solid #2a2a2a; display: flex; gap: 10px; }
  #q { flex: 1; background: #1e1e1e; border: 1px solid #2a2a2a; border-radius: 8px;
       padding: 10px 14px; color: #e0e0e0; font-size: 14px; resize: none; min-height: 44px; max-height: 120px; }
  #q:focus { outline: none; border-color: #3a7bd5; }
  button { background: #3a7bd5; color: #fff; border: none; border-radius: 8px;
           padding: 10px 18px; font-size: 14px; cursor: pointer; white-space: nowrap; }
  button:hover { background: #2e6bc4; }
  button:disabled { background: #2a2a2a; color: #555; cursor: default; }
  .opts { display: flex; gap: 16px; align-items: center; padding: 0 24px 8px; font-size: 13px; color: #666; }
  .opts label { display: flex; align-items: center; gap: 6px; cursor: pointer; }
  .opts input[type=checkbox] { accent-color: #3a7bd5; }
  .typing { display: inline-block; }
  .typing::after { content: '▋'; animation: blink 1s step-end infinite; }
  @keyframes blink { 50% { opacity: 0; } }
</style>
</head>
<body>
<header>
  <h1>🧠 Engram</h1>
  <span>Personal AI knowledge assistant</span>
</header>
<div id="chat"></div>
<div class="opts">
  <label><input type="checkbox" id="hybridCk"> Hybrid search</label>
  <label><input type="checkbox" id="rerankCk"> Rerank</label>
  <label>Results: <input type="number" id="nResults" value="5" min="1" max="20" style="width:50px;background:#1e1e1e;border:1px solid #2a2a2a;color:#e0e0e0;border-radius:4px;padding:2px 6px;"></label>
</div>
<div id="inputbar">
  <textarea id="q" placeholder="Ask anything..." rows="1"></textarea>
  <button id="send" onclick="sendMsg()">Send</button>
</div>
<script>
const chat = document.getElementById('chat');
const qEl = document.getElementById('q');
const sendBtn = document.getElementById('send');

qEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); }
});

function addMsg(role, text, citations) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  div.appendChild(bubble);
  if (citations && citations.length) {
    const cDiv = document.createElement('div');
    cDiv.className = 'citations';
    cDiv.textContent = citations.map(c => `[${c.index}] ${c.title} (${c.source_type})`).join(' · ');
    div.appendChild(cDiv);
  }
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return bubble;
}

async function sendMsg() {
  const q = qEl.value.trim();
  if (!q) return;
  qEl.value = '';
  sendBtn.disabled = true;

  addMsg('user', q, null);

  const bubble = addMsg('assistant', '', null);
  bubble.classList.add('typing');

  const body = {
    query: q,
    n_results: parseInt(document.getElementById('nResults').value) || 5,
    use_hybrid: document.getElementById('hybridCk').checked,
    rerank: document.getElementById('rerankCk').checked,
    stream: true,
  };

  try {
    const res = await fetch('/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    let fullText = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\\n');
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = JSON.parse(line.slice(6));
        if (data.done) break;
        if (data.token) {
          fullText += data.token;
          bubble.textContent = fullText;
          chat.scrollTop = chat.scrollHeight;
        }
      }
    }

    bubble.classList.remove('typing');
  } catch (e) {
    bubble.textContent = 'Error: ' + e.message;
    bubble.classList.remove('typing');
  }

  sendBtn.disabled = false;
  qEl.focus();
}
</script>
</body>
</html>"""
