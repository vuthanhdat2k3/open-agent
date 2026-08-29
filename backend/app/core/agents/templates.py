from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

TEMPLATE_MATCH_FIELDS = (
    "description",
    "system_prompt",
    "tools",
    "allowed_risk_tiers",
    "kind",
    "max_iterations",
    "temperature",
    "enable_thinking",
    "a2a_exposed",
    "auto_rollback_enabled",
)


def _template_match_hash(source: Any) -> str:
    """Compute semantic fingerprint of an agent configuration ignoring org-specific model_id."""

    def _val(f: str) -> Any:
        v = source.get(f) if isinstance(source, dict) else getattr(source, f, None)
        if f in ("tools", "allowed_risk_tiers") and isinstance(v, (list, tuple, set)):
            return sorted(list(v))
        if f == "system_prompt" and isinstance(v, str):
            return v.strip()
        if f in ("enable_thinking", "a2a_exposed", "auto_rollback_enabled"):
            return bool(v)
        return v

    config = {field: _val(field) for field in TEMPLATE_MATCH_FIELDS}
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SystemAgentBlueprint:
    id: str  # Deterministic System ID (e.g. sys-agent-general)
    key: str  # template_key (e.g. general)
    name: str  # Display name
    description: str
    system_prompt: str
    recommended_tier: str  # fast | standard | reasoning | frontier
    tools: list[str]
    allowed_risk_tiers: list[str]
    kind: str = "worker"
    max_iterations: int = 12
    temperature: float = 0.7
    enable_thinking: bool | None = None
    a2a_exposed: bool = False
    auto_rollback_enabled: bool = False
    is_pinned_by_default: bool = False  # UI default pin state

    @property
    def baseline_match_hash(self) -> str:
        return _template_match_hash(self)


# ---------------------------------------------------------------------------
# 13 System Agent Blueprints Definition
# ---------------------------------------------------------------------------

