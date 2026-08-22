"use client";

import * as React from "react";
import { Clock, DollarSign, Wrench, Cpu, AlertCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { StatsBlock } from "@/lib/chat/projection";

interface StatsLineProps {
  block: StatsBlock;
}

export function StatsLine({ block }: StatsLineProps) {
  if (block.noAnswer) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-destructive mt-1">
        <AlertCircle className="h-3.5 w-3.5" />
        <span>No answer was generated. Please try again.</span>
      </div>
    );
  }

  const hasAnyStat =
    block.tokensIn != null ||
    block.tokensOut != null ||
    block.costUsd != null ||
    block.latencyMs != null ||
    block.model ||
    block.toolCount;

  if (!hasAnyStat) return null;

  const totalTokens = (block.tokensIn ?? 0) + (block.tokensOut ?? 0);

  return (
    <div className="flex flex-wrap items-center gap-1.5 pt-1 text-muted-foreground">
      {block.latencyMs != null && (
        <Badge variant="secondary" className="gap-1 font-mono text-[10px] px-1.5 py-0">
          <Clock className="h-2.5 w-2.5" aria-hidden="true" />
          {(block.latencyMs / 1000).toFixed(1)}s
        </Badge>
      )}

      {totalTokens > 0 && (
        <Badge variant="secondary" className="gap-1 font-mono text-[10px] px-1.5 py-0">
          <Cpu className="h-2.5 w-2.5" aria-hidden="true" />
          {block.tokensIn != null && block.tokensOut != null ? (
            <span>
              ↑{block.tokensIn} ↓{block.tokensOut}
            </span>
          ) : (
            <span>{totalTokens} tokens</span>
          )}
        </Badge>
      )}

      {block.costUsd != null && (
        <Badge variant="secondary" className="gap-1 font-mono text-[10px] px-1.5 py-0">
          <DollarSign className="h-2.5 w-2.5" aria-hidden="true" />
          {block.costUsd < 0.0001 && block.costUsd > 0
            ? block.costUsd.toExponential(2)
            : block.costUsd.toFixed(4)}
        </Badge>
      )}

      {block.toolCount != null && block.toolCount > 0 && (
        <Badge variant="secondary" className="gap-1 font-mono text-[10px] px-1.5 py-0">
          <Wrench className="h-2.5 w-2.5" aria-hidden="true" />
          {block.toolCount} tool{block.toolCount > 1 ? "s" : ""}
        </Badge>
      )}

      {block.model && (
        <Badge variant="outline" className="ml-auto font-mono text-[10px] px-1.5 py-0 border-border/50 text-muted-foreground">
          {block.model}
        </Badge>
      )}
    </div>
  );
}
