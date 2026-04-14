"""
Engram CLI — Phase 1 commands.
Usage: uv run python -m interfaces.cli <command>
       or: engram <command>  (after uv install)
"""
import argparse

from rich.console import Console
from rich.table import Table

console = Console()


# ── Phase 1 commands ──────────────────────────────────────────────────────────

def cmd_init(args):
    from vault.writer import setup_vault
    from scripts.setup_db import setup
    console.print("\n[bold cyan]🧠 Initializing Engram...[/bold cyan]")
    setup()
    setup_vault()
    console.print("\n[green]✓ Done.[/green] Next steps:")
    console.print("  ollama pull llama3.1:8b")
    console.print("  ollama pull nomic-embed-text")
    console.print("  engram add <url-or-file>\n")


def cmd_add(args):
    from ingestion.pipeline import ingest
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
    with console.status(f"[cyan]Ingesting {args.source}...[/cyan]"):
        result = ingest(args.source, para_category=args.para, tags=tags)
    console.print(
        f"[green]✓[/green] [bold]{result['title']}[/bold] — "
        f"{result['chunks']} chunks → {result['vault_note']}"
    )


def cmd_ask(args):
    from core.rag import ask
    query = " ".join(args.query)
    result = ask(
        query,
        n_results=args.n,
        use_hybrid=args.hybrid,
        rerank=args.rerank,
    )
    console.print()
    console.print(result["answer"])
    if result["citations"]:
        console.print("\n[dim]── Sources ─────────────────────────────[/dim]")
        for c in result["citations"]:
            console.print(
                f"  [dim]\\[{c['index']}] {c['title']} "
                f"({c['source_type']}) — {c['score']:.2f}[/dim]"
            )
    console.print()


def cmd_search(args):
    from core.vector_store import vector_store
    query = " ".join(args.query)
    with console.status("[cyan]Searching...[/cyan]"):
        results = vector_store.search(query, n_results=args.n)

    for i, r in enumerate(results, 1):
        console.print(
            f"[bold]\\[{i}][/bold] {r['metadata'].get('title', '?')} "
            f"[dim]({r['metadata'].get('source_type', '?')}) — {r['score']:.2f}[/dim]"
        )
        console.print(f"    [dim]{r['text'][:150].strip()}...[/dim]\n")


def cmd_list(args):
    from db.connection import get_cursor
    with get_cursor() as cur:
        cur.execute(
            "SELECT title, source_type, ingested_at FROM documents ORDER BY ingested_at DESC LIMIT 50"
        )
        rows = cur.fetchall()

    table = Table(title=f"Knowledge Base ({len(rows)} documents)")
    table.add_column("Title", style="bold")
    table.add_column("Type", style="cyan")
    table.add_column("Ingested", style="dim")

    for r in rows:
        table.add_row(
            r["title"],
            r["source_type"],
            str(r["ingested_at"])[:10] if r["ingested_at"] else "—",
        )
    console.print(table)


def cmd_stats(args):
    from core.vector_store import vector_store
    from db.connection import get_cursor

    total_chunks = vector_store.count()
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM documents")
        total_docs = cur.fetchone()["n"]

    console.print(f"\n[bold]Engram Knowledge Base[/bold]")
    console.print(f"  Documents : [cyan]{total_docs}[/cyan]")
    console.print(f"  Chunks    : [cyan]{total_chunks}[/cyan]")
    console.print()


# ── Phase 2+ stubs (not yet implemented) ────────────────────────────────────

def _not_implemented(name: str):
    def _cmd(args):
        console.print(f"[yellow]{name} is implemented in Phase 2.[/yellow]")
    return _cmd


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        prog="engram",
        description="Personal AI knowledge assistant",
    )
    sub = p.add_subparsers(dest="command", metavar="command")

    # init
    sub.add_parser("init", help="Setup database and Obsidian vault")

    # add
    a = sub.add_parser("add", help="Ingest a source (URL, file, YouTube)")
    a.add_argument("source", help="URL or file path to ingest")
    a.add_argument("--para", default="Resources",
                   choices=["Projects", "Areas", "Resources", "Archive"],
                   help="PARA category (default: Resources)")
    a.add_argument("--tags", default="", help="Comma-separated tags")

    # ask
    a = sub.add_parser("ask", help="Ask a question (RAG query)")
    a.add_argument("query", nargs="+", help="Your question")
    a.add_argument("-n", type=int, default=5, help="Chunks to retrieve (default: 5)")
    a.add_argument("--hybrid", action="store_true", help="Use hybrid BM25+semantic search (Phase 4)")
    a.add_argument("--rerank", action="store_true", help="Re-rank results (Phase 4)")

    # search
    a = sub.add_parser("search", help="Raw vector search (no LLM)")
    a.add_argument("query", nargs="+", help="Search query")
    a.add_argument("-n", type=int, default=5, help="Results to return (default: 5)")

    # list
    sub.add_parser("list", help="List ingested documents")

    # stats
    sub.add_parser("stats", help="Show knowledge base stats")

    # Phase 2+ stubs
    sub.add_parser("voice",    help="Voice assistant (Phase 2)")
    sub.add_parser("note",     help="Ingest a voice note (Phase 2)")
    sub.add_parser("sync",     help="Sync all connectors (Phase 2)")
    sub.add_parser("telegram", help="Start Telegram bot (Phase 2)")
    sub.add_parser("research", help="Queue a research task (Phase 3)")
    a = sub.add_parser("serve", help="Start web UI (Phase 4)")
    a.add_argument("--port", type=int, default=8000)
    a.add_argument("--reload", action="store_true")

    args = p.parse_args()

    dispatch = {
        "init":     cmd_init,
        "add":      cmd_add,
        "ask":      cmd_ask,
        "search":   cmd_search,
        "list":     cmd_list,
        "stats":    cmd_stats,
        "voice":    _not_implemented("voice"),
        "note":     _not_implemented("note"),
        "sync":     _not_implemented("sync"),
        "telegram": _not_implemented("telegram"),
        "research": _not_implemented("research"),
        "serve":    _not_implemented("serve"),
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
