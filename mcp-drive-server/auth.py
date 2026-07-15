"""One-time Google Drive OAuth helper for the drive-mcp server.

Run this once (in the same environment the MCP server will use) to perform the
browser-based OAuth consent and cache the token to GOOGLE_TOKEN_PATH. The MCP
server then reuses that token and never blocks on a login prompt.

    python auth.py

Environment:
    GOOGLE_CREDENTIALS_PATH  path to the OAuth client_secret JSON (default credentials.json)
    GOOGLE_TOKEN_PATH        where to write the cached token (default token.json)
"""

from __future__ import annotations

import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPE = "https://www.googleapis.com/auth/drive.readonly"
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", "token.json")


def main() -> None:
    if not Path(CREDENTIALS_PATH).exists():
        raise SystemExit(
            f"Missing {CREDENTIALS_PATH}.\n"
            "1) Go to Google Cloud Console -> APIs & Services -> Credentials\n"
            "2) Create an 'OAuth 2.0 Client ID' of type 'Desktop app'\n"
            "3) Download the JSON and save it as credentials.json next to this script."
        )

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, scopes=[SCOPE])
    creds = flow.run_local_server(port=0)
    Path(TOKEN_PATH).write_text(creds.to_json())
    print(f"Saved token to {TOKEN_PATH}. The MCP server can now connect to Google Drive.")


if __name__ == "__main__":
    main()
