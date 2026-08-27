from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

NodeKind = Literal[
    "input",
    "agent",
    "tool",
    "merge",
    "output",
    "approval",
    "sub_workflow",
    "scheduler",
    "triager",
    "integration",
]
MergeMode = Literal["all", "any"]


class GraphNode(BaseModel):
    id: str
    kind: NodeKind
    label: str = ""
    agent_id: str | None = None  # for kind == "agent", mode == "inherit"
    merge_mode: MergeMode = "all"  # for kind == "merge"
    parameters: dict[str, Any] = {}  # validated per NodeDefinition
    config: dict[str, Any] = {}  # DEPRECATED: read fallback only


class GraphEdge(BaseModel):
    from_: str
    to: str
    condition: str | None = None  # optional guard expression


class NodeOutput(BaseModel):
    """Unified output contract for every workflow node."""

    text: str = ""
    data: dict[str, Any] = {}
    error: str | None = None


class WorkflowGraph(BaseModel):
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []


class WorkflowBase(BaseModel):
    name: str
    description: str = ""
    graph: WorkflowGraph = WorkflowGraph()


class WorkflowCreate(WorkflowBase):
    pass


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    graph: WorkflowGraph | None = None


class WorkflowOut(WorkflowBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class RunWorkflowRequest(BaseModel):
    input: str
    stream: bool = True
    workflow_run_id: str | None = None
    timezone: str | None = None
    trigger_node_id: str | None = None


class WorkflowGenerateRequest(BaseModel):
    prompt: str
    model_id: str


class WorkflowGenerateResponse(BaseModel):
    name: str
    description: str = ""
    graph: WorkflowGraph


class WorkflowRunEvent(BaseModel):
    event: str  # "node_start" | "node_done" | "node_error" | "edge" | "done" | "error"
    node_id: str | None = None
    data: dict[str, Any] = {}


class WorkflowValidationError(ValueError):
    """Graph validation failed with structured per-node/per-field errors."""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("workflow graph validation failed")
        self.errors = errors
