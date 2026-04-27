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


# ── Phase 2 commands ──────────────────────────────────────────────────────────

def cmd_github(args):
    from connectors.github.ingest import ingest_repo, ingest_all_repos
    if args.repo == "all":
        results = ingest_all_repos()
        for r in results:
            console.print(
                f"  [green]✓[/green] {r['repo']} — "
                f"{r['files_ingested']} files, {r['issues_ingested']} issues, {r['prs_ingested']} PRs"
            )
    else:
        r = ingest_repo(args.repo)
        console.print(
            f"[green]✓[/green] {r['repo']} — "
            f"{r['files_ingested']} files, {r['issues_ingested']} issues, {r['prs_ingested']} PRs"
        )


def cmd_sync(args):
    from connectors.registry import sync_all, get_connector
    if args.connector:
        result = get_connector(args.connector).sync(dry_run=args.dry_run)
        console.print(result)
    else:
        results = sync_all(dry_run=args.dry_run)
        for r in results:
            status = "[green]✓[/green]" if not r["errors"] else "[yellow]⚠[/yellow]"
            console.print(
                f"{status} {r['connector']} — "
                f"{r['ingested']} ingested, {r['skipped']} skipped, {len(r['errors'])} errors"
            )


def cmd_voice(args):
    from voice.assistant import voice_query_loop
    voice_query_loop()


def cmd_note(args):
    from voice.mic import ingest_voice_note
    result = ingest_voice_note()
    if result:
        console.print(f"\n[green]✓[/green] Voice note saved → {result['vault_note']}")


# ── Phase 3 commands ──────────────────────────────────────────────────────────

def cmd_research(args):
    import asyncio
    from research.agent import run_research
    from research.scheduler import queue_research, list_research_tasks

    if args.list:
        from research.scheduler import list_research_tasks
        tasks = list_research_tasks()
        if not tasks:
            console.print("[dim]No research tasks yet.[/dim]")
            return
        from rich.table import Table
        table = Table(title="Research Tasks")
        table.add_column("ID", style="dim", width=10)
        table.add_column("Title")
        table.add_column("Status", style="cyan")
        table.add_column("Created", style="dim")
        for t in tasks:
            table.add_row(
                t["id"][:8],
                t["title"],
                t["status"],
                str(t["created_at"])[:16] if t["created_at"] else "—",
            )
        console.print(table)
        return

    trigger = " ".join(args.trigger)

    if args.background:
        rid = asyncio.run(queue_research(trigger))
        console.print(f"[green]✓[/green] Research queued — ID: [bold]{rid[:8]}[/bold]")
        console.print("  Runs in background. You'll get a ntfy.sh notification when done.")
    else:
        console.print(f"\n[cyan]🔬 Researching:[/cyan] {trigger}\n")
        result = asyncio.run(run_research(trigger))
        console.print(f"\n[green]✓[/green] Research complete!")
        console.print(f"  Topics : {', '.join(result['topics'])}")
        console.print(f"  Note   : {result['vault_note']}\n")


# ── Phase 4 commands ──────────────────────────────────────────────────────────

def cmd_telegram(args):
    from interfaces.telegram.bot import run
    run()


def cmd_serve(args):
    import uvicorn
    console.print(f"[bold cyan]🌐 Starting Engram web UI on http://localhost:{args.port}[/bold cyan]")
    uvicorn.run(
        "interfaces.web.app:app",
        host="0.0.0.0",
        port=args.port,
        reload=args.reload,
    )


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

    # github
    a = sub.add_parser("github", help="Ingest a GitHub repo (or 'all')")
    a.add_argument("repo", help="owner/repo, repo name, or 'all'")

    # sync
    a = sub.add_parser("sync", help="Sync all connectors (GitHub + Obsidian vault)")
    a.add_argument("--connector", help="Run only a specific connector by name")
    a.add_argument("--dry-run", action="store_true", help="List what would be ingested")

    # voice
    sub.add_parser("voice", help="Start hands-free voice assistant")
    sub.add_parser("note",  help="Record + ingest a voice note")

    # research
    a = sub.add_parser("research", help="Run or queue a research task")
    a.add_argument("trigger", nargs="*", help="Topic or question to research")
    a.add_argument("--background", "-b", action="store_true",
                   help="Queue and run in background (ntfy.sh notification when done)")
    a.add_argument("--list", "-l", action="store_true", help="List recent research tasks")
    # telegram
    sub.add_parser("telegram", help="Start Telegram bot")

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
        "github":   cmd_github,
        "sync":     cmd_sync,
        "voice":    cmd_voice,
        "note":     cmd_note,
        "research": cmd_research,
        "telegram": cmd_telegram,
        "serve":    cmd_serve,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
