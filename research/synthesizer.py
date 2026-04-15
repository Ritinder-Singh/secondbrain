"""
Research synthesizer.
Takes KB results, web results, and GitHub results and uses the LLM
to produce a structured Obsidian-ready research note in markdown.
"""
from core.llm import chat


_SYNTHESIS_PROMPT = """\
You are a research assistant. Synthesize the following sources into a structured, \
thorough research note in Obsidian markdown format.

Use this structure exactly:
## Summary
(2-3 sentence executive summary)

## Key Findings
(bullet points of the most important insights)

## From Knowledge Base
(insights from personal notes and saved content)

## Web Research
(insights from web search results, with source links)

## Related Code / Technical Details
(any code patterns, implementations, or technical specifics found)

## Questions & Next Steps
(open questions worth investigating further)

## Sources
(list all URLs referenced)

Be technical and precise. Use [[wikilinks]] for concepts worth linking in Obsidian.
Do not hallucinate — only use information present in the sources below.

---

TRIGGER: {trigger}

TOPICS: {topics}

KNOWLEDGE BASE:
{kb_context}

WEB RESULTS:
{web_context}

GITHUB / CODE:
{github_context}
"""


def synthesize(
    trigger: str,
    intent: dict,
    kb_results: dict,
    web_results: dict[str, list],
    github_results: list[dict],
) -> str:
    """
    Synthesize all research sources into a structured markdown note.

    Args:
        trigger: Original trigger text (voice note / query)
        intent: {topics, questions, intent} from _extract_intent
        kb_results: Output of core.rag.ask()
        web_results: {topic: [search results]} from web_search
        github_results: Chunks from GitHub-sourced KB entries

    Returns:
        Markdown string of the research note body
    """
    kb_context = _format_kb(kb_results)
    web_context = _format_web(web_results)
    github_context = _format_github(github_results)

    prompt = _SYNTHESIS_PROMPT.format(
        trigger=trigger,
        topics=", ".join(intent.get("topics", [])),
        kb_context=kb_context,
        web_context=web_context,
        github_context=github_context,
    )

    return chat([{"role": "user", "content": prompt}])


def _format_kb(kb_results: dict) -> str:
    chunks = kb_results.get("chunks", [])
    if not chunks:
        return "No relevant entries found in personal knowledge base."
    lines = []
    for c in chunks:
        title = c["metadata"].get("title", "?")
        lines.append(f"- **{title}**: {c['text'][:300].strip()}")
    return "\n".join(lines)


def _format_web(web_results: dict[str, list]) -> str:
    if not web_results:
        return "No web results."
    lines = []
    for topic, results in web_results.items():
        lines.append(f"### {topic}")
        for r in results[:4]:
            lines.append(f"- [{r['title']}]({r['url']}): {r['snippet'][:200]}")
    return "\n".join(lines)


def _format_github(github_results: list[dict]) -> str:
    if not github_results:
        return "No related code found in knowledge base."
    lines = []
    for c in github_results[:5]:
        src = c["metadata"].get("source_url") or c["metadata"].get("file_path", "?")
        lines.append(f"- `{src}`: {c['text'][:300].strip()}")
    return "\n".join(lines)
