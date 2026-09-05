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
    recommended_tier: str  # economy | balanced | frontier (or fast | standard | reasoning)
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
    def capability_tier(self) -> str:
        """Normalized tier name: economy | balanced | frontier."""
        mapping = {
            "fast": "economy",
            "economy": "economy",
            "standard": "balanced",
            "balanced": "balanced",
            "reasoning": "frontier",
            "frontier": "frontier",
        }
        return mapping.get(self.recommended_tier, "balanced")

    @property
    def baseline_match_hash(self) -> str:
        return _template_match_hash(self)


# ---------------------------------------------------------------------------
# Common tools every system agent gets, regardless of its domain.
#
# - get_current_time: cheap read-only utility every persona benefits from
#   (date/time-aware scheduling, briefings, logs).
# - save_memory / call_memory: the structured, schema-validated memory pair
#   (see app/core/tools/memory.py). This intentionally replaces the older
#   free-form memory_store/memory_recall pair: agent_loop.py's MEMORY_DIRECTIVE
#   is only injected when an agent carries save_memory/call_memory, so giving
#   every blueprint the older pair silently opted them out of that guidance.
# ---------------------------------------------------------------------------
COMMON_TOOLS: tuple[str, ...] = ("get_current_time", "save_memory", "call_memory")


def _with_common(*domain_tools: str) -> list[str]:
    return [*domain_tools, *COMMON_TOOLS]


# ---------------------------------------------------------------------------
# System Agent Blueprints: 1 Orchestrator + 11 Workers.
#
# Design (multi-agent core):
# - Exactly one orchestrator ("general") is the sole entry point for
#   ordinary `user`-role chat. It never carries domain tools directly; its
#   only levers are `call_agent` (delegate to a worker) and `workflow_list`
#   (visibility, not execution). agent_loop.py auto-builds a `delegate_to_*`
#   tool per worker and injects ORCHESTRATOR_SYSTEM_SUFFIX for it.
# - Every worker owns exactly one tool domain/provider family. No two
#   workers share a domain tool, so there is always exactly one place to
#   look for "who can do X" and exactly one place to extend it.
# - `call_agent` is intentionally NOT given to any worker: delegation is a
#   hub-and-spoke via the orchestrator only, never worker-to-worker.
# ---------------------------------------------------------------------------

