"""Allow-list of Settings fields platform_admin may override via the
Platform Config UI/API, layered on top of the .env-sourced default.

Deliberately excludes every field whose blast radius is "lock the whole
platform out" or "corrupt data permanently" if set wrong through a UI form:
db_url/redis_url (app can't run to save a bad value), jwt_secret_key
(instantly invalidates every session, including the admin's own),
credential_encryption_key/ci_credential_encryption_key (already-encrypted
DB rows become permanently undecryptable), every zitadel_* field and
auth_provider (breaks login for everyone), platform_admin_emails (self
privilege-escalation via a free-text field instead of the existing
member-invite flow), and cors_origins/cookie_secure/host/port/session
cookie names (breaks browser-to-API connectivity platform-wide). Those stay
.env-only, edited by whoever has host/infra access, never through this app.

Also excluded (Group 2 in the design discussion): OAuth app credentials
(affect every org's Gmail/Calendar/Drive connect flow at once), budget/quota
limits (shared safety nets, already tuned live once this session), and
sandbox_allow_network (flips a security posture, not a plain integration
knob) — kept out for now; can be promoted here later with its own
confirmation UX if actually needed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigField:
    key: str
    label: str
    group: str
    type: str  # "string" | "boolean" | "number" | "secret" | "options"
    description: str = ""
    options: tuple[str, ...] | None = None


PLATFORM_CONFIG_FIELDS: tuple[ConfigField, ...] = (
    # --- Integrations ---
    ConfigField("tinyfish_api_key", "TinyFish Search API key", "Integrations", "secret",
                "3rd-tier web_search fallback (after SearXNG and DuckDuckGo)."),
    ConfigField("youtube_api_key", "YouTube Data API key", "Integrations", "secret",
                "Backs the youtube_search tool."),
    ConfigField("crawler_api_token", "Crawler (crawl4ai) API token", "Integrations", "secret",
                "Auth token for the self-hosted crawl4ai instance backing web_fetch."),
    ConfigField("rag_api_key", "RAG service API key", "Integrations", "secret",
                "Auth key for the standalone rag-service."),
    ConfigField("searxng_url", "SearXNG URL", "Integrations", "string",
                "Self-hosted metasearch instance backing web_search. Empty disables it."),
    ConfigField("crawler_url", "Crawler URL", "Integrations", "string",
                "Self-hosted crawl4ai instance backing web_fetch. Empty disables it."),
    ConfigField("rag_service_url", "RAG service URL", "Integrations", "string"),
    ConfigField("rag_mcp_url", "RAG MCP URL", "Integrations", "string"),
    ConfigField("docling_service_url", "Docling service URL", "Integrations", "string"),

    # --- Observability ---
    ConfigField("langfuse_enabled", "Enable Langfuse", "Observability", "boolean"),
    ConfigField("langfuse_public_key", "Langfuse public key", "Observability", "string"),
    ConfigField("langfuse_secret_key", "Langfuse secret key", "Observability", "secret"),
    ConfigField("langfuse_base_url", "Langfuse base URL", "Observability", "string"),
    ConfigField("langfuse_flush_timeout_seconds", "Langfuse flush timeout (s)", "Observability", "number"),
    ConfigField("otel_enabled", "Enable OpenTelemetry", "Observability", "boolean"),
    ConfigField("otel_exporter_endpoint", "OTel exporter endpoint", "Observability", "string"),
    ConfigField("otel_capture_message_content", "OTel: capture message content", "Observability", "boolean",
                "Attaches prompt/completion text to spans — may contain user PII."),
    ConfigField("observability_enabled", "Enable LLM observability", "Observability", "boolean"),
    ConfigField("observability_capture_content", "Capture prompt/completion content", "Observability", "boolean",
                "Sends prompt/completion text to the observability backend — may contain user PII."),
    ConfigField("observability_sampling_rate", "Observability sampling rate", "Observability", "number"),
    ConfigField("observability_max_content_bytes", "Observability max content bytes", "Observability", "number"),

    # --- Workflow ---
    ConfigField("workflow_execution_mode", "Workflow execution mode", "Workflow", "options",
                options=("inline", "queued")),
    ConfigField("workflow_max_concurrency", "Workflow max concurrency", "Workflow", "number"),
    ConfigField("workflow_node_default_timeout_s", "Workflow node default timeout (s)", "Workflow", "number"),
    ConfigField("workflow_webhook_shared_token", "Workflow webhook shared token", "Workflow", "secret"),

    # --- Customer Intelligence ---
    ConfigField("customer_intelligence_enabled", "Enable Customer Intelligence", "Customer Intelligence", "boolean"),
    ConfigField("ci_classifier_enabled", "Enable CI email classifier", "Customer Intelligence", "boolean"),
    ConfigField("ci_classifier_economy_model_id", "CI classifier economy model ID", "Customer Intelligence", "string"),
    ConfigField("ci_classifier_strong_model_id", "CI classifier strong model ID", "Customer Intelligence", "string"),
    ConfigField("ci_classifier_timeout_s", "CI classifier timeout (s)", "Customer Intelligence", "number"),
    ConfigField("ci_classifier_strong_timeout_s", "CI classifier strong timeout (s)", "Customer Intelligence", "number"),
    ConfigField("ci_classifier_max_body_chars", "CI classifier max body chars", "Customer Intelligence", "number"),
    ConfigField("ci_classifier_accept_confidence", "CI classifier accept confidence", "Customer Intelligence", "number"),
    ConfigField("ci_classifier_company_confidence", "CI classifier company confidence", "Customer Intelligence", "number"),
    ConfigField("ci_classifier_meeting_confidence", "CI classifier meeting confidence", "Customer Intelligence", "number"),
    ConfigField("ci_classifier_daily_call_limit_per_org", "CI classifier daily call limit/org", "Customer Intelligence", "number"),
    ConfigField("ci_news_window_days", "CI news window (days)", "Customer Intelligence", "number"),
    ConfigField("ci_daily_schedule_default", "CI daily schedule default (HH:MM)", "Customer Intelligence", "string"),
    ConfigField("ci_research_timeout_s", "CI research timeout (s)", "Customer Intelligence", "number"),
    ConfigField("ci_max_sources_per_case", "CI max sources per case", "Customer Intelligence", "number"),
    ConfigField("ci_max_attachment_bytes", "CI max attachment bytes", "Customer Intelligence", "number"),
    ConfigField("ci_approval_expiry_hours", "CI approval expiry (hours)", "Customer Intelligence", "number"),
    ConfigField("ci_company_api_url", "CI company API URL", "Customer Intelligence", "string"),
    ConfigField("ci_company_api_key", "CI company API key", "Customer Intelligence", "secret"),
    ConfigField("ci_company_provider", "CI company provider", "Customer Intelligence", "options",
                options=("mcp", "fixture")),

    # --- Sandbox ---
    ConfigField("sandbox_docker_image_python", "Sandbox Python image", "Sandbox", "string"),
    ConfigField("sandbox_docker_image_bash", "Sandbox Bash image", "Sandbox", "string"),
    ConfigField("sandbox_docker_image_node", "Sandbox Node image", "Sandbox", "string"),
    ConfigField("sandbox_memory", "Sandbox memory limit", "Sandbox", "string"),
    ConfigField("sandbox_cpus", "Sandbox CPU limit", "Sandbox", "number"),
    ConfigField("sandbox_default_timeout", "Sandbox default timeout (s)", "Sandbox", "number"),
    ConfigField("sandbox_max_run_seconds", "Sandbox max run time (s)", "Sandbox", "number"),
    ConfigField("sandbox_max_retries", "Sandbox max retries", "Sandbox", "number"),

    # --- Other ---
    ConfigField("log_level", "Log level", "Other", "string"),
)

PLATFORM_CONFIG_BY_KEY: dict[str, ConfigField] = {f.key: f for f in PLATFORM_CONFIG_FIELDS}
