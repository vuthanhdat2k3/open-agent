"use client";

import { CheckCircle2, Loader2, Wrench, XCircle, Bot, Terminal, ChevronDown } from "lucide-react";
import type { ToolCallBlock } from "@/lib/chat/projection";

interface ToolCallChipProps {
  block: ToolCallBlock;
  active?: boolean;
  onClick?: () => void;
}

export function ToolCallChip({ block, active = false, onClick }: ToolCallChipProps) {
  const isSubagent = block.name === "call_agent" || Boolean(block.subagent);
  const isCode = block.name === "run_code" || block.name === "write_file";

  const statusIcon =
    block.status === "running" ? (
      <Loader2 className="h-3 w-3 animate-spin text-primary" aria-hidden="true" />
    ) : block.status === "error" ? (
      <XCircle className="h-3 w-3 text-destructive" aria-hidden="true" />
    ) : (
      <CheckCircle2 className="h-3 w-3 text-success" aria-hidden="true" />
    );

  const kindIcon = isSubagent ? (
    <Bot className="h-3 w-3 text-indigo-400" aria-hidden="true" />
  ) : isCode ? (
    <Terminal className="h-3 w-3 text-primary/80" aria-hidden="true" />
  ) : (
    <Wrench className="h-3 w-3 text-muted-foreground/60" aria-hidden="true" />
  );

  const displayName = block.subagent?.agentName ? `subagent: ${block.subagent.agentName}` : block.name;

  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] transition-all cursor-pointer select-none ${
        active
          ? "border-primary bg-primary/10 text-foreground shadow-sm ring-1 ring-primary/30"
          : block.status === "running"
            ? "border-primary/50 bg-primary/5 text-foreground animate-pulse"
            : "border-border/60 bg-muted/30 text-muted-foreground hover:border-border hover:bg-muted/60 hover:text-foreground"
      }`}
      title={`${displayName} — ${block.status} (click to toggle details)`}
    >
      {statusIcon}
      {kindIcon}
      <span className="font-mono text-[10.5px] font-medium">{displayName}</span>
      {onClick && (
        <ChevronDown
          className={`h-2.5 w-2.5 text-muted-foreground/60 transition-transform duration-150 ${
            active ? "rotate-180 text-foreground" : ""
          }`}
          aria-hidden="true"
        />
      )}
    </button>
  );
}

