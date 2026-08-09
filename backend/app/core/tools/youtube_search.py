from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings
from app.core.tools.registry import register
from app.core.tools.risk_tier import RiskTier
from app.core.tools.types import ToolContext, ToolSpec

MAX_SEARCH_CHARS = 20_000
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


async def _youtube_search(args: dict[str, Any], ctx: ToolContext) -> str:
    query = args.get("query", "")
    if not query:
        return "error: missing 'query'"
    try:
        max_results = int(args.get("max_results", 5))
    except (TypeError, ValueError):
        max_results = 5
    max_results = max(1, min(max_results, 10))

    api_key = get_settings().youtube_api_key
    if not api_key:
        return "error: YouTube search is not configured (missing youtube_api_key)"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                YOUTUBE_SEARCH_URL,
                params={
                    "part": "snippet",
                    "q": query,
                    "type": "video",
                    "maxResults": max_results,
                    "key": api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        return f"error searching YouTube: {e}"

    items = data.get("items", [])
    if not items:
        return "No search results found"

    results: list[str] = []
    for i, item in enumerate(items):
        video_id = item.get("id", {}).get("videoId", "")
        snippet = item.get("snippet", {})
        title = snippet.get("title", "")
        channel = snippet.get("channelTitle", "")
        published = snippet.get("publishedAt", "")
        description = snippet.get("description", "")
        url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
        line = f"{i + 1}. {title}\n   {url}\n   channel: {channel} | published: {published}"
        if description:
            line += f"\n   {description}"
        results.append(line)

    out = "\n\n".join(results)
    if len(out) > MAX_SEARCH_CHARS:
        out = out[:MAX_SEARCH_CHARS] + "\n...[truncated]"
    return out


register(
    ToolSpec(
        name="youtube_search",
        description=(
            "Search YouTube for videos matching a 'query' and return a list of results "
            "(title, url, channel, published date, description). Requires a configured "
            "YouTube Data API key; returns an error if unavailable."
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
                    "description": "Maximum number of results (default 5, max 10)",
                },
            },
            "required": ["query"],
        },
        run=_youtube_search,
        risk_tier=RiskTier.network,
    )
)
