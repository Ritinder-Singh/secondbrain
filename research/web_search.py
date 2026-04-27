"""
Web search via self-hosted SearXNG only. Strictly offline.
Set SEARXNG_URL in .env to enable. Leave blank to disable research features.
"""
import requests
from config.settings import settings


def web_search(query: str, max_results: int = 8) -> list[dict]:
    """Search via local SearXNG. Raises RuntimeError if SEARXNG_URL is not configured."""
    if not settings.SEARXNG_URL:
        raise RuntimeError(
            "Web search is disabled. Set SEARXNG_URL in .env to point at your "
            "self-hosted SearXNG instance."
        )
    return _searxng_search(query, max_results)


def _searxng_search(query: str, n: int) -> list[dict]:
    resp = requests.get(
        f"{settings.SEARXNG_URL}/search",
        params={"q": query, "format": "json", "categories": "general"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {
            "title":   r.get("title", ""),
            "url":     r.get("url", ""),
            "snippet": r.get("content", ""),
        }
        for r in data.get("results", [])[:n]
    ]
