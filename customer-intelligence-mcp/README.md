# customer-intelligence-mcp

Stateless MCP service for real Customer Intelligence connectors. It does not
store OAuth credentials; the backend passes a short-lived access token per
call. Run over SSE in Docker or stdio for local development.

Tools: `email_*`, `calendar_list_events`, `drive_list_files`,
`drive_get_file`, `drive_create_file`, `drive_update_file`,
`drive_delete_file`, `web_search`, `news_search`, `company_search`, and
`company_get`.

Company tools require `CI_COMPANY_API_URL` and `CI_COMPANY_API_KEY`; when they
are absent the service returns `research_unavailable`, never fixture data.
