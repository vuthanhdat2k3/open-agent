"use client";

import { CheckCircle2, Loader2, Wrench, XCircle } from "lucide-react";
import type { ToolCallBlock } from "@/lib/chat/projection";

interface ToolCallChipProps {
  block: ToolCallBlock;
}

export function ToolCallChip({ block }: ToolCallChipProps) {
  const icon =
    block.status === "running" ? (
      <Loader2 className="h-3 w-3 animate-spin text-primary/80" aria-hidden="true" />
    ) : block.status === "error" ? (
      <XCircle className="h-3 w-3 text-destructive" aria-hidden="true" />
    ) : (
      <CheckCircle2 className="h-3 w-3 text-success" aria-hidden="true" />
    );

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-muted/30 px-2.5 py-0.5 text-[11px] text-muted-foreground"
      title={`${block.name} — ${block.status}`}
    >
      {icon}
      <Wrench className="h-3 w-3 text-muted-foreground/60" aria-hidden="true" />
      <span className="font-mono">{block.name}</span>
    </span>
  );
}
