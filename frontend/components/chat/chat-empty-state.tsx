"use client";

import { Bot, Cpu } from "lucide-react";
import type { Agent, Model } from "@/types";

interface ChatEmptyStateProps {
  currentAgent?: Agent;
  effectiveModel?: Model;
}

export function ChatEmptyState({ currentAgent, effectiveModel }: ChatEmptyStateProps) {
  return (
    <div className="m-auto max-w-sm animate-scale-in text-center">
      <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl border border-primary/25 bg-primary/10 text-primary shadow-inner-edge">
        <Bot className="h-6 w-6" aria-hidden="true" />
      </div>
      <p className="text-sm font-semibold tracking-tight">Ready to prompt</p>
      <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
        Start a conversation with <span className="font-medium text-foreground">{currentAgent?.name ?? "the selected agent"}</span>.
        Tool actions will appear inline.
      </p>
      {effectiveModel && (
        <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-border/40 bg-muted/40 px-3 py-1">
          <Cpu className="h-3 w-3 text-primary" aria-hidden="true" />
          <span className="font-mono text-[11px] text-muted-foreground">
            {effectiveModel.display_name || effectiveModel.name}
          </span>
        </div>
      )}
    </div>
  );
}
