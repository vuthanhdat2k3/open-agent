# Web Search Revamp — Design Spec

Date: 2026-08-09
Status: Approved (Phase 1 scope)

## 1. Context

`web_search` exists in two independent places, both scraping DuckDuckGo's
HTML result page with regex:

- `backend/app/core/tools/web_search.py` — the agent-facing `web_search` tool.
- `customer-intelligence-mcp/server.py` (`_ddg`, `web_search`, `news_search`)
  — a second, separately-maintained copy used by the Customer Intelligence
  MCP service.

Problems:

- **Fragile**: a DuckDuckGo markup change breaks both copies independently,
  with no fallback provider.
- **No real content**: DDG's HTML result page has no snippet/date fields for
  most engines, so results are title + URL only.
- **Live bug**: `news_search` (`customer-intelligence-mcp/server.py:389-397`)
  filters results to `hit.get("published_date")`, but `_ddg()` never
  populates `published_date` — so `news_search` always returns
  `research_unavailable`, unconditionally.

Full research (repos/APIs/crawlers/social-platform search) is in the prior
conversation turn. Conclusion: build on **SearXNG**, a self-hosted
metasearch engine — free, no API key, aggregates multiple upstream engines
behind one JSON endpoint, and isolates us from any single engine's markup
changes.

## 2. Scope

**In scope (Phase 1 — this branch):**
- Add a `searxng` service to `docker-compose.yml` (internal-network only, no
  host port).
- New `SearxngProvider` used by both call sites, returning real
  title/url/excerpt/published_date from SearXNG's JSON API.
- DuckDuckGo HTML-scrape kept as an automatic fallback when `SEARXNG_URL` is
  unset or the SearXNG request fails — zero-config behavior is unchanged for
  anyone who hasn't rebuilt their compose stack.
- Fixes the `news_search` bug as a side effect of using a provider that
  actually returns dates.

**Out of scope (future phases, not started here):**
- Full-page crawling/rendering (Crawl4AI or similar) for reading whole pages
  instead of search snippets — separate concern from search, no current
  caller needs it.
- Platform-specific search (YouTube Data API, Telegram via Telethon, X/
  Facebook). Each has its own auth/quota/ToS model and no current feature
  requires them; adding speculative integrations now would be unused code.

## 3. Design

### 3.1 `SearxngProvider`

Both call sites already talk to a bare function (`_web_search` /
`_ddg`+`web_search`+`news_search`), not a shared library — SearXNG's JSON API
is simple enough (`GET /search?q=...&format=json`) that each call site gets
its own small client function rather than introducing a new shared package
for two ~15-line callers.

Response shape used from SearXNG JSON:
```json
{"results": [{"title": "...", "url": "...", "content": "...", "publishedDate": "2026-08-01T00:00:00"}]}
```
`content` → excerpt, `publishedDate` → published_date (present for engines
that support it, e.g. news-oriented engines — absent for plain web results,
which is correct/expected, not a bug).

### 3.2 Fallback

`SEARXNG_URL` empty or request raising/non-200 → fall back to the existing
DDG-HTML-regex path, unchanged. This keeps both tools working even if the
SearXNG container isn't running (e.g. a partial stack), and keeps the change
low-risk — worst case behavior reverts to exactly what exists today.

### 3.3 Config

New setting, defaulted so local/dev stacks that build from `docker-compose.yml`
get SearXNG automatically, but anything overriding `SEARXNG_URL=""` explicitly
gets the old DDG-only behavior:

- `backend/app/config.py`: `searxng_url: str = "http://searxng:8080"`
- `customer-intelligence-mcp/server.py`: `SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://searxng:8080")`
- `docker-compose.yml`: new `searxng` service (image `searxng/searxng`,
  `expose: ["8080"]`, no host port — internal callers only), plus
  `SEARXNG_URL` env passed to `api`, `worker`, `customer-intelligence-mcp`
  (all already reach other internal services by container DNS name, same
  pattern as `ci_mcp_url: http://customer-intelligence-mcp:8301/sse`).
- SearXNG needs `search.formats: [html, json]` in its settings (JSON is
  disabled by default upstream to discourage public scraping of public
  instances — irrelevant here since this instance is never exposed to a host
  port). Checked into `searxng/settings.yml`, mounted read-only.

## 4. Verification

- Unit tests using `httpx.MockTransport` (already a project dependency, no
  new package) for: SearXNG success path (real excerpt/date returned),
  SearXNG failure → DDG fallback path, `news_search` returning dated results
  instead of always erroring.
- `docker compose build customer-intelligence-mcp` — syntax/import sanity
  only; full live stack verification deferred (this session is already over
  its cost budget for interactive Docker+browser passes — see prior turns).
