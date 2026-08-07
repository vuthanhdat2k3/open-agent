"use client";

import { Sparkles, Wrench, ShieldAlert } from "lucide-react";
import type { Model } from "@/types";

interface ChatStatusRowProps {
  statusPhase: string;
  effectiveModel?: Model;
}

// Renders the live "thinking / using tool / waiting for approval" row shown
// while a run is in flight. Pure display — statusPhase is computed by the
// page from `phase`/`streaming`, unchanged here.
export function ChatStatusRow({ statusPhase, effectiveModel }: ChatStatusRowProps) {
  const label =
    statusPhase === "approval"
      ? "Waiting for approval"
      : statusPhase.startsWith("tool:")
        ? `Using tool: ${statusPhase.slice(5)}`
        : statusPhase === "result"
          ? "Processing result"
          : statusPhase === "answering"
            ? "Generating answer"
            : "Thinking";

  const Icon = statusPhase === "approval" ? ShieldAlert : statusPhase.startsWith("tool:") ? Wrench : Sparkles;
  const iconColor = statusPhase === "approval" ? "text-warning" : statusPhase.startsWith("tool:") ? "text-info" : "text-primary";

  return (
    <div className="flex max-w-[92%] items-center gap-2 self-start rounded-xl border border-primary/20 bg-primary/[0.04] px-3 py-2 text-[10px] text-muted-foreground shadow-sm">
      <Icon className={`h-3.5 w-3.5 shrink-0 animate-pulse ${iconColor}`} aria-hidden="true" />
      <span>{label}</span>
      {effectiveModel && (
        <span className="font-mono text-muted-foreground/60">
          · {effectiveModel.display_name || effectiveModel.name}
        </span>
      )}
      <span className="ml-auto flex gap-0.5" aria-hidden="true">
        <span className="h-1 w-1 rounded-full bg-current animate-pulse" />
        <span className="h-1 w-1 rounded-full bg-current animate-pulse [animation-delay:150ms]" />
        <span className="h-1 w-1 rounded-full bg-current animate-pulse [animation-delay:300ms]" />
      </span>
    </div>
  );
}
