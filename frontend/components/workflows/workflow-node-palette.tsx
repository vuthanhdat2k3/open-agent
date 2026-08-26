"use client";

import * as React from "react";
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
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { GraphNode } from "@/types";

const PALETTE_ITEMS: { kind: GraphNode["kind"]; icon: typeof Box; label: string; description: string }[] = [
  { kind: "input", icon: Box, label: "Input", description: "Entry point for on-demand requests" },
  { kind: "scheduler", icon: Clock, label: "Scheduler", description: "Automated cron or recurring trigger" },
  { kind: "integration", icon: Cable, label: "Integration", description: "Fetch Gmail, Calendar, Drive data" },
  { kind: "triager", icon: GitFork, label: "Triager", description: "Classify & branch requests by intent" },
  { kind: "agent", icon: Bot, label: "Agent", description: "Invoke an AI agent" },
  { kind: "tool", icon: Wrench, label: "Tool", description: "Call a built-in or MCP tool" },
  { kind: "merge", icon: GitMerge, label: "Merge", description: "Combine multiple branches" },
  { kind: "approval", icon: ShieldAlert, label: "Approval", description: "Pause for human approval" },
  { kind: "output", icon: LogOut, label: "Output", description: "Final workflow result" },
  { kind: "sub_workflow", icon: WorkflowIcon, label: "Sub-workflow", description: "Run another workflow" },
];

export const WORKFLOW_DND_MIME = "application/x-openagent-node-kind";

interface WorkflowNodePaletteProps {
  className?: string;
  onAddNode?: (kind: GraphNode["kind"]) => void;
}

export function WorkflowNodePalette({ className, onAddNode }: WorkflowNodePaletteProps) {
  const [collapsed, setCollapsed] = React.useState(false);

  const onDragStart = (e: React.DragEvent, kind: GraphNode["kind"]) => {
    e.dataTransfer.setData(WORKFLOW_DND_MIME, kind);
    e.dataTransfer.effectAllowed = "move";
  };

  return (
    <div
      className={cn(
        "flex flex-col gap-2 rounded-xl border border-border/80 bg-card/50 p-3 backdrop-blur-xl shadow-3d-card transition-[width] duration-200",
        collapsed ? "w-[60px]" : "w-[220px]",
        className,
      )}
    >
      <div className="flex items-center justify-between">
        {!collapsed && (
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
            Node palette
          </span>
        )}
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expand palette" : "Collapse palette"}
          title={collapsed ? "Expand palette" : "Collapse palette"}
          className="ml-auto grid h-6 w-6 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          {collapsed ? <ChevronsRight className="h-3.5 w-3.5" /> : <ChevronsLeft className="h-3.5 w-3.5" />}
        </button>
      </div>

      <div className="flex flex-col gap-1.5">
        {PALETTE_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.kind}
              type="button"
              draggable
              onDragStart={(e) => onDragStart(e, item.kind)}
              onClick={() => onAddNode?.(item.kind)}
              title={`${item.label} — ${item.description}${onAddNode ? " (click to add)" : ""}`}
              aria-label={`Add ${item.label} node — ${item.description}`}
              className={cn(
                "flex cursor-grab items-center gap-2 rounded-lg border border-border/40 bg-muted/30 px-2 py-2 text-left text-xs transition-colors hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing",
                collapsed && "justify-center",
              )}
            >
              <Icon className="h-4 w-4 shrink-0 text-foreground/80" />
              {!collapsed && (
                <div className="flex min-w-0 flex-col">
                  <span className="truncate font-medium text-foreground">{item.label}</span>
                  <span className="truncate text-[10px] leading-tight text-muted-foreground/70">
                    {item.description}
                  </span>
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
