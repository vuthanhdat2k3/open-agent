"use client";

import { CheckCircle2, Loader2, Wrench, XCircle, Bot, Terminal } from "lucide-react";
import type { ToolCallBlock } from "@/lib/chat/projection";

interface ToolCallChipProps {
  block: ToolCallBlock;
}

export function ToolCallChip({ block }: ToolCallChipProps) {
  const isSubagent = block.name === "call_agent" || block.name.startsWith("delegate_to_") || Boolean(block.subagent);
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

  const subagentName = block.subagent?.agentName || (block.name.startsWith("delegate_to_") ? block.name.replace(/^delegate_to_/, "").replace(/_/g, " ") : null);
  const displayName = subagentName ? `subagent: ${subagentName}` : block.name;

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-muted/30 px-2.5 py-0.5 text-[11px] text-muted-foreground select-none"
      title={`${displayName} — ${block.status}`}
    >
      {statusIcon}
      {kindIcon}
      <span className="font-mono text-[10.5px]">{displayName}</span>
    </span>
  );
}


