"""Declarative node configuration schemas for the workflow DAG engine.

Each ``NodeDefinition`` describes the fields a node kind accepts. The backend
uses it to validate ``GraphNode.parameters`` on save; the frontend renders the
node config form from the same definition (single source of truth), exposed via
``GET /api/workflows/node-definitions``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

FieldType = Literal[
    "string",
    "time",
    "date",
    "textarea",
    "number",
    "boolean",
    "options",
    "multiOptions",
    "collection",
    "fixedCollection",
    "json",
]

LoadOptionsSource = Literal[
    "tools",
    "models",
    "agents",
    "workflows",
    "connections",
    "users",
    "categories",
    "channels",
]


class NodeField(BaseModel):
    """One form field inside a ``NodeDefinition`` (n8n ``INodeProperties`` style)."""

    name: str
    label: str
    type: FieldType
    default: Any = None
    required: bool = False
    description: str = ""
    placeholder: str = ""
    options: list[dict[str, Any]] | None = None
    load_options_from: LoadOptionsSource | None = None
    display: dict[str, Any] | None = None
    type_options: dict[str, Any] = {}
    multiple: bool = False
    advanced: bool = False
    internal: bool = False


class NodeDefinition(BaseModel):
    """The full config schema for one node kind."""

    kind: str
    label: str
    description: str
    icon: str = ""
    fields: list[NodeField]
    default_parameters: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Shared fields (every node kind)
# ---------------------------------------------------------------------------

_COMMON_FIELDS: list[NodeField] = [
    NodeField(
        name="input_mapping",
        label="Input mapping",
        type="fixedCollection",
        default={},
        description="Map structured fields from upstream nodes into this node.",
        placeholder="Add field",
        type_options={"multipleValues": True},
    ),
    NodeField(
        name="onError",
        label="On error",
        type="options",
        default="stop",
        options=[
            {"name": "Stop workflow", "value": "stop"},
            {"name": "Continue (skip node)", "value": "continue"},
            {"name": "Use fallback value", "value": "fallback"},
        ],
        description="What to do when this node fails after retries are exhausted.",
    ),
    NodeField(
        name="fallback",
        label="Fallback value",
        type="textarea",
        default="",
        description="Used as output when onError is 'fallback'.",
        display={"show": {"onError": ["fallback"]}},
    ),
    NodeField(
        name="retry",
        label="Retry",
        type="collection",
        default={},
        description="Retry policy for this node.",
        options=[
            {"name": "Max attempts", "value": "max_attempts"},
            {"name": "Backoff seconds", "value": "backoff_s"},
        ],
    ),
    NodeField(
        name="timeout_s",
        label="Timeout (seconds)",
        type="number",
        default=0,
        description="Per-node execution timeout in seconds. 0 = no timeout.",
        type_options={"minValue": 0},
    ),
]


def common_fields() -> list[NodeField]:
    return [f.model_copy(deep=True) for f in _COMMON_FIELDS]


# ---------------------------------------------------------------------------
# Per-kind definitions
# ---------------------------------------------------------------------------

def _with_common(fields: list[NodeField]) -> list[NodeField]:
    return fields + common_fields()


def _build_definitions() -> dict[str, NodeDefinition]:
    input_node = NodeDefinition(
        kind="input",
        label="Input",
        description="Entry trigger for on-demand runs. Collects user input.",
        icon="log-in",
        default_parameters={"input_field": "Run input", "required": True},
        fields=_with_common(
            [
                NodeField(
                    name="input_field",
                    label="Input field name",
                    type="string",
                    default="Run input",
                    required=True,
                    description="Label shown for the run-input form.",
                ),
                NodeField(
                    name="required",
                    label="Required",
                    type="boolean",
                    default=True,
                    description="Whether run input is mandatory.",
                ),
                NodeField(
                    name="description",
                    label="Description",
                    type="textarea",
                    default="",
                    description="Help text for the input field.",
                ),
                NodeField(
                    name="trigger_type",
                    label="Trigger type",
                    type="string",
                    default="",
                    internal=True,
                ),
                NodeField(
                    name="template_key",
                    label="Template key",
                    type="string",
                    default="",
                    internal=True,
                ),
            ]
        ),
    )

    scheduler_node = NodeDefinition(
        kind="scheduler",
        label="Scheduler",
        description="Entry trigger on a recurring schedule. Fires via the cron tick.",
        icon="clock",
        default_parameters={"frequency": "daily", "time": "07:30", "timezone": "Asia/Ho_Chi_Minh"},
        fields=_with_common(
            [
                NodeField(
                    name="frequency",
                    label="Frequency",
                    type="options",
                    default="daily",
                    required=True,
                    options=[
                        {"name": "Once", "value": "once"},
                        {"name": "Hourly", "value": "hourly"},
                        {"name": "Daily", "value": "daily"},
                        {"name": "Weekdays", "value": "weekdays"},
                        {"name": "Weekly", "value": "weekly"},
                        {"name": "Custom (cron)", "value": "custom"},
                    ],
                ),
                NodeField(
                    name="enabled",
                    label="Enabled",
                    type="boolean",
                    default=True,
                    description="Whether this scheduler trigger is active.",
                ),
                NodeField(
                    name="time",
                    label="Time",
                    type="time",
                    default="07:30",
                    description="Time of day (HH:MM) in the selected timezone.",
                    type_options={"step": 60},
                    display={"hide": {"frequency": ["once", "hourly", "custom"]}},
                ),
                NodeField(
                    name="days_of_week",
                    label="Days of week",
                    type="multiOptions",
                    default=["mon", "tue", "wed", "thu", "fri"],
                    options=[
                        {"name": "Mon", "value": "mon"},
                        {"name": "Tue", "value": "tue"},
                        {"name": "Wed", "value": "wed"},
                        {"name": "Thu", "value": "thu"},
                        {"name": "Fri", "value": "fri"},
                        {"name": "Sat", "value": "sat"},
                        {"name": "Sun", "value": "sun"},
                    ],
                    display={"show": {"frequency": ["weekdays", "weekly"]}},
                ),
                NodeField(
                    name="timezone",
                    label="Timezone",
                    type="options",
                    default="Asia/Ho_Chi_Minh",
                    description="IANA timezone for the schedule.",
                    load_options_from="categories",  # overridden by backend to IANA list
                    display={"hide": {"frequency": ["once"]}},
                ),
                NodeField(
                    name="custom_cron",
                    label="Cron expression",
                    type="string",
                    default="",
                    placeholder="0 6 * * *",
                    description="5-field cron expression.",
                    display={"show": {"frequency": ["custom"]}},
                    advanced=True,
                ),
                NodeField(
                    name="start_date",
                    label="Start date",
                    type="date",
                    default="",
                    description="Optional ISO date (YYYY-MM-DD) to start the schedule.",
                    advanced=True,
                ),
                NodeField(
                    name="end_date",
                    label="End date",
                    type="date",
                    default="",
                    description="Optional ISO date (YYYY-MM-DD) to stop the schedule.",
                    advanced=True,
                ),
                NodeField(
                    name="emit_today_date",
                    label="Include today's date in output",
                    type="boolean",
                    default=False,
                    description="Add today's date (in the schedule's timezone) to this node's output data as `today_date`.",
                    advanced=True,
                ),
            ]
        ),
    )

    integration_node = NodeDefinition(
        kind="integration",
        label="Integration",
        description="Connects to a real external data source (Gmail, Calendar, Drive, webhook).",
        icon="plug",
        default_parameters={"source": "gmail", "operation": "list_new", "max_results": 20},
        fields=_with_common(
            [
                NodeField(
                    name="source",
                    label="Data source",
                    type="options",
                    default="gmail",
                    required=True,
                    options=[
                        {"name": "Gmail", "value": "gmail"},
                        {"name": "Google Calendar", "value": "google_calendar"},
                        {"name": "Google Drive", "value": "google_drive"},
                        {"name": "Gmail + Google Calendar", "value": "gmail_and_calendar"},
                        {"name": "Webhook", "value": "webhook"},
                    ],
                ),
                NodeField(
                    name="connection_id",
                    label="Connection",
                    type="options",
                    default="",
                    description="Your connected account for this source.",
                    load_options_from="connections",
                    display={"hide": {"source": ["webhook"]}},
                ),
                NodeField(
                    name="calendar_connection_id",
                    label="Calendar connection",
                    type="options",
                    default="",
                    description="Google Calendar account used when the source combines Gmail and Calendar.",
                    load_options_from="connections",
                    display={"show": {"source": ["gmail_and_calendar"]}},
                ),
                NodeField(
                    name="operation",
                    label="Operation",
                    type="options",
                    default="list_new",
                    options=[
                        {"name": "List new items", "value": "list_new"},
                        {"name": "Search", "value": "search"},
                        {"name": "Get by id", "value": "get"},
                        {"name": "List events", "value": "list_events"},
                        {"name": "List files", "value": "list_files"},
                    ],
                    display={"hide": {"source": ["webhook"]}},
                ),
                NodeField(
                    name="max_results",
                    label="Max results",
                    type="number",
                    default=20,
                    type_options={"minValue": 1, "maxValue": 100},
                ),
                NodeField(
                    name="query",
                    label="Query",
                    type="string",
                    default="",
                    placeholder="from:partner@example.com",
                    description="Search query / filter for the operation.",
                    display={"show": {"operation": ["search"]}},
                ),
                NodeField(
                    name="time_range",
                    label="Time range",
                    type="options",
                    default="7d",
                    options=[
                        {"name": "Today", "value": "today"},
                        {"name": "Last 7 days", "value": "7d"},
                        {"name": "Last 30 days", "value": "30d"},
                        {"name": "Custom", "value": "custom"},
                    ],
                ),
                NodeField(
                    name="webhook_path",
                    label="Webhook path",
                    type="string",
                    default="",
                    placeholder="my-events",
                    description="Path segment for POST /api/webhooks/workflow/{id}/{path}.",
                    display={"show": {"source": ["webhook"]}},
                ),
                NodeField(
                    name="trigger_type",
                    label="Trigger type",
                    type="string",
                    default="",
                    internal=True,
                ),
                NodeField(
                    name="template_key",
                    label="Template key",
                    type="string",
                    default="",
                    internal=True,
                ),
            ]
        ),
    )

    triager_node = NodeDefinition(
        kind="triager",
        label="Triager",
        description="Routes or classifies upstream data into categories (LLM or rules).",
        icon="filter",
        default_parameters={
            "mode": "llm",
            "categories": "high_priority, action_required, routine",
            "output_format": "category_with_reason",
        },
        fields=_with_common(
            [
                NodeField(
                    name="mode",
                    label="Mode",
                    type="options",
                    default="llm",
                    options=[
                        {"name": "LLM routing", "value": "llm"},
                        {"name": "Rules", "value": "rules"},
                    ],
                ),
                NodeField(
                    name="categories",
                    label="Categories",
                    type="textarea",
                    default="high_priority, action_required, routine",
                    description="Comma/newline-separated categories to route into.",
                ),
                NodeField(
                    name="instruction",
                    label="Routing instruction",
                    type="textarea",
                    default="",
                    description="Extra guidance for the LLM on how to classify.",
                    display={"show": {"mode": ["llm"]}},
                ),
                NodeField(
                    name="model_id",
                    label="Model",
                    type="options",
                    default="",
                    description="Optional model override for LLM routing.",
                    load_options_from="models",
                    display={"show": {"mode": ["llm"]}},
                ),
                NodeField(
                    name="output_format",
                    label="Output format",
                    type="options",
                    default="category_with_reason",
                    options=[
                        {"name": "Category only", "value": "category_only"},
                        {"name": "Category + reason", "value": "category_with_reason"},
                    ],
                    display={"show": {"mode": ["llm"]}},
                ),
                NodeField(
                    name="rules",
                    label="Rules",
                    type="fixedCollection",
                    default=[],
                    description="Pattern → category rules (regex/keyword).",
                    type_options={"multipleValues": True},
                    display={"show": {"mode": ["rules"]}},
                ),
            ]
        ),
    )

    agent_node = NodeDefinition(
        kind="agent",
        label="Agent",
        description="Runs an agent loop — either an existing agent with overrides, or a fully custom inline agent.",
        icon="bot",
        default_parameters={"mode": "custom", "temperature": 0.7, "max_iterations": 12},
        fields=_with_common(
            [
                NodeField(
                    name="mode",
                    label="Mode",
                    type="options",
                    default="custom",
                    options=[
                        {"name": "Custom", "value": "custom"},
                        {"name": "Use existing agent", "value": "inherit"},
                    ],
                    description="Run an inline agent or use an existing agent as the base.",
                ),
                NodeField(
                    name="agent_id",
                    label="Load from Agent (Optional)",
                    type="options",
                    default="",
                    load_options_from="agents",
                    description="Select an agent to copy its system prompt, model, and tools into this node.",
                ),
                NodeField(
                    name="system_prompt",
                    label="System prompt",
                    type="textarea",
                    default="You are a helpful workflow agent.",
                ),
                NodeField(
                    name="instructions",
                    label="Task instructions for this step",
                    type="textarea",
                    default="",
                    description="What this node should do with the upstream data, layered onto it as the task message — kept separate from the agent's own system_prompt/persona above.",
                ),
                NodeField(
                    name="model_id",
                    label="Model",
                    type="options",
                    default="",
                    load_options_from="models",
                ),
                NodeField(
                    name="tools",
                    label="Tools",
                    type="multiOptions",
                    default=[],
                    load_options_from="tools",
                ),
                NodeField(
                    name="temperature",
                    label="Temperature",
                    type="number",
                    default=0.7,
                    type_options={"minValue": 0, "maxValue": 2, "numberPrecision": 1},
                ),
                NodeField(
                    name="max_iterations",
                    label="Max iterations",
                    type="number",
                    default=12,
                    type_options={"minValue": 1, "maxValue": 100},
                ),
                NodeField(
                    name="enable_thinking",
                    label="Enable thinking",
                    type="boolean",
                    default=False,
                ),
            ]
        ),
    )

    tool_node = NodeDefinition(
        kind="tool",
        label="Tool",
        description="Invokes a registered tool (builtin, MCP, or customer-intelligence).",
        icon="wrench",
        default_parameters={"tool": ""},
        fields=_with_common(
            [
                NodeField(
                    name="tool",
                    label="Tool",
                    type="options",
                    default="",
                    required=True,
                    load_options_from="tools",
                ),
                NodeField(
                    name="arguments",
                    label="Arguments",
                    type="json",
                    default={},
                    description="Tool arguments as JSON. Input-mapped fields override same-named static arguments.",
                ),
            ]
        ),
    )

    merge_node = NodeDefinition(
        kind="merge",
        label="Merge",
        description="Joins parallel branches into a single text output.",
        icon="merge",
        default_parameters={"merge_mode": "all", "separator": "\n\n"},
        fields=_with_common(
            [
                NodeField(
                    name="merge_mode",
                    label="Merge logic",
                    type="options",
                    default="all",
                    options=[
                        {"name": "Wait all ancestors", "value": "all"},
                        {"name": "Wait any ancestor", "value": "any"},
                    ],
                ),
                NodeField(
                    name="separator",
                    label="Separator",
                    type="string",
                    default="\n\n",
                    description="Separator between merged outputs.",
                ),
            ]
        ),
    )

    approval_node = NodeDefinition(
        kind="approval",
        label="Approval",
        description="Pauses the workflow for a human decision before continuing.",
        icon="shield-check",
        default_parameters={"title": "Approve this workflow step"},
        fields=_with_common(
            [
                NodeField(
                    name="title",
                    label="Title",
                    type="string",
                    default="Approve this workflow step",
                    description="Title shown to the approver.",
                ),
                NodeField(
                    name="instructions",
                    label="Instructions",
                    type="textarea",
                    default="",
                    description="Context shown to the approver.",
                ),
                NodeField(
                    name="approver_user_ids",
                    label="Approvers",
                    type="multiOptions",
                    default=[],
                    description="Users allowed to approve. Empty = anyone with approval permission.",
                    load_options_from="users",
                ),
                NodeField(
                    name="timeout_minutes",
                    label="Timeout (minutes)",
                    type="number",
                    default=0,
                    description="Auto-decline after this many minutes. 0 = no timeout.",
                    type_options={"minValue": 0},
                ),
            ]
        ),
    )

    sub_workflow_node = NodeDefinition(
        kind="sub_workflow",
        label="Sub-workflow",
        description="Runs another workflow inline and returns its output.",
        icon="git-branch",
        default_parameters={"workflow_id": ""},
        fields=_with_common(
            [
                NodeField(
                    name="workflow_id",
                    label="Workflow",
                    type="options",
                    default="",
                    required=True,
                    load_options_from="workflows",
                ),
            ]
        ),
    )

    output_node = NodeDefinition(
        kind="output",
        label="Output",
        description="Collects the final result of the workflow.",
        icon="log-out",
        default_parameters={"include": "all_inputs", "format": "text", "save_as_file": False},
        fields=_with_common(
            [
                NodeField(
                    name="include",
                    label="Include",
                    type="options",
                    default="all_inputs",
                    options=[
                        {"name": "All upstream inputs", "value": "all_inputs"},
                        {"name": "Selected nodes", "value": "selected"},
                    ],
                ),
                NodeField(
                    name="selected_from",
                    label="Selected nodes",
                    type="multiOptions",
                    default=[],
                    description="Upstream node ids to include.",
                    load_options_from="categories",  # backend resolves to upstream node ids
                    display={"show": {"include": ["selected"]}},
                ),
                NodeField(
                    name="format",
                    label="Format",
                    type="options",
                    default="text",
                    options=[
                        {"name": "Text", "value": "text"},
                        {"name": "JSON", "value": "json"},
                    ],
                ),
                NodeField(
                    name="save_as_file",
                    label="Save as workspace file",
                    type="boolean",
                    default=False,
                    description="Write the final output to a markdown file in the org's Sandbox workspace on every run.",
                ),
                NodeField(
                    name="file_name",
                    label="File name",
                    type="string",
                    default="",
                    placeholder="workflow-outputs/my-brief.md",
                    description="Relative workspace path. Defaults to workflow-outputs/<workflow id>.md; each run overwrites it.",
                    display={"show": {"save_as_file": [True]}},
                ),
                NodeField(
                    name="channel_connection_id",
                    label="Post to channel",
                    type="options",
                    default="",
                    description="Send the final output to a connected Telegram/Discord channel on every run.",
                    load_options_from="channels",
                ),
                NodeField(
                    name="channel_recipient",
                    label="Recipient (chat/channel ID)",
                    type="string",
                    default="",
                    placeholder="e.g. -1001234567890",
                    description="Telegram chat ID or Discord channel ID to deliver to. Only used when 'Post to channel' above is set.",
                ),
            ]
        ),
    )

    return {
        d.kind: d
        for d in [
            input_node,
            scheduler_node,
            integration_node,
            triager_node,
            agent_node,
            tool_node,
            merge_node,
            approval_node,
            sub_workflow_node,
            output_node,
        ]
    }


NODE_DEFINITIONS: dict[str, NodeDefinition] = _build_definitions()


def get_node_definition(kind: str) -> NodeDefinition | None:
    return NODE_DEFINITIONS.get(kind)
