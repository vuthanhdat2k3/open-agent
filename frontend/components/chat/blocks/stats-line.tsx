"use client";

import * as React from "react";
import { AlertCircle } from "lucide-react";
import type { StatsBlock } from "@/lib/chat/projection";

interface StatsLineProps {
  block: StatsBlock;
}

function formatTokens(n: number): string {
  const scaled = (v: number): string =>
    v >= 100 ? String(Math.round(v)) : String(Math.round(v * 10) / 10);
  if (n < 1_000) return String(n);
  if (n < 1_000_000) return `${scaled(n / 1_000)}K`;
  return `${scaled(n / 1_000_000)}M`;
}

function formatDuration(ms: number): string {
  const s = ms / 1000;
  if (s < 60) return `${Math.round(s * 10) / 10}s`;
  const whole = Math.round(s);
  const minutes = Math.floor(whole / 60);
  const seconds = whole % 60;
  return `${minutes}m${String(seconds).padStart(2, "0")}s`;
}

export function StatsLine({ block }: StatsLineProps) {
  if (block.noAnswer) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-destructive mt-1 font-mono">
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
  const items: React.ReactNode[] = [];

  if (block.latencyMs != null) {
    items.push(<span key="lat">{formatDuration(block.latencyMs)}</span>);
  }

  if (totalTokens > 0) {
    const detail =
      block.tokensIn != null && block.tokensOut != null
        ? `↑${formatTokens(block.tokensIn)} ↓${formatTokens(block.tokensOut)} (${formatTokens(totalTokens)})`
        : `${formatTokens(totalTokens)} tokens`;
    items.push(<span key="tok">{detail}</span>);
  }

  if (block.costUsd != null && block.costUsd > 0) {
    const formattedCost =
      block.costUsd < 0.0001
        ? `$${block.costUsd.toExponential(2)}`
        : `$${block.costUsd.toFixed(4)}`;
    items.push(<span key="cost">{formattedCost}</span>);
  }

  if (block.toolCount != null && block.toolCount > 0) {
    items.push(
      <span key="tools">
        {block.toolCount} {block.toolCount === 1 ? "tool" : "tools"}
      </span>
    );
  }

  if (block.model) {
    items.push(<span key="model" className="opacity-90">{block.model}</span>);
  }

  return (
    <div className="flex flex-wrap items-center gap-x-2 pt-1 text-[12px] font-mono leading-5 text-muted-foreground/75 select-none">
      {items.map((item, idx) => (
        <React.Fragment key={idx}>
          {idx > 0 && <span className="opacity-40 select-none">·</span>}
          {item}
        </React.Fragment>
      ))}
    </div>
  );
}