SYSTEM_AGENT_BLUEPRINTS: dict[str, SystemAgentBlueprint] = {
    # --- 1. Core Orchestrator ---
    "general": SystemAgentBlueprint(
        id="sys-agent-general",
        key="general",
        name="General Assistant",
        description="General-purpose conversational assistant and multi-agent orchestrator",
        system_prompt=(
            "You are a helpful AI assistant. Use the provided tools when they "
            "help accomplish the user's request. You can delegate complex tasks to specialized sub-agents "
            "or trigger automated workflows when appropriate."
        ),
        recommended_tier="fast",
        tools=[
            "call_agent",
            "workflow_list",
            "workflow_run",
            "read_attachment",
            "web_fetch",
            "memory_store",
            "memory_recall",
        ],
        allowed_risk_tiers=["safe", "read", "network"],
        kind="worker",
        max_iterations=12,
        temperature=0.7,
        is_pinned_by_default=True,
    ),
    # --- 2. Executive Assistant ---
    "executive-assistant": SystemAgentBlueprint(
        id="sys-agent-executive-assistant",
        key="executive-assistant",
        name="Executive Assistant",
        description="Daily briefings, schedule management, meeting preparation, and executive summaries",
        system_prompt=(
            "You are an Executive Assistant. Your mission is to provide concise daily briefings, "
            "manage and prepare agendas for upcoming meetings, inspect emails for high-priority items, "
            "and synthesize actionable summaries for busy leaders."
        ),
        recommended_tier="standard",
        tools=[
            "calendar_list_events",
            "calendar_get_event",
            "email_list_new",
            "email_search",
            "drive_list_files",
            "get_current_time",
            "memory_recall",
            "memory_store",
        ],
        allowed_risk_tiers=["safe", "read", "network"],
        kind="worker",
        max_iterations=14,
        temperature=0.4,
        is_pinned_by_default=False,
    ),
    # --- 3. Automation & Workflow Manager ---
    "workflow-manager": SystemAgentBlueprint(
        id="sys-agent-workflow-manager",
        key="workflow-manager",
        name="Workflow & Automation Manager",
        description="Design, test, inspect, generate, and execute DAG automation workflows",
        system_prompt=(
            "You are an expert Workflow & Automation Specialist in OpenAgent. "
            "Your objective is to help users design, inspect, create, update, run, and manage DAG automation workflows.\n\n"
            "Key capabilities:\n"
            "- List and search existing workflows using `workflow_list`\n"
            "- Inspect node/edge DAG definitions using `workflow_get`\n"
            "- Run workflows with on-demand input parameters using `workflow_run`\n"
            "- Generate new workflow architectures from prompt using `workflow_generate`\n"
            "- Create or update custom workflows using `workflow_create` or `workflow_update`\n"
            "- Search and install pre-built templates from the Marketplace using `workflow_catalog_list` and `workflow_catalog_install`\n"
            "- Remove outdated workflows using `workflow_delete`"
        ),
        recommended_tier="reasoning",
        tools=[
            "workflow_list",
            "workflow_get",
            "workflow_run",
            "workflow_create",
            "workflow_update",
            "workflow_delete",
            "workflow_generate",
            "workflow_catalog_list",
            "workflow_catalog_install",
            "read_attachment",
            "web_fetch",
            "memory_store",
            "memory_recall",
            "call_agent",
        ],
        allowed_risk_tiers=["safe", "read", "network"],
        kind="worker",
        max_iterations=20,
        temperature=0.2,
        is_pinned_by_default=True,
    ),
    # --- 4. Email Intelligence ---
    "email-intelligence": SystemAgentBlueprint(
        id="sys-agent-email-intelligence",
        key="email-intelligence",
        name="Email Intelligence",
        description="Inbox triage, priority classification, draft generation, and email tracking",
        system_prompt=(
            "You are an Email Intelligence specialist. Analyze inbound emails, categorize priority, "
            "draft contextual replies, suggest labels, and summarize email threads."
        ),
        recommended_tier="fast",
        tools=[
            "email_search",
            "email_get",
            "email_list_new",
            "email_create_draft",
            "email_reply",
            "email_label",
            "email_send",
            "memory_store",
            "memory_recall",
        ],
        allowed_risk_tiers=["safe", "read", "network"],
        kind="worker",
        max_iterations=12,
        temperature=0.3,
        is_pinned_by_default=False,
    ),
    # --- 5. Calendar Assistant ---
    "calendar-assistant": SystemAgentBlueprint(
        id="sys-agent-calendar-assistant",
        key="calendar-assistant",
        name="Calendar Assistant",
        description="Meeting scheduling, conflict resolution, calendar invites, and availability checking",
        system_prompt=(
            "You are a Calendar Management Assistant. Help users check availability, schedule meetings, "
            "update events, handle scheduling conflicts, and send Google Calendar invitations."
        ),
        recommended_tier="fast",
        tools=[
            "calendar_list_events",
            "calendar_get_event",
            "calendar_create_event",
            "calendar_update_event",
            "calendar_delete_event",
            "get_current_time",
            "memory_recall",
        ],
        allowed_risk_tiers=["safe", "read", "network"],
        kind="worker",
        max_iterations=10,
        temperature=0.2,
        is_pinned_by_default=False,
    ),
    # --- 6. Customer Researcher ---
    "customer-researcher": SystemAgentBlueprint(
        id="sys-agent-customer-researcher",
        key="customer-researcher",
        name="Customer & Company Researcher",
        description="B2B company intelligence, market news enrichment, contract and document retrieval",
        system_prompt=(
            "You are a Customer & B2B Intelligence Specialist. Research corporate accounts, analyze industry news, "
            "retrieve customer documents and contracts from Drive, and synthesize structured company profiles."
        ),
        recommended_tier="standard",
        tools=[
            "company_search",
            "company_get",
            "news_search",
            "drive_list_files",
            "drive_get_file",
            "web_search",
            "memory_store",
            "memory_recall",
        ],
        allowed_risk_tiers=["safe", "read", "network"],
        kind="worker",
        max_iterations=16,
        temperature=0.3,
        is_pinned_by_default=False,
    ),
    # --- 7. RAG Researcher ---
    "rag-researcher": SystemAgentBlueprint(
        id="sys-agent-rag-researcher",
        key="rag-researcher",
        name="RAG Knowledge Researcher",
        description="Enterprise knowledge base retrieval, semantic vector search, and Graph RAG",
        system_prompt=(
            "You are a specialized RAG research agent. Your objective is to answer questions "
            "by querying the knowledge base using RAG tools. Always call `rag_search` before "
            "answering factual or domain queries. If details are missing, suggest ingesting "
            "documents or URLs using `rag_ingest_file` or `rag_ingest_url`."
        ),
        recommended_tier="standard",
        tools=[
            "rag_search",
            "rag_graph_search",
            "rag_list_collections",
            "rag_ingest_file",
            "rag_ingest_url",
            "rag_ingest_text",
            "web_fetch",
            "memory_store",
            "memory_recall",
        ],
        allowed_risk_tiers=["safe", "read", "network"],
        kind="worker",
        max_iterations=20,
        temperature=0.2,
        is_pinned_by_default=False,
    ),
    # --- 8. Document Analyst ---
    "document-analyst": SystemAgentBlueprint(
        id="sys-agent-document-analyst",
        key="document-analyst",
        name="Document Analyst & Ingestion",
        description="Complex PDF/DOCX OCR parsing, structured data extraction, and knowledge ingestion",
        system_prompt=(
            "You are a Document Analysis Specialist. Parse complex documents (PDFs, spreadsheets, DOCX), "
            "extract tables and key metadata, and ingest parsed knowledge into structured collections."
        ),
        recommended_tier="standard",
        tools=[
            "rag_ingest_file",
            "rag_ingest_url",
            "rag_ingest_text",
            "read_attachment",
            "memory_store",
            "memory_recall",
        ],
        allowed_risk_tiers=["safe", "read", "network"],
        kind="worker",
        max_iterations=16,
        temperature=0.2,
        is_pinned_by_default=False,
    ),
    # --- 9. Coder ---
    "coder": SystemAgentBlueprint(
        id="sys-agent-coder",
        key="coder",
        name="Coder & UI Designer",
        description="Software development, debugging, script execution, and interactive live UI preview",
        system_prompt=(
            "You are a coding agent. Read the relevant files, plan the change, "
            "and implement it with clear, minimal diffs.\n\n"
            "IMPORTANT: When responding with HTML, CSS, or JavaScript for preview/display purposes, "
            "return it as a code block (```html, ```css, ```javascript) in your response. "
            "Do NOT use write_file for this. Users can then preview it directly in the chat UI "
            "using the Preview button or 'Mở tab mới' (open in new tab) feature."
        ),
        recommended_tier="fast",
        tools=["run_code", "read_attachment", "memory_store", "memory_recall"],
        allowed_risk_tiers=["safe", "read", "execute"],
        kind="worker",
        max_iterations=16,
        temperature=0.2,
        is_pinned_by_default=True,
    ),
    # --- 10. Data Analyst ---
    "data-analyst": SystemAgentBlueprint(
        id="sys-agent-data-analyst",
        key="data-analyst",
        name="Data Analyst",
        description="Quantitative analysis, CSV/Excel processing, statistical insights, and data visualization",
        system_prompt=(
            "You are a Data Analyst. Inspect CSV/Excel datasets, run Python scripts for descriptive statistics "
            "and exploratory data analysis, generate charts, and synthesize data-driven business insights."
        ),
        recommended_tier="standard",
        tools=["run_code", "read_attachment", "web_fetch", "memory_store", "memory_recall"],
        allowed_risk_tiers=["safe", "read", "execute"],
        kind="worker",
        max_iterations=16,
        temperature=0.2,
        is_pinned_by_default=False,
    ),
    # --- 11. Deep Researcher ---
    "deep-researcher": SystemAgentBlueprint(
        id="sys-agent-deep-researcher",
        key="deep-researcher",
        name="Deep Web Researcher",
        description="Multi-hop query breakdown, SearXNG & YouTube search, and structured academic synthesis",
        system_prompt=(
            "You are a research agent. Break the question into sub-questions, "
            "fetch authoritative sources, and synthesize a cited answer."
        ),
        recommended_tier="reasoning",
        tools=["web_search", "web_fetch", "youtube_search", "read_attachment", "memory_store", "memory_recall"],
        allowed_risk_tiers=["safe", "read", "network"],
        kind="worker",
        max_iterations=20,
        temperature=0.3,
        is_pinned_by_default=False,
    ),
    # --- 12. Summarizer ---
    "summarizer": SystemAgentBlueprint(
        id="sys-agent-summarizer",
        key="summarizer",
        name="Summarizer",
        description="Concise, factual, and structured document and thread summarization",
        system_prompt=(
            "You are a summarization agent. Produce a tight, structured summary "
            "that preserves the key facts and omits filler."
        ),
        recommended_tier="fast",
        tools=["read_attachment", "memory_store"],
        allowed_risk_tiers=["safe", "read"],
        kind="worker",
        max_iterations=8,
        temperature=0.4,
        is_pinned_by_default=False,
    ),
    # --- 13. Content Writer ---
    "content-writer": SystemAgentBlueprint(
        id="sys-agent-content-writer",
        key="content-writer",
        name="Content Writer & Copywriter",
        description="PR articles, blog posts, marketing copy, newsletters, and tone-of-voice alignment",
        system_prompt=(
            "You are an expert Content Writer and Copywriter. Create engaging, well-structured, "
            "and persuasive written content (blog posts, press releases, newsletters, social copy) "
            "tailored to the target audience and brand tone."
        ),
        recommended_tier="standard",
        tools=["web_search", "read_attachment", "memory_store", "memory_recall"],
        allowed_risk_tiers=["safe", "read", "network"],
        kind="worker",
        max_iterations=14,
        temperature=0.7,
        is_pinned_by_default=False,
    ),
}
