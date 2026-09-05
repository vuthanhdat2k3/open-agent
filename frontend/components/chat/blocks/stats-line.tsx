"use client";

import * as React from "react";
import { AlertCircle } from "lucide-react";
import type { StatsBlock } from "@/lib/chat/projection";
import { useTranslation } from "@/lib/i18n";

interface StatsLineProps {
  block: StatsBlock;
  debug?: boolean;
}

function formatTokens(n: number): string {
  const scaled = (v: number): string =>
    v >= 100 ? String(Math.round(v)) : String(Math.round(v * 10) / 10);
  if (n < 1_000) return String(n);
  if (n < 1_000_000) return `${scaled(n / 1_000)}K`;
  return `${scaled(n / 1_000_000)}M`;
}

function formatDuration(ms: number, debug?: boolean): string {
  if (debug) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  if (s < 60) return `${Math.round(s * 10) / 10}s`;
  const whole = Math.round(s);
  const minutes = Math.floor(whole / 60);
  const seconds = whole % 60;
  return `${minutes}m${String(seconds).padStart(2, "0")}s`;
}

export function StatsLine({ block, debug }: StatsLineProps) {
    const { locale, tx } = useTranslation();
  if (block.noAnswer) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-destructive mt-1 font-mono">
        <AlertCircle className="h-3.5 w-3.5" />
        <span>{tx("Không có câu trả lời được tạo. Vui lòng thử lại.", "No answer was generated. Please try again.")}</span>
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

  if (!hasAnyStat && !debug) return null;

  const totalTokens = (block.tokensIn ?? 0) + (block.tokensOut ?? 0);
  const items: React.ReactNode[] = [];

  if (block.latencyMs != null) {
    items.push(<span key="lat">{formatDuration(block.latencyMs, debug)}</span>);
  }

  if (totalTokens > 0) {
    const detail = debug
      ? `in: ${block.tokensIn ?? 0} · out: ${block.tokensOut ?? 0} (${totalTokens} tok)`
      : block.tokensIn != null && block.tokensOut != null
        ? `↑${formatTokens(block.tokensIn)} ↓${formatTokens(block.tokensOut)} (${formatTokens(totalTokens)})`
        : `${formatTokens(totalTokens)} tokens`;
    items.push(<span key="tok">{detail}</span>);
  }

  if (block.costUsd != null && block.costUsd > 0) {
    const formattedCost = debug
      ? `$${block.costUsd.toFixed(6)}`
      : block.costUsd < 0.0001
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

  if (debug) {
    items.push(
      <span key="dbg-tag" className="rounded bg-primary/10 px-1 py-0.2 text-[10px] font-semibold text-primary">
        {tx("TRACE", "TRACE")}</span>
    );
  }

  return (
    <div className={`flex flex-wrap items-center gap-x-2 pt-1 font-mono leading-5 select-none ${debug ? "text-[11px] text-foreground/75" : "text-[12px] text-muted-foreground/75"}`}>
      {items.map((item, idx) => (
        <React.Fragment key={idx}>
          {idx > 0 && <span className="opacity-40 select-none">·</span>}
          {item}
        </React.Fragment>
      ))}
    </div>
  );
}
