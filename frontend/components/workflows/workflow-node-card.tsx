"use client";

import * as React from "react";
import { Box, Bot, Wrench, GitMerge, LogOut, Trash2 } from "lucide-react";
import type { Agent } from "@/types";

export type GNode = {
  id: string;
  kind: "input" | "agent" | "tool" | "merge" | "output" | "approval" | "sub_workflow";
  label: string;
  agent_id?: string;
  merge_mode?: "all" | "any";
  config: Record<string, any>;
  position?: { x: number; y: number };
};

interface WorkflowNodeCardProps {
  node: GNode;
  position: { x: number; y: number };
  isSelected: boolean;
  status?: string;
  connectingFromId: string | null;
  onNodeMouseDown: (e: React.MouseEvent, id: string) => void;
  onOutputPortMouseDown: (e: React.MouseEvent, id: string) => void;
  onInputPortMouseUp: (e: React.MouseEvent, id: string) => void;
  onDeleteNode: (id: string) => void;
}

export function WorkflowNodeCard({
  node: n,
  position: p,
  isSelected,
  status,
  connectingFromId,
  onNodeMouseDown,
  onOutputPortMouseDown,
  onInputPortMouseUp,
  onDeleteNode,
}: WorkflowNodeCardProps) {
  const NodeIcon =
    n.kind === "input" ? Box : n.kind === "agent" ? Bot : n.kind === "tool" ? Wrench : n.kind === "merge" ? GitMerge : LogOut;

  const borderColor =
    status === "done"
      ? "border-success bg-success/5 shadow-3d-card"
      : status === "running"
        ? "border-info bg-info/5 shadow-3d-elevated animate-pulse-soft"
        : status === "error"
          ? "border-destructive bg-destructive/5"
          : isSelected
            ? "ring-2 ring-primary border-primary/60 shadow-3d-card"
            : "border-border/80 hover:border-primary/40 hover:shadow-3d-card";

  return (
    <div
      className={`absolute flex w-[160px] h-[70px] select-none cursor-grab active:cursor-grabbing flex-col justify-between rounded-xl border bg-card/95 dark:bg-card/85 p-3 text-xs shadow-3d-card transition-all duration-200 backdrop-blur-md ${borderColor}`}
      style={{ left: p.x, top: p.y }}
      onMouseDown={(e) => onNodeMouseDown(e, n.id)}
    >
      {/* Target Port handle (Left) */}
      <div
        className={`absolute -left-2 top-[25px] h-4.5 w-4.5 rounded-full border border-border bg-background flex items-center justify-center cursor-crosshair z-30 transition-all hover:scale-125 hover:border-primary shadow-sm ${
          connectingFromId && connectingFromId !== n.id ? "animate-pulse-soft border-primary/80 bg-primary/20 scale-110" : ""
        }`}
        onMouseUp={(e) => onInputPortMouseUp(e, n.id)}
        title="Connect parent output here"
      >
        <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground hover:bg-primary" />
      </div>

      {/* Source Port handle (Right) */}
      <div
        className="absolute -right-2 top-[25px] h-4.5 w-4.5 rounded-full border border-border bg-background flex items-center justify-center cursor-crosshair z-30 transition-all hover:scale-125 hover:border-primary shadow-sm"
        onMouseDown={(e) => onOutputPortMouseDown(e, n.id)}
        title="Drag to child input"
      >
        <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground hover:bg-primary" />
      </div>

      <div className="flex items-center justify-between gap-1 font-bold tracking-tight">
        <div className="flex items-center gap-1.5">
          <NodeIcon className="h-3.5 w-3.5 text-primary" /> 
          <span className="capitalize text-foreground">{n.kind}</span>
        </div>
        <button
          className="no-drag text-muted-foreground hover:text-destructive transition-colors p-0.5 rounded hover:bg-muted"
          onClick={(e) => {
            e.stopPropagation();
            onDeleteNode(n.id);
          }}
          title="Delete node"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
      <div className="truncate text-[10px] text-muted-foreground/90 font-mono bg-muted/40 px-1.5 py-0.5 rounded border border-border/30">{n.label}</div>
    </div>
  );
}
