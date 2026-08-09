# Web Search Revamp — Design Spec

Date: 2026-08-09
Status: Approved and implemented (Phase 1 + Phase 2, live-verified)

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

**In scope (Phase 2 — this branch, added after Phase 1 shipped):**
- `web_fetch` gets a self-hosted **crawl4ai** instance (`unclecode/crawl4ai`
  official Docker image) as a JS-rendering crawler, with the existing plain
  `httpx.get` kept as the automatic fallback — same fail-open pattern as
  Phase 1's SearXNG fallback.
- crawl4ai's REST API is bearer-token authenticated
  (`CRAWL4AI_API_TOKEN`/`CRAWLER_API_TOKEN`) — the image refuses a
  non-loopback bind without a token configured, and ships that way
  deliberately (open, unauthenticated headless-browser-as-a-service on the
  compose network would be a real SSRF/resource-abuse surface). Required via
  `docker-compose.yml`'s `${CRAWLER_API_TOKEN:?...}`, documented in
  `.env.example`.
- The existing `safe_url()` SSRF guard still runs before a URL is ever
  handed to the crawler — unchanged from the pre-existing `web_fetch`
  behavior, so the crawler only ever receives URLs that already resolved to
  a public address.

**Out of scope (not started here):**
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

Unit tests (`httpx.MockTransport`, no new dependency):
`backend/tests/test_web_search.py` (SearXNG success, SearXNG-failure→DDG
fallback, disabled→DDG), `backend/tests/test_web_fetch.py` (crawler success
+ both markdown response shapes, crawler-failure→plain-fetch fallback,
disabled→plain-fetch, blocked/SSRF URL never reaches the crawler).

Live verification (full stack rebuilt and brought up — `docker compose
build api worker customer-intelligence-mcp`, `up -d`), exercised through the
actual running containers, not mocks:

- `web_search` (agent tool) against a live query → real SearXNG results with
  titles/excerpts.
- `web_fetch` against `https://quotes.toscrape.com/js/` (a page whose content
  only exists after JS execution) → confirmed the crawler actually renders
  JS: real quote text came back, not an empty shell.
- `news_search` (customer-intelligence-mcp) — first live pass still returned
  `research_unavailable`. Root cause: SearXNG only returns `publishedDate`
  for `categories=news`-routed engines (e.g. Reuters), not general web
  results, and the original fix only appended the word "news" to the query
  text without setting that category. Fixed by threading a `category` param
  through `_searxng`/`_search` and having `news_search` request
  `categories=news` explicitly. Re-verified live: 3/3 dated Reuters results
  returned.
- crawl4ai container confirmed to refuse a plaintext non-loopback bind
  without `CRAWL4AI_API_TOKEN` set (its own default posture); after setting
  the token and mounting `crawler/config.yml` (host: 0.0.0.0, trusted_hosts
  pinned to the service name instead of `*`), confirmed reachable
  cross-container with the bearer token and rejecting the open-bind case.
