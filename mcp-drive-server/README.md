# mcp-drive-server — Google Drive MCP server for open-agent

A **stdio MCP server** that lets open-agent list and read files from a **Google
Drive** account. It plugs straight into open-agent's existing MCP client (which
spawns servers over stdio), so no backend changes are needed.

Tools exposed:

| Tool | Purpose |
|------|---------|
| `list_drive_files` | List files on the Drive (optionally filtered by name). |
| `get_drive_file` | Find a file by **id** or **name** and return its text (Markdown) for the chat. |
| `read_file_tool` | Alias of `get_drive_file`. |

File content is extracted with **MarkItDown** (pdf / docx / xlsx / pptx / csv /
txt / html / images → Markdown), so documents can be shown directly in the chat.

---

## 1. Prerequisites

- Python ≥ 3.10 (the same runtime open-agent's backend uses).
- A Google account with the files you want to access.

## 2. Google Cloud setup (one time)

1. Open [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials).
2. **Enable the API**: Library → search **"Google Drive API"** → Enable.
3. **Create OAuth consent**: OAuth consent screen → External → fill app name → add
   your Google account as a **test user** (needed while the app is in "Testing").
4. **Create credentials**: Credentials → **+ Create Credentials → OAuth client ID**
   → Application type **Desktop app** → Create → **Download JSON**.
5. Save that JSON as `credentials.json` inside this folder (`mcp-drive-server/`).

> The client ID must be a **Desktop app** (not Web/Service). The server uses the
> installed-app flow and opens your browser for a one-time consent.

## 3. Install

```bash
cd mcp-drive-server
python -m venv .venv
# Windows:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Authenticate (one time)

```bash
python auth.py
```

This opens a browser, asks you to consent, and writes `token.json` next to the
script. The server reuses that token. (If you deploy headless, instead set
`GOOGLE_SERVICE_ACCOUNT_PATH` to a service-account JSON — no browser needed.)

## 5. Register the server in open-agent

open-agent manages MCP servers through its REST API. Register the stdio server so
the backend can spawn it:

```bash
curl -X POST http://localhost:8000/api/mcp/servers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAGENT_API_KEY" \
  -d '{
    "name": "google-drive",
    "transport": "stdio",
    "command": "G:/open-agent/mcp-drive-server/.venv/Scripts/python.exe",
    "args": ["G:/open-agent/mcp-drive-server/server.py"],
    "env": {
      "GOOGLE_CREDENTIALS_PATH": "G:/open-agent/mcp-drive-server/credentials.json",
      "GOOGLE_TOKEN_PATH": "G:/open-agent/mcp-drive-server/token.json"
    }
  }'
```

- Adjust the `command`/`args` paths to your machine (use forward slashes or escaped
  backslashes).
- The `Authorization` header is only required if open-agent runs with an API key
  set; in localhost dev mode (no key) you can omit it.
- Optional env: `DRIVE_ROOT_FOLDER_ID` (restrict to one folder), `DRIVE_PAGE_SIZE`,
  `DRIVE_MAX_OUTPUT_CHARS`.

Then **connect** it (triggers discovery of the tools):

```bash
curl -X POST http://localhost:8000/api/mcp/servers/<server_id>/connect \
  -H "Authorization: Bearer $OPENAGENT_API_KEY"
```

The response tells you how many tools were discovered. After that, the agent can
call `list_drive_files` / `get_drive_file` directly from chat.

## 6. Usage in chat

- *"List my Drive files"* → `list_drive_files`
- *"Read the Q3 report from Drive"* → `get_drive_file(name="Q3 report")` →
  content rendered as Markdown in the chat.
- You can also pass an exact file id: `get_drive_file(file_id="1A2b3C...")`.

## 7. Configuration reference

| Env var | Default | Meaning |
|---------|---------|---------|
| `GOOGLE_CREDENTIALS_PATH` | `credentials.json` | OAuth client_secret JSON |
| `GOOGLE_TOKEN_PATH` | `token.json` | Cached OAuth token |
| `GOOGLE_SERVICE_ACCOUNT_PATH` | – | Service-account JSON (headless) |
| `DRIVE_ROOT_FOLDER_ID` | – | Restrict all ops to this folder |
| `DRIVE_PAGE_SIZE` | `20` | Default list page size |
| `DRIVE_MAX_OUTPUT_CHARS` | `40000` | Truncate file text beyond this |

## 8. Files

```
mcp-drive-server/
├── server.py          # the MCP server (FastMCP, stdio)
├── auth.py            # one-time browser OAuth helper
├── requirements.txt   # pinned deps
├── pyproject.toml     # same deps, PEP 621
├── .env.example       # env template
├── credentials.json   # (you create) OAuth client secret
└── token.json         # (auth.py creates) cached token
```

## 9. Running in Docker (containerized, SSE)

The server can run as a container exposing the **SSE** transport on port `8001`.
open-agent then connects over the network (`transport: "sse"`) — no need to spawn
`docker` as a command.

### Build

```bash
cd mcp-drive-server
docker build -t open-agent-drive-mcp:latest .
```

### Run

Secrets are **mounted read-only** from the host; they are never baked into the image.

```bash
docker run -d --name drive-mcp -p 8001:8001 `
  -v %CD%/credentials.json:/app/credentials.json:ro `
  -v %CD%/token.json:/app/token.json:ro `
  open-agent-drive-mcp:latest
```

Or with Compose (already provided as `docker-compose.yml`):

```bash
docker compose up -d
```

Check it came up:

```bash
docker logs drive-mcp   # expect: Uvicorn running on http://0.0.0.0:8001
```

### Register in open-agent (SSE transport)

```bash
curl -X POST http://localhost:8000/api/mcp/servers \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAGENT_API_KEY" \
  -d '{"name":"google-drive","transport":"sse","url":"http://localhost:8001/sse"}'
```

Then connect to discover tools:

```bash
curl -X POST http://localhost:8000/api/mcp/servers/<id>/connect \
  -H "Authorization: Bearer $OPENAGENT_API_KEY"
```

### Notes
- `token.json` must already exist (run `python auth.py` on the host **once** before
  building/running). The container only reuses it.
- When the token expires, the server refreshes it headlessly using the saved
  `refresh_token` (the consent URL requested `access_type=offline`), so no browser
  is needed inside the container.
- The image contains **no secrets** — only code + dependencies.

