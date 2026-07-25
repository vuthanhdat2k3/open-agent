"use client";

import * as React from "react";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { Wrench, CornerDownRight, Clock, DollarSign } from "lucide-react";

export type UIMessage = {
  id: string;
  role: string;
  content: string;
  meta?: {
    model?: string;
    in_tokens?: number;
    out_tokens?: number;
    cost_usd?: number;
    latency_ms?: number;
    toolName?: string;
    tools?: any[];
  };
};

interface ChatMessageItemProps {
  message: UIMessage;
  debug: boolean;
  hasLiveTools?: boolean;
}

export function ChatMessageItem({ message: m, debug, hasLiveTools }: ChatMessageItemProps) {
  if (!debug && (m.role === "tool_call" || m.role === "tool_result")) return null;

  if (m.role === "user") {
    return (
      <div
        key={m.id}
        className="animate-scale-in self-end max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-xs text-primary-foreground shadow-3d-card leading-relaxed select-text font-medium"
      >
        {m.content || "…"}
      </div>
    );
  }

  if (m.role === "tool_call") {
    const trimmed = m.content.trim();
    let argsText = m.content;
    try {
      if (trimmed.startsWith("{") || trimmed.startsWith("["))
        argsText = JSON.stringify(JSON.parse(m.content), null, 2);
    } catch {}
    return (
      <div
        key={m.id}
        className="animate-scale-in self-start w-full max-w-[92%] rounded-xl border border-amber-500/30 bg-amber-500/[0.06] shadow-sm"
      >
        <div className="flex items-center gap-1.5 border-b border-amber-500/20 bg-amber-500/10 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400 rounded-t-xl">
          <Wrench className="h-3 w-3" /> Tool Use
          {m.meta?.toolName && (
            <span className="ml-1 rounded bg-amber-500/20 px-1.5 py-0.5 font-mono text-[10px] normal-case tracking-normal text-amber-700 dark:text-amber-300">
              {m.meta.toolName}
            </span>
          )}
        </div>
        <pre className="block w-full min-h-[80px] max-h-60 overflow-y-auto overflow-x-auto px-3 py-2.5 font-mono text-[10.5px] text-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-all">
          {argsText}
        </pre>
      </div>
    );
  }

  if (m.role === "tool_result") {
    return (
      <div
        key={m.id}
        className="animate-scale-in self-start w-full max-w-[92%] rounded-xl border border-border/50 bg-muted/20 shadow-sm"
      >
        <div className="flex items-center gap-1.5 border-b border-border/40 bg-muted/40 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground rounded-t-xl">
          <CornerDownRight className="h-3 w-3" /> Result
          {m.meta?.toolName && (
            <span className="ml-1 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] normal-case tracking-normal">
              {m.meta.toolName}
            </span>
          )}
        </div>
        <pre className="block w-full min-h-[80px] max-h-60 overflow-y-auto overflow-x-auto px-3 py-2.5 font-mono text-[10.5px] leading-relaxed scrollbar-thin whitespace-pre-wrap break-all">
          {m.content}
        </pre>
      </div>
    );
  }

  // Assistant message
  const showHistoricalTools = debug && !hasLiveTools && m.meta?.tools && m.meta.tools.length > 0;

  return (
    <React.Fragment key={m.id}>
      {showHistoricalTools && (m.meta?.tools ?? []).map((t: any, idx: number) => {
        let argsText = String(t.arguments ?? "");
        try {
          if (typeof t.arguments === "object")
            argsText = JSON.stringify(t.arguments, null, 2);
          else if (typeof t.arguments === "string")
            argsText = JSON.stringify(JSON.parse(t.arguments), null, 2);
        } catch {}
        return (
          <React.Fragment key={`hist-tool-${m.id}-${idx}`}>
            <div className="animate-scale-in self-start w-full max-w-[92%] rounded-xl border border-amber-500/30 bg-amber-500/[0.06] shadow-sm mb-2">
              <div className="flex items-center gap-1.5 border-b border-amber-500/20 bg-amber-500/10 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400 rounded-t-xl">
                <Wrench className="h-3 w-3" /> Tool Use
                <span className="ml-1 rounded bg-amber-500/20 px-1.5 py-0.5 font-mono text-[10px] normal-case tracking-normal text-amber-700 dark:text-amber-300">
                  {t.name}
                </span>
              </div>
              <pre className="block w-full min-h-[80px] max-h-60 overflow-y-auto overflow-x-auto px-3 py-2.5 font-mono text-[10.5px] text-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-all">
                {argsText}
              </pre>
            </div>

            <div className="animate-scale-in self-start w-full max-w-[92%] rounded-xl border border-border/50 bg-muted/20 shadow-sm mb-3">
              <div className="flex items-center gap-1.5 border-b border-border/40 bg-muted/40 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground rounded-t-xl">
                <CornerDownRight className="h-3 w-3" /> Result
                <span className="ml-1 rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] normal-case tracking-normal">
                  {t.name}
                </span>
              </div>
              <pre className="block w-full min-h-[80px] max-h-60 overflow-y-auto overflow-x-auto px-3 py-2.5 font-mono text-[10.5px] leading-relaxed scrollbar-thin whitespace-pre-wrap break-all">
                {t.result}
              </pre>
            </div>
          </React.Fragment>
        );
      })}

      <div className="animate-scale-in self-start max-w-[85%] space-y-1">
        <div className="rounded-2xl rounded-bl-sm border border-border/80 bg-card/90 px-4 py-3 text-xs shadow-3d-card select-text leading-relaxed backdrop-blur-md">
          {m.content ? (
            <MarkdownRenderer content={m.content} />
          ) : (
            <span className="flex items-center gap-2 text-muted-foreground">
              <span className="inline-flex gap-0.5">
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:0ms]" />
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:150ms]" />
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:300ms]" />
              </span>
              {debug && <span className="text-[11px]">Thinking…</span>}
            </span>
          )}
        </div>
        {m.meta?.cost_usd != null && (
          <div className="flex items-center gap-3 px-1 text-[10px] text-muted-foreground/60">
            {m.meta.latency_ms != null && (
              <span className="flex items-center gap-0.5">
                <Clock className="h-2.5 w-2.5" />
                {(m.meta.latency_ms / 1000).toFixed(1)}s
              </span>
            )}
            {m.meta.in_tokens != null && (
              <span>{m.meta.in_tokens + (m.meta.out_tokens ?? 0)} tokens</span>
            )}
            {m.meta.cost_usd != null && (
              <span className="flex items-center gap-0.5">
                <DollarSign className="h-2.5 w-2.5" />
                {m.meta.cost_usd.toFixed(5)}
              </span>
            )}
            {m.meta.tools?.length ? (
              <span className="flex items-center gap-0.5">
                <Wrench className="h-2.5 w-2.5" />
                {m.meta.tools.length} tool{m.meta.tools.length > 1 ? "s" : ""}
              </span>
            ) : null}
            {m.meta.model && (
              <span className="font-mono ml-auto">{m.meta.model}</span>
            )}
          </div>
        )}
      </div>
    </React.Fragment>
  );
}
