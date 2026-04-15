"""
Web search provider.
SearXNG (self-hosted, private) is the primary.
DuckDuckGo is the fallback when SearXNG is not configured.
"""
import requests
from config.settings import settings


def web_search(query: str, max_results: int = 8) -> list[dict]:
    """
    Search the web. Returns list of {title, url, snippet}.
    Uses SearXNG if SEARXNG_URL is set, otherwise DuckDuckGo.
    """
    if settings.SEARCH_PROVIDER == "searxng" and settings.SEARXNG_URL:
        try:
            return _searxng_search(query, max_results)
        except Exception as e:
            print(f"[WebSearch] SearXNG failed ({e}), falling back to DuckDuckGo")
    return _ddg_search(query, max_results)


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


def _ddg_search(query: str, n: int) -> list[dict]:
    from duckduckgo_search import DDGS
    results = []
    with DDGS() as ddg:
        for r in ddg.text(query, max_results=n):
            results.append({
                "title":   r.get("title", ""),
                "url":     r.get("href", ""),
                "snippet": r.get("body", ""),
            })
    return results
