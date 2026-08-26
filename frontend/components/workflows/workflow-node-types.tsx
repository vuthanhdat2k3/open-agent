"use client";

import * as React from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  Box,
  Bot,
  Wrench,
  GitMerge,
  LogOut,
  ShieldAlert,
  Workflow as WorkflowIcon,
  Clock,
  GitFork,
  Cable,
  AlertCircle,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { GraphNode } from "@/types";

export type NodeStatus = "idle" | "running" | "done" | "error";

export type WorkflowNodeData = {
  label: string;
  kind: GraphNode["kind"];
  status: NodeStatus;
};

const KIND_META: Record<GraphNode["kind"], { icon: LucideIcon; description: string }> = {
  input: { icon: Box, description: "Input" },
  agent: { icon: Bot, description: "Agent" },
  tool: { icon: Wrench, description: "Tool" },
  merge: { icon: GitMerge, description: "Merge" },
  output: { icon: LogOut, description: "Output" },
  approval: { icon: ShieldAlert, description: "Approval" },
  sub_workflow: { icon: WorkflowIcon, description: "Sub-workflow" },
  scheduler: { icon: Clock, description: "Scheduler" },
  triager: { icon: GitFork, description: "Triager" },
  integration: { icon: Cable, description: "Integration" },
};

const statusBorderClass: Record<NodeStatus, string> = {
  idle: "border-border/80 hover:border-primary/40 hover:shadow-3d-card",
  running: "border-info shadow-[0_0_20px_hsl(var(--info)/0.35)] animate-pulse-soft",
  done: "border-success shadow-3d-card",
  error: "border-destructive shadow-3d-card",
};

function BaseWorkflowNode({ data, selected }: NodeProps & { data: WorkflowNodeData }) {
  const meta = KIND_META[data.kind];
  const Icon = meta.icon;
  const isApproval = data.kind === "approval";

  const badgeClass = isApproval
    ? "bg-warning/15 border-warning/40 text-warning"
    : "bg-muted/50 border-border/60 text-foreground/80";

  return (
    <div
      className={cn(
        "relative flex h-[88px] w-[200px] select-none flex-col justify-between rounded-2xl border bg-card/90 p-3 text-xs shadow-3d-card backdrop-blur-xl transition-[border-color,box-shadow,transform,background-color] duration-200",
        statusBorderClass[data.status],
        selected && data.status === "idle" && "ring-2 ring-primary border-primary/60",
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-3 !w-3 !border !border-border !bg-background transition-transform hover:!scale-125 hover:!border-primary"
      />
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-3 !w-3 !border !border-border !bg-background transition-transform hover:!scale-125 hover:!border-primary"
      />

      <div className="flex items-center gap-2">
        <div
          className={cn(
            "grid h-8 w-8 shrink-0 place-items-center rounded-xl border",
            badgeClass,
          )}
        >
          <Icon className="h-5 w-5" />
        </div>
        <div className="flex min-w-0 flex-col">
          <span className="truncate text-[11px] font-semibold capitalize leading-tight text-foreground">
            {meta.description}
          </span>
          <span className="truncate text-[10px] leading-tight text-muted-foreground/80">
            {data.label}
          </span>
        </div>
        {data.status === "error" && (
          <AlertCircle className="ml-auto h-3.5 w-3.5 shrink-0 text-destructive" />
        )}
      </div>

      <div className="truncate rounded border border-border/30 bg-muted/30 px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground/80">
        {data.kind}
      </div>
    </div>
  );
}

export const workflowNodeTypes = {
  input: BaseWorkflowNode,
  agent: BaseWorkflowNode,
  tool: BaseWorkflowNode,
  merge: BaseWorkflowNode,
  output: BaseWorkflowNode,
  approval: BaseWorkflowNode,
  sub_workflow: BaseWorkflowNode,
};

export const NODE_KIND_META = KIND_META;
