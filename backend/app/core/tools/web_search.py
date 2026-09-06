from __future__ import annotations

import re
from typing import Any

import httpx

from app.config import get_settings
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


def _format_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "No search results found"
    lines: list[str] = []
    for i, r in enumerate(results):
        line = f"{i + 1}. {r['title']}\n   {r['url']}"
        if r.get("excerpt"):
            line += f"\n   {r['excerpt']}"
        if r.get("published_date"):
            line += f"\n   published: {r['published_date']}"
        lines.append(line)
    out = "\n\n".join(lines)
    if len(out) > MAX_SEARCH_CHARS:
        out = out[:MAX_SEARCH_CHARS] + "\n...[truncated]"
    return out


async def _searxng_search(searxng_url: str, query: str, max_results: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{searxng_url.rstrip('/')}/search",
            params={"q": query, "format": "json"},
        )
        resp.raise_for_status()
        data = resp.json()
    results = []
    for item in data.get("results", [])[:max_results]:
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "excerpt": item.get("content", ""),
                "published_date": item.get("publishedDate"),
            }
        )
    return results


async def _ddg_search(query: str, max_results: int) -> list[dict[str, Any]]:
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

    title_re = re.compile(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
    snippet_re = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)

    titles = title_re.findall(html)
    snippets = snippet_re.findall(html)

    results = []
    for i, (href, title) in enumerate(titles[:max_results]):
        snippet = _clean(snippets[i]) if i < len(snippets) else ""
        results.append({"title": _clean(title), "url": href, "excerpt": snippet, "published_date": None})
    return results


TINYFISH_SEARCH_URL = "https://api.search.tinyfish.ai"


async def _tinyfish_search(api_key: str, query: str, max_results: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            TINYFISH_SEARCH_URL,
            params={"query": query},
            headers={"X-API-Key": api_key},
        )
        resp.raise_for_status()
        data = resp.json()
    results = []
    for item in data.get("results", [])[:max_results]:
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "excerpt": item.get("snippet", ""),
                "published_date": None,
            }
        )
    return results


async def _web_search(args: dict[str, Any], ctx: ToolContext) -> str:
    query = args.get("query", "")
    if not query:
        return "error: missing 'query'"
    try:
        max_results = int(args.get("max_results", 5))
    except (TypeError, ValueError):
        max_results = 5

    if ctx.emit:
        await ctx.emit({"stage": "searching", "query": query, "line": f"Searching web for: '{query}'...\n"})

    settings = get_settings()
    searxng_url = settings.searxng_url
    if searxng_url:
        try:
            results = await _searxng_search(searxng_url, query, max_results)
            if results:
                if ctx.emit:
                    await ctx.emit({"stage": "found", "count": len(results), "line": f"Found {len(results)} results via SearXNG\n"})
                return _format_results(results)
            # SearXNG answers with HTTP 200 and an empty result list when
            # every engine it aggregates is rate-limited/CAPTCHA'd — that's
            # not an exception, so it silently skipped the fallback below
            # in exactly the case that needs it most. Fall through instead
            # of returning "No search results found" for a query that a
            # differently-fingerprinted direct request might still answer.
        except Exception:  # noqa: BLE001
            pass  # fall through to the DDG fallback below

    ddg_error: Exception | None = None
    try:
        results = await _ddg_search(query, max_results)
        if results:
            if ctx.emit:
                await ctx.emit({"stage": "found", "count": len(results), "line": f"Found {len(results)} results via DuckDuckGo\n"})
            return _format_results(results)
    except Exception as e:  # noqa: BLE001
        ddg_error = e

    if settings.tinyfish_api_key:
        try:
            results = await _tinyfish_search(settings.tinyfish_api_key, query, max_results)
            if ctx.emit:
                await ctx.emit({"stage": "found", "count": len(results), "line": f"Found {len(results)} results via TinyFish\n"})
            return _format_results(results)
        except Exception:  # noqa: BLE001
            pass  # every tier exhausted; fall through to the summary below

    if ddg_error is not None:
        return f"error searching the web: {ddg_error}"
    return "No search results found"


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