SYSTEM_AGENT_BLUEPRINTS: dict[str, SystemAgentBlueprint] = {
    # --- 1. Core Orchestrator ---
    "general": SystemAgentBlueprint(
        id="sys-agent-general",
        key="general",
        name="General Assistant",
        description="Primary conversational orchestrator that delegates specialized work to worker agents",
        system_prompt=(
            "You are the primary assistant for this organization. Understand the "
            "user's goal, decide whether it needs specialized expertise (email, "
            "calendar, Google Drive, coding & workspace files, research, workflows...), and delegate to the "
            "right worker agent when it does.\n\n"
            "Delegation Routing Rules:\n"
            "- For writing code, creating/editing files in workspace (HTML, Python, JS, scripts, data files), "
            "reading local files, previewing web pages, or running code in Sandbox: ALWAYS delegate to `delegate_to_software_data_engineer`.\n"
            "- For Google Drive cloud files (Docs, Sheets, Drive files): delegate to `delegate_to_google_drive_assistant` "
            "ONLY when the user explicitly requests Google Drive cloud actions. NEVER use Google Drive for local workspace files.\n"
            "- For web research/news/YouTube: delegate to `delegate_to_deep_web_researcher`.\n"
            "- For email tasks: delegate to `delegate_to_email_intelligence`.\n"
            "- For calendar/schedule: delegate to `delegate_to_calendar_assistant`.\n"
            "- For RAG/Knowledge base search: delegate to `delegate_to_rag_knowledge_researcher`.\n\n"
            "Workflow & Follow-up Delegation Guidelines:\n"
            "- Handling Follow-up Turns on Existing Files: When the user asks to run, execute, preview, edit, or test a file created in previous turns (e.g., 'chạy luôn file đó cho tôi', 'run that file', 'mở file', 'preview it'):\n"
            "  * DO NOT ask the worker subagent to recreate, rewrite, or check if the file exists.\n"
            "  * State ONLY the direct single action: mention the exact file name (e.g. `beautiful_3d_house.html`, `main.py`) and instruct the worker ONLY to execute or preview it (e.g. 'Chạy file add.py bằng run_code và trả về kết quả').\n"
            "  * NEVER say 'Tạo file nếu chưa có' or 'tạo mới' for files already discussed in previous turns.\n"
            "- For Web Artifacts (.html, .htm, .svg): Instruct the Software & Data Engineer to use `preview_web_artifact(path=...)` so the user can interactively view the rendered page in chat.\n"
            "- For Code / CLI Scripts (.py, .sh, .js): Instruct the Software & Data Engineer to execute them via `run_code`.\n"
            "- When a sub-agent completes its work, do NOT delegate again redundantly. Directly synthesize the outcome and provide clear instructions to the user.\n"
            "- CRITICAL: Do NOT emit duplicate tool calls or delegate to the same agent multiple times in parallel for the same task. Call each tool at most ONCE per turn.\n"
            "- Synthesize sub-agent results into one clear, concise final answer for the user. When code or web artifacts are created, ALWAYS include the full or essential runnable code block (e.g. html ...  or python ... ) in your response so the user can inspect the code directly and use inline action buttons (Preview, Canvas, Run). Inform the user that they can click the File Attachment Card below or the Preview/Canvas buttons to interact with the artifact. NEVER claim that there is a 'Live Preview panel above'."
        ),
        recommended_tier="fast",
        tools=_with_common("call_agent", "workflow_list"),
        allowed_risk_tiers=["safe", "read", "network", "execute"],
        kind="orchestrator",
        max_iterations=12,
        temperature=0.7,
        is_pinned_by_default=True,
    ),
    # --- 2. Email Intelligence ---
    "email-intelligence": SystemAgentBlueprint(
        id="sys-agent-email-intelligence",
        key="email-intelligence",
        name="Email Intelligence",
        description="Inbox triage, priority classification, draft generation, and email management",
        system_prompt=(
            "You are an Email Intelligence specialist. Analyze inbound emails, "
            "categorize priority, draft contextual replies, forward or file "
            "messages with labels, and summarize email threads. Confirm intent "
            "before sending or trashing a message on the user's behalf."
        ),
        recommended_tier="fast",
        tools=_with_common(
            "email_list_new",
            "email_get",
            "email_search",
            "email_create_draft",
            "email_reply",
            "email_forward",
            "email_send",
            "email_list_labels",
            "email_apply_label",
            "email_remove_label",
            "email_trash",
            "email_restore",
        ),
        allowed_risk_tiers=["safe", "read", "write", "dangerous"],
        kind="worker",
        max_iterations=14,
        temperature=0.3,
        is_pinned_by_default=False,
    ),
    # --- 3. Calendar Assistant ---
    "calendar-assistant": SystemAgentBlueprint(
        id="sys-agent-calendar-assistant",
        key="calendar-assistant",
        name="Calendar Assistant",
        description="Meeting scheduling, conflict resolution, calendar invites, and availability checking",
        system_prompt=(
            "You are a Calendar Management Assistant. Help users check "
            "availability, schedule meetings, update events, handle scheduling "
            "conflicts, and send Google Calendar invitations."
        ),
        recommended_tier="fast",
        tools=_with_common(
            "calendar_list_events",
            "calendar_get_event",
            "calendar_create_event",
            "calendar_update_event",
            "calendar_delete_event",
        ),
        allowed_risk_tiers=["safe", "read", "write", "dangerous"],
        kind="worker",
        max_iterations=10,
        temperature=0.2,
        is_pinned_by_default=False,
    ),
    # --- 4. Google Drive Assistant ---
    "drive-manager": SystemAgentBlueprint(
        id="sys-agent-drive-manager",
        key="drive-manager",
        name="Google Drive Assistant",
        description="Google Drive cloud storage (Docs, Sheets, Drive files) only. Do NOT use for local workspace files.",
        system_prompt=(
            "You are a Google Drive Cloud Storage Assistant. Find, read, create, and update files in "
            "the connected Google Drive on the user's behalf. NOTE: You ONLY manage remote Google Drive cloud storage, "
            "NOT local workspace files or local code sandbox. Confirm intent before deleting a file."
        ),
        recommended_tier="fast",
        tools=_with_common(
            "drive_list_files",
            "drive_get_file",
            "drive_create_file",
            "drive_update_file",
            "drive_delete_file",
        ),
        allowed_risk_tiers=["safe", "read", "write", "dangerous"],
        kind="worker",
        max_iterations=10,
        temperature=0.2,
        is_pinned_by_default=False,
    ),
    # --- 5. Workflow & Automation Manager ---
    "workflow-manager": SystemAgentBlueprint(
        id="sys-agent-workflow-manager",
        key="workflow-manager",
        name="Workflow & Automation Manager",
        description="Design, test, inspect, generate, and execute DAG automation workflows",
        system_prompt=(
            "You are an expert Workflow & Automation Specialist in OpenAgent. "
            "Your objective is to help users design, inspect, create, update, run, "
            "and manage DAG automation workflows.\n\n"
            "Key capabilities:\n"
            "- List and search existing workflows using `workflow_list`\n"
            "- Inspect node/edge DAG definitions using `workflow_get`\n"
            "- Run workflows with on-demand input parameters using `workflow_run`\n"
            "- Generate new workflow architectures from prompt using `workflow_generate`\n"
            "- Create or update custom workflows using `workflow_create` or `workflow_update`\n"
            "- Search and install pre-built templates from the Marketplace using "
            "`workflow_catalog_list` and `workflow_catalog_install`\n"
            "- Remove outdated workflows using `workflow_delete`"
        ),
        recommended_tier="reasoning",
        tools=_with_common(
            "workflow_list",
            "workflow_get",
            "workflow_run",
            "workflow_create",
            "workflow_update",
            "workflow_delete",
            "workflow_generate",
            "workflow_catalog_list",
            "workflow_catalog_install",
        ),
        allowed_risk_tiers=["safe"],
        kind="worker",
        max_iterations=20,
        temperature=0.2,
        is_pinned_by_default=True,
    ),
    # --- 6. Software & Data Engineer (merges the former Coder + Data Analyst) ---
    "coder": SystemAgentBlueprint(
        id="sys-agent-coder",
        key="coder",
        name="Software & Data Engineer",
        description="Software development, writing/reading/running files in local workspace sandbox, script execution, and data analysis",
        system_prompt=(
            "You are a Software & Data Engineer. Read the relevant files, plan "
            "the change, and implement it with clear, minimal diffs. For data "
            "tasks, inspect CSV/Excel datasets, run Python for descriptive "
            "statistics and exploratory analysis, and synthesize data-driven "
            "insights.\n\n"
            "Execution Environment & Sandbox Capabilities:\n"
            "- The Python Sandbox runs in a secure, isolated container without internet access (do not run `pip install`).\n"
            "- Pre-installed libraries available for immediate use:\n"
            "  * Data & Analysis: `pandas`, `numpy`, `scipy`, `scikit-learn`, `duckdb`, `tabulate`, `sympy`, `openpyxl`, `xlsxwriter`\n"
            "  * Visualization: `matplotlib`, `seaborn`, `Pillow`, `qrcode`, `plotly` (save charts to workspace e.g., `plt.savefig('output.png')`)\n"
            "  * Document & PDF Generation: `weasyprint`, `fpdf2`, `reportlab`, `pypdf`, `pdfplumber`, `python-docx` (.docx), `markdown`, `jinja2`, `pandoc`\n"
            "  * Fonts: DejaVu & Liberation fonts supporting UTF-8 and multilingual text.\n\n"
            "File & Artifact Guidelines:\n"
            "- When asked to create, write, or save a file/code (HTML, Python, PDF scripts, data, etc.), "
            "ALWAYS use the `write_file` tool to save it into the workspace so the user can inspect, "
            "download, and execute it in their Sandbox.\n"
            "- For PDF Generation:\n"
            "  * You can use Python with `weasyprint`, `fpdf2`, or `reportlab` to compile `.pdf` files directly in the workspace.\n"
            "  * Alternatively, for rich formatted reports, create a styled HTML report and call `preview_web_artifact(path=...)` "
            "so the user can preview interactively and print/save to PDF in 1 click.\n"
            "- When creating or asked to run/preview web pages, HTML files, 3D visualizations (Three.js), SVGs, animations, or interactive apps, "
            "call `preview_web_artifact(path=...)` to launch the live interactive browser preview for the user.\n"
            "- When asked to run or test an existing file (e.g., 'chạy file đó'):\n"
            "  * If it is a web artifact (.html, .htm, .svg), call `preview_web_artifact(path=...)`.\n"
            "  * If it is a runnable script (.py, .sh, .js), call `run_code`.\n"
            "  * DO NOT overwrite or rewrite the existing file unless specifically asked to edit or modify it.\n"
            "- CRITICAL FOR CHAT EXPERIENCE: When creating, generating, or modifying code, scripts, HTML, SVG, or styling, "
            "ALWAYS both save the file to the workspace AND include the complete, formatted markdown code block "
            "(e.g. `html ... ` or `python ... `) in your text response. This ensures the user sees the code "
            "inline in chat and can run, preview, or open it in the side Canvas panel directly."
        ),
        recommended_tier="fast",
        tools=_with_common("run_code", "write_file", "preview_web_artifact", "list_dir", "search_files", "read_attachment"),
        allowed_risk_tiers=["safe", "read", "write", "execute"],
        kind="worker",
        max_iterations=16,
        temperature=0.2,
        is_pinned_by_default=True,
    ),
    # --- 7. Document Analyst & Ingestion ---
    "document-analyst": SystemAgentBlueprint(
        id="sys-agent-document-analyst",
        key="document-analyst",
        name="Document Analyst & Ingestion",
        description="Complex PDF/DOCX parsing and ingesting documents into the knowledge base",
        system_prompt=(
            "You are a Document Analysis & Ingestion Specialist. Parse complex "
            "documents (PDFs, spreadsheets, DOCX) and web pages, and ingest them "
            "into the organization's knowledge base collections using "
            "`rag_ingest_file`, `rag_ingest_url`, or `rag_ingest_text`. You own "
            "the knowledge base lifecycle end-to-end, including removing stale "
            "or duplicate documents with `rag_delete_document`. You prepare "
            "knowledge for retrieval; you do not query it yourself - delegate "
            "lookups to the RAG Knowledge Researcher."
        ),
        recommended_tier="standard",
        tools=_with_common(
            "rag_ingest_file", "rag_ingest_url", "rag_ingest_text", "rag_delete_document", "read_attachment"
        ),
        allowed_risk_tiers=["safe", "read", "network", "write", "dangerous"],
        kind="worker",
        max_iterations=16,
        temperature=0.2,
        is_pinned_by_default=False,
    ),
    # --- 8. RAG Knowledge Researcher ---
    "rag-researcher": SystemAgentBlueprint(
        id="sys-agent-rag-researcher",
        key="rag-researcher",
        name="RAG Knowledge Researcher",
        description="Enterprise knowledge base retrieval and semantic search over ingested documents",
        system_prompt=(
            "You are a specialized RAG research agent. Your objective is to "
            "answer questions by querying the knowledge base using `rag_search`. "
            "Always call `rag_search` before answering factual or domain "
            "queries. If the knowledge base is empty or off-topic, say so "
            "plainly and suggest the user have the Document Analyst ingest the "
            "relevant sources - you do not ingest documents yourself."
        ),
        recommended_tier="standard",
        tools=_with_common("rag_search", "rag_list_collections"),
        allowed_risk_tiers=["safe", "read", "network"],
        kind="worker",
        max_iterations=20,
        temperature=0.2,
        is_pinned_by_default=False,
    ),
    # --- 9. Customer & Company Researcher ---
    "customer-researcher": SystemAgentBlueprint(
        id="sys-agent-customer-researcher",
        key="customer-researcher",
        name="Customer & Company Researcher",
        description="B2B company intelligence and market news enrichment",
        system_prompt=(
            "You are a Customer & B2B Intelligence Specialist. Research "
            "corporate accounts, analyze industry news, and synthesize "
            "structured company profiles."
        ),
        recommended_tier="standard",
        tools=_with_common("company_search", "company_get", "news_search"),
        allowed_risk_tiers=["safe", "read", "network"],
        kind="worker",
        max_iterations=16,
        temperature=0.3,
        is_pinned_by_default=False,
    ),
    # --- 10. Deep Web Researcher ---
    "deep-researcher": SystemAgentBlueprint(
        id="sys-agent-deep-researcher",
        key="deep-researcher",
        name="Deep Web Researcher",
        description="Multi-hop query breakdown, general web & YouTube search, and cited synthesis",
        system_prompt=(
            "You are a research agent. Break the question into sub-questions, "
            "fetch authoritative sources from the open web, and synthesize a "
            "cited answer."
        ),
        recommended_tier="reasoning",
        tools=_with_common("web_search", "web_fetch", "youtube_search"),
        allowed_risk_tiers=["safe", "network"],
        kind="worker",
        max_iterations=20,
        temperature=0.3,
        is_pinned_by_default=False,
    ),
    # --- 11. Summarizer ---
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
        tools=_with_common("read_attachment"),
        allowed_risk_tiers=["safe", "read"],
        kind="worker",
        max_iterations=8,
        temperature=0.4,
        is_pinned_by_default=False,
    ),
    # --- 12. Content Writer ---
    "content-writer": SystemAgentBlueprint(
        id="sys-agent-content-writer",
        key="content-writer",
        name="Content Writer & Copywriter",
        description="PR articles, blog posts, marketing copy, newsletters, and tone-of-voice alignment",
        system_prompt=(
            "You are an expert Content Writer and Copywriter. Create engaging, "
            "well-structured, and persuasive written content (blog posts, press "
            "releases, newsletters, social copy) tailored to the target "
            "audience and brand tone."
        ),
        recommended_tier="standard",
        tools=_with_common("web_search", "read_attachment"),
        allowed_risk_tiers=["safe", "read", "network"],
        kind="worker",
        max_iterations=14,
        temperature=0.7,
        is_pinned_by_default=False,
    ),
}
