from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict

NodeKind = Literal["input", "agent", "tool", "merge", "output"]
MergeMode = Literal["all", "any"]


class GraphNode(BaseModel):
    id: str
    kind: NodeKind
    label: str = ""
    agent_id: Optional[str] = None  # for kind == "agent"
    merge_mode: MergeMode = "all"   # for kind == "merge"
    config: dict[str, Any] = {}


class GraphEdge(BaseModel):
    from_: str
    to: str
    condition: Optional[str] = None  # optional guard expression


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
    name: Optional[str] = None
    description: Optional[str] = None
    graph: Optional[WorkflowGraph] = None


class WorkflowOut(WorkflowBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class RunWorkflowRequest(BaseModel):
    input: str
    stream: bool = True


class WorkflowRunEvent(BaseModel):
    event: str  # "node_start" | "node_done" | "node_error" | "edge" | "done" | "error"
    node_id: Optional[str] = None
    data: dict[str, Any] = {}
