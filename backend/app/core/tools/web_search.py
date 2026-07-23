from __future__ import annotations

import re
from typing import Any

import httpx

from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec

MAX_SEARCH_CHARS = 20_000
DDG_HTML_URL = "https://html.duckduckgo.com/html/"


def _decode_entities(s: str) -> str:
    return (
        s.replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#x27;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )


def _clean(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    return _decode_entities(text).strip()


async def _web_search(args: dict[str, Any], ctx: ToolContext) -> str:
    query = args.get("query", "")
    if not query:
        return "error: missing 'query'"
    try:
        max_results = int(args.get("max_results", 5))
    except (TypeError, ValueError):
        max_results = 5

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.post(
                DDG_HTML_URL,
                data={"q": query},
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                    )
                },
            )
            html = resp.text
    except Exception as e:  # noqa: BLE001
        return f"error searching the web: {e}"

    title_re = re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
    snippet_re = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)

    titles = title_re.findall(html)
    snippets = snippet_re.findall(html)

    results: list[str] = []
    for i, (href, title) in enumerate(titles[:max_results]):
        snippet = _clean(snippets[i]) if i < len(snippets) else ""
        results.append(f"{i + 1}. {_clean(title)}\n   {href}\n   {snippet}")

    if not results:
        return "No search results found"
    out = "\n\n".join(results)
    if len(out) > MAX_SEARCH_CHARS:
        out = out[:MAX_SEARCH_CHARS] + "\n...[truncated]"
    return out


register(
    ToolSpec(
        name="web_search",
        description=(
            "Search the web for a 'query' and return a list of results "
            "(title, url, snippet). Best-effort, keyless provider."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default 5)",
                },
            },
            "required": ["query"],
        },
        run=_web_search,
        risk_tier=RiskTier.network,
    )
)
