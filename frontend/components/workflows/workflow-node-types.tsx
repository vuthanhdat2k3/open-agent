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
  CheckCircle2,
  Loader2,
  X,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { GraphNode } from "@/types";

export type NodeStatus = "idle" | "running" | "done" | "error";

export type WorkflowNodeData = {
  label: string;
  kind: GraphNode["kind"];
  status: NodeStatus;
  onDelete?: (id: string) => void;
  onInspect?: (id: string) => void;
};

const KIND_META: Record<
  GraphNode["kind"],
  {
    icon: LucideIcon;
    description: string;
    badgeClass: string;
    chipClass: string;
  }
> = {
  input: {
    icon: Box,
    description: "Input Trigger",
    badgeClass: "bg-emerald-500/15 border-emerald-500/30 text-emerald-600 dark:text-emerald-400",
    chipClass: "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  },
  scheduler: {
    icon: Clock,
    description: "Scheduled Trigger",
    badgeClass: "bg-amber-500/15 border-amber-500/30 text-amber-600 dark:text-amber-400",
    chipClass: "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  },
  integration: {
    icon: Cable,
    description: "Integration Connector",
    badgeClass: "bg-sky-500/15 border-sky-500/30 text-sky-600 dark:text-sky-400",
    chipClass: "border-sky-500/20 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  },
  triager: {
    icon: GitFork,
    description: "Triage & Router",
    badgeClass: "bg-purple-500/15 border-purple-500/30 text-purple-600 dark:text-purple-400",
    chipClass: "border-purple-500/20 bg-purple-500/10 text-purple-700 dark:text-purple-300",
  },
  agent: {
    icon: Bot,
    description: "AI Agent",
    badgeClass: "bg-indigo-500/15 border-indigo-500/30 text-indigo-600 dark:text-indigo-400",
    chipClass: "border-indigo-500/20 bg-indigo-500/10 text-indigo-700 dark:text-indigo-300",
  },
  tool: {
    icon: Wrench,
    description: "Tool Executor",
    badgeClass: "bg-blue-500/15 border-blue-500/30 text-blue-600 dark:text-blue-400",
    chipClass: "border-blue-500/20 bg-blue-500/10 text-blue-700 dark:text-blue-300",
  },
  approval: {
    icon: ShieldAlert,
    description: "Human Approval",
    badgeClass: "bg-amber-500/20 border-amber-500/40 text-amber-600 dark:text-amber-400",
    chipClass: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  },
  merge: {
    icon: GitMerge,
    description: "Branch Join",
    badgeClass: "bg-orange-500/15 border-orange-500/30 text-orange-600 dark:text-orange-400",
    chipClass: "border-orange-500/20 bg-orange-500/10 text-orange-700 dark:text-orange-300",
  },
  sub_workflow: {
    icon: WorkflowIcon,
    description: "Sub-Workflow",
    badgeClass: "bg-violet-500/15 border-violet-500/30 text-violet-600 dark:text-violet-400",
    chipClass: "border-violet-500/20 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  },
  output: {
    icon: LogOut,
    description: "Output Collector",
    badgeClass: "bg-rose-500/15 border-rose-500/30 text-rose-600 dark:text-rose-400",
    chipClass: "border-rose-500/20 bg-rose-500/10 text-rose-700 dark:text-rose-300",
  },
};

const statusBorderClass: Record<NodeStatus, string> = {
  idle: "border-border/80 hover:border-primary/50 hover:shadow-3d-card",
  running: "border-info shadow-[0_0_25px_hsl(var(--info)/0.45)] ring-2 ring-info/60 animate-pulse",
  done: "border-emerald-500/80 shadow-[0_0_15px_rgba(16,185,129,0.25)] ring-1 ring-emerald-500/40",
  error: "border-destructive/80 shadow-[0_0_18px_rgba(239,68,68,0.3)] ring-1 ring-destructive/40",
};

function BaseWorkflowNode({ id, data, selected }: NodeProps & { data: WorkflowNodeData }) {
  const meta = KIND_META[data.kind] || {
    icon: Box,
    description: data.kind,
    badgeClass: "bg-muted/50 border-border/60 text-foreground/80",
    chipClass: "border-border/30 bg-muted/30 text-muted-foreground/80",
  };
  const Icon = meta.icon;

  return (
    <div
      className={cn(
        "group relative flex h-[94px] w-[214px] select-none flex-col justify-between rounded-2xl border bg-card/95 p-3 text-xs shadow-3d-card backdrop-blur-xl transition-all duration-200",
        statusBorderClass[data.status],
        selected && data.status === "idle" && "ring-2 ring-primary border-primary/80 shadow-lg",
      )}
    >
      {/* Running pulse radar wave */}
      {data.status === "running" && (
        <span className="pointer-events-none absolute -inset-0.5 rounded-2xl bg-info/20 animate-ping opacity-60" />
      )}

      {/* Node Delete Button on hover or when selected */}
      {data.onDelete && (
        <button
          type="button"
          title="Delete node"
          aria-label="Delete node"
          onClick={(e) => {
            e.stopPropagation();
            data.onDelete?.(id);
          }}
          className={cn(
            "absolute -right-2 -top-2 z-10 grid h-5 w-5 place-items-center rounded-full border border-border/80 bg-destructive text-destructive-foreground opacity-0 shadow-md transition-all duration-150 hover:scale-110 hover:bg-destructive/90 focus-visible:opacity-100",
            "group-hover:opacity-100",
            selected && "opacity-100",
          )}
        >
          <X className="h-3 w-3 stroke-[2.5]" />
        </button>
      )}

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

      <div className="flex items-center gap-2.5 relative z-10">
        <div
          className={cn(
            "grid h-8 w-8 shrink-0 place-items-center rounded-xl border shadow-inner-edge relative",
            meta.badgeClass,
          )}
        >
          <Icon className="h-4.5 w-4.5" />
          {data.status === "running" && (
            <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-info ring-2 ring-background animate-pulse" />
          )}
        </div>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[11px] font-bold leading-tight text-foreground">
            {data.label || meta.description}
          </span>
          <span className="truncate text-[10px] font-medium leading-tight text-muted-foreground/80">
            {meta.description}
          </span>
        </div>
        {data.status === "running" && (
          <Loader2 className="ml-auto h-4 w-4 shrink-0 text-info animate-spin" />
        )}
        {data.status === "done" && (
          <CheckCircle2 className="ml-auto h-4 w-4 shrink-0 text-emerald-500" />
        )}
        {data.status === "error" && (
          <AlertCircle className="ml-auto h-4 w-4 shrink-0 text-destructive animate-pulse" />
        )}
      </div>

      <div className="flex items-center justify-between gap-1 pt-1 relative z-10">
        <div
          className={cn(
            "truncate rounded-md border px-1.5 py-0.5 font-mono text-[9px] font-medium tracking-tight",
            meta.chipClass,
          )}
        >
          {data.kind}
        </div>
        <div className="text-[9px] font-mono text-muted-foreground/70 uppercase font-semibold">
          {data.status !== "idle" ? data.status : ""}
        </div>
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
  scheduler: BaseWorkflowNode,
  triager: BaseWorkflowNode,
  integration: BaseWorkflowNode,
};

export const NODE_KIND_META = KIND_META;
