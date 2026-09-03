"use client";

import * as React from "react";
import { Copy, Check, Bot, User, ChevronDown, XCircle } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { ToolCallBlock, StatsBlock } from "@/lib/chat/projection";
import { ToolCallCard } from "./blocks/tool-call-card";
import { ToolCallChip } from "./blocks/tool-call-chip";
import { StatsLine } from "./blocks/stats-line";
import type { ChannelMessage } from "@/types";
import { useTranslation } from "@/lib/i18n";

const LazyMarkdownRenderer = React.lazy(() =>
  import("@/components/markdown-renderer").then((m) => ({ default: m.MarkdownRenderer })),
);

interface ChannelMessageItemProps {
  message: ChannelMessage;
  debug: boolean;
}

function ChannelMessageItemBase({ message: m, debug }: ChannelMessageItemProps) {
  const { tx } = useTranslation();
  const [copied, setCopied] = React.useState(false);
  const [debugOpen, setDebugOpen] = React.useState(false);

  const isInbound = m.direction === "inbound";
  const isError = m.message_type === "error" || Boolean(m.metadata?.error);

  const copyText = React.useCallback(async (text: string) => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.left = "-9999px";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Ignore clipboard errors
    }
  }, []);

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  };

  // Convert raw tools from metadata into standard ToolCallBlock[]
  const toolBlocks: ToolCallBlock[] = React.useMemo(() => {
    if (!m.metadata?.tools || !Array.isArray(m.metadata.tools)) return [];
    return m.metadata.tools.map((t: any, idx: number) => {
      const argsText =
        typeof t.arguments === "string"
          ? t.arguments
          : typeof t.args === "string"
          ? t.args
          : JSON.stringify(t.arguments || t.args || {}, null, 2);
      const result =
        typeof t.result === "string"
          ? t.result
          : t.result != null
          ? JSON.stringify(t.result, null, 2)
          : undefined;
      return {
        kind: "tool_call" as const,
        id: `${m.id}-tool-${idx}`,
        callIndex: idx,
        name: t.name || "tool",
        argsText,
        result,
        status: (t.status as any) || (t.error ? "error" : "done"),
      };
    });
  }, [m.id, m.metadata]);

  // Construct StatsBlock if usage/cost/latency or tools exist
  const statsBlock: StatsBlock | null = React.useMemo(() => {
    if (isInbound) return null;
    const meta = m.metadata || {};
    const usage = meta.usage || {};
    const hasUsage = usage.input_tokens != null || usage.output_tokens != null;
    const hasLatency = meta.latency_ms != null;
    const hasCost = meta.cost_usd != null;
    const hasModel = Boolean(meta.model);
    if (!hasUsage && !hasLatency && !hasCost && !hasModel && toolBlocks.length === 0) {
      return null;
    }
    return {
      kind: "stats",
      id: `stats-${m.id}`,
      tokensIn: usage.input_tokens,
      tokensOut: usage.output_tokens,
      costUsd: meta.cost_usd,
      latencyMs: meta.latency_ms,
      model: meta.model,
      toolCount: toolBlocks.length,
    };
  }, [m.id, m.metadata, toolBlocks.length, isInbound]);

  return (
    <div className={`group flex w-full items-start gap-2.5 ${isInbound ? "justify-end" : "self-start"}`}>
      {!isInbound && (
        <Avatar className="mt-0.5 h-7 w-7 shrink-0 border border-border bg-muted">
          <AvatarFallback className="bg-transparent text-foreground">
            <Bot className="h-3.5 w-3.5" aria-hidden="true" />
          </AvatarFallback>
        </Avatar>
      )}

      <div className={`min-w-0 flex-1 space-y-2 ${isInbound ? "flex flex-col items-end" : ""}`}>
        {/* Sender label */}
        <div className={`flex items-center gap-2 text-[11px] text-muted-foreground ${isInbound ? "flex-row-reverse" : ""}`}>
          <span className="font-medium">
            {isInbound ? (m.sender_name || tx("Người dùng", "User")) : (m.sender_name || tx("Bot", "Bot"))}
          </span>
          <span className="text-muted-foreground/60">
            {formatDate(m.created_at)}
          </span>
        </div>

        {/* Tool calls trace: compact chips in Clean mode, expanded cards in Debug mode */}
        {!isInbound && toolBlocks.length > 0 && (
          <div className="w-full max-w-[92%]">
            {!debug ? (
              <div className="flex flex-wrap items-center gap-1.5 my-1">
                {toolBlocks.map((b) => (
                  <ToolCallChip key={b.id} block={b} />
                ))}
              </div>
            ) : (
              <div className="space-y-2 my-1.5">
                {toolBlocks.map((b) => (
                  <ToolCallCard key={b.id} block={b} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Message bubble / Error alert */}
        {isError ? (
          <div
            role="alert"
            className="w-full max-w-[85%] rounded-xl border border-destructive/40 bg-destructive/[0.06] p-3 text-sm text-destructive shadow-card my-1"
          >
            <div className="flex items-center gap-2 font-semibold">
              <XCircle className="h-4 w-4" />
              <span>{tx("Lỗi phản hồi bot", "Bot response error")}</span>
            </div>
            <p className="mt-1.5 whitespace-pre-wrap break-words text-foreground">{m.content}</p>
          </div>
        ) : (
          <div
            className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm shadow-sm ${
              isInbound
                ? "bg-primary text-primary-foreground"
                : "bg-card border border-border text-foreground"
            }`}
          >
            {isInbound ? (
              <p className="whitespace-pre-wrap break-words select-text">{m.content}</p>
            ) : m.content ? (
              <React.Suspense fallback={<span className="whitespace-pre-wrap break-words">{m.content}</span>}>
                <LazyMarkdownRenderer content={m.content} />
              </React.Suspense>
            ) : (
              <span className="text-muted-foreground italic">{tx("(Không có nội dung)", "(No content)")}</span>
            )}
          </div>
        )}

        {/* Execution Stats line (Tokens, latency, cost, model) */}
        {!isInbound && statsBlock && (
          <div className="max-w-[85%]">
            <StatsLine block={statsBlock} debug={debug} />
          </div>
        )}

        {/* Debug metadata panel (Technical audit) */}
        {debug && (
          <Collapsible open={debugOpen} onOpenChange={setDebugOpen} className="w-full max-w-[85%]">
            <CollapsibleTrigger className="group flex w-full cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-[10px] font-medium text-muted-foreground hover:bg-muted/50">
              <ChevronDown className="h-3 w-3 transition-transform duration-200 group-data-[state=closed]:-rotate-90" />
              <span>{tx("Thông tin kỹ thuật (Trace Metadata)", "Trace Metadata & IDs")}</span>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="mt-1 space-y-1.5 rounded-lg border border-border/40 bg-muted/30 p-2.5 text-[10.5px] font-mono">
                <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                  <div>
                    <span className="text-muted-foreground/70">{tx("Sender ID:", "Sender ID:")}</span>{" "}
                    <span className="text-foreground">{m.sender_id || "—"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground/70">{tx("Conversation ID:", "Conversation ID:")}</span>{" "}
                    <span className="text-foreground">{m.conversation_id || "—"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground/70">{tx("External Msg ID:", "External Msg ID:")}</span>{" "}
                    <span className="text-foreground">{m.external_message_id || "—"}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground/70">{tx("Type:", "Type:")}</span>{" "}
                    <span className="text-foreground">{m.message_type || "—"}</span>
                  </div>
                  {m.agent_id && (
                    <div>
                      <span className="text-muted-foreground/70">{tx("Agent ID:", "Agent ID:")}</span>{" "}
                      <span className="text-foreground">{m.agent_id}</span>
                    </div>
                  )}
                </div>
                {m.metadata && Object.keys(m.metadata).length > 0 && (
                  <div className="pt-1.5 border-t border-border/30">
                    <div className="text-muted-foreground/70 mb-1">{tx("Raw Metadata:", "Raw Metadata:")}</div>
                    <pre className="max-h-36 overflow-auto whitespace-pre-wrap break-all rounded bg-background/60 p-1.5 text-[10px] text-foreground border border-border/20">
                      {JSON.stringify(m.metadata, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}

        {/* Copy button */}
        {m.content && (
          <div className={`flex items-center gap-1.5 pt-0.5 ${isInbound ? "flex-row-reverse" : ""}`}>
            <button
              type="button"
              onClick={() => void copyText(m.content)}
              className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none group-hover:opacity-100"
              aria-label={copied ? tx("Đã sao chép", "Copied") : tx("Sao chép", "Copy")}
            >
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              {copied ? tx("Đã sao chép", "Copied") : tx("Sao chép", "Copy")}
            </button>
          </div>
        )}
      </div>

      {isInbound && (
        <Avatar className="mt-0.5 h-7 w-7 shrink-0 border border-border bg-primary/10">
          <AvatarFallback className="bg-transparent text-primary">
            <User className="h-3.5 w-3.5" aria-hidden="true" />
          </AvatarFallback>
        </Avatar>
      )}
    </div>
  );
}

export const ChannelMessageItem = React.memo(ChannelMessageItemBase);
