"use client";

import * as React from "react";
import { Copy, Check, ShieldCheck, ShieldX, ShieldAlert, Bot, XCircle, RefreshCw, Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import type { ChatMessage, AssistantBlock, ToolCallBlock } from "@/lib/chat/projection";
import { TextBlock } from "./blocks/text-block";
import { ReasoningRow } from "./blocks/reasoning-row";
import { ToolCallCard } from "./blocks/tool-call-card";
import { ToolCallChip } from "./blocks/tool-call-chip";
import { StatsLine } from "./blocks/stats-line";
import { useTranslation } from "@/lib/i18n";

export interface ChatMessageItemProps {
  message: ChatMessage;
  debug: boolean;
  onApprovalDecision?: (messageId: string, decision: "approved" | "rejected") => void;
}

function ChatMessageItemBase({ message: m, debug, onApprovalDecision }: ChatMessageItemProps) {
  const { locale, tx } = useTranslation();
  const [copied, setCopied] = React.useState(false);
  const [isDeciding, setIsDeciding] = React.useState(false);

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

  // 1. User message
  if (m.role === "user") {
    return (
      <div className="group flex w-full justify-end gap-2">
        <div className="mt-1 flex opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
          <button
            type="button"
            onClick={() => void copyText(m.content)}
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={copied ? tx("Đã sao chép tin nhắn", "Message copied") : tx("Sao chép tin nhắn", "Copy message")}
            title={copied ? tx("Đã sao chép", "Copied") : tx("Sao chép tin nhắn", "Copy message")}
          >
            {copied ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
          </button>
        </div>
        <div className="flex max-w-[85%] flex-col items-end gap-1.5">
          {m.attachments?.length ? (
            <div className="flex flex-wrap justify-end gap-1.5">
              {m.attachments.map((a) => (
                <span
                  key={a.id}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-card px-2.5 py-1.5 text-xs text-foreground shadow-sm"
                >
                  <Paperclip className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <span className="max-w-[14rem] truncate">{a.name}</span>
                </span>
              ))}
            </div>
          ) : null}
          <div className="rounded-2xl bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-sm">
            <p className="whitespace-pre-wrap break-words select-text">{m.content}</p>
          </div>
        </div>
      </div>
    );
  }

  // 2. Approval messages: Handled exclusively by the dedicated bottom ApprovalDock while pending; hidden once approved/decided to keep the chat stream clean
  if (m.role === "approval") {
    return null;
  }

  // 3. Error message
  if (m.role === "error") {
    return (
      <div
        tabIndex={0}
        role="alert"
        aria-label={tx("Lỗi mô hình", "Model error")}
        className="animate-scale-in self-start w-full max-w-[92%] rounded-xl border border-destructive/40 bg-destructive/[0.06] p-3 text-sm text-destructive shadow-card my-1"
      >
        <div className="flex items-center gap-2 font-semibold">
          <XCircle className="h-4 w-4" />
          <span>{tx("Lỗi mô hình", "Model error")}</span>
        </div>
        <p className="mt-2 whitespace-pre-wrap break-words text-foreground">{m.content}</p>
      </div>
    );
  }

  // 4. Assistant message (renders blocks in arrival order)
  const fullTextContent = m.blocks
    .filter((b): b is Extract<AssistantBlock, { kind: "text" }> => b.kind === "text")
    .map((b) => b.content)
    .join("\n\n");

  const hasVisibleBlocks = m.blocks.some((b) => {
    if (b.kind === "text") return b.content.trim().length > 0 || b.streaming;
    if (b.kind === "reasoning") return b.content.trim().length > 0 || b.streaming;
    if (b.kind === "tool_call") return true;
    if (b.kind === "stats") return true;
    return false;
  });

  if (!hasVisibleBlocks) return null;

  const rendered: React.ReactNode[] = [];
  let chipGroup: ToolCallBlock[] = [];
  const flushChips = () => {
    if (chipGroup.length > 0) {
      rendered.push(
        <div key={`chips-${rendered.length}`} className="flex flex-wrap items-center gap-1.5 my-1">
          {chipGroup.map((b) => (
            <ToolCallChip key={b.id} block={b} />
          ))}
        </div>,
      );
      chipGroup = [];
    }
  };

  for (const block of m.blocks) {
    if (!debug && block.kind === "tool_call") {
      chipGroup.push(block);
      continue;
    }
    flushChips();
    switch (block.kind) {
      case "reasoning":
        rendered.push(<ReasoningRow key={block.id} content={block.content} streaming={block.streaming} />);
        break;
      case "tool_call":
        rendered.push(<ToolCallCard key={block.id} block={block} />);
        break;
      case "text":
        rendered.push(<TextBlock key={block.id} content={block.content} streaming={block.streaming} />);
        break;
      case "stats":
        rendered.push(<StatsLine key={block.id} block={block} debug={debug} />);
        break;
    }
  }
  flushChips();

  return (
    <div key={m.id} className="group flex w-full max-w-[92%] items-start gap-2.5 self-start">
      <Avatar className="mt-0.5 h-7 w-7 shrink-0 border border-border bg-muted">
        <AvatarFallback className="bg-transparent text-foreground">
          <Bot className="h-3.5 w-3.5" aria-hidden="true" />
        </AvatarFallback>
      </Avatar>

      <div className="min-w-0 flex-1 space-y-2 pt-0.5">
        {rendered}

        {fullTextContent && (
          <div className="flex items-center gap-1.5 pt-0.5">
            <button
              type="button"
              onClick={() => void copyText(fullTextContent)}
              className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none group-hover:opacity-100"
              aria-label={copied ? tx("Đã sao chép tin nhắn", "Message copied") : tx("Sao chép tin nhắn", "Copy message")}
              title={copied ? tx("Đã sao chép", "Copied") : tx("Sao chép tin nhắn", "Copy message")}
            >
              {copied ? <Check className="h-3 w-3" aria-hidden="true" /> : <Copy className="h-3 w-3" aria-hidden="true" />}
              {copied ? tx("Đã sao chép", "Copied") : tx("Sao chép", "Copy")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export const ChatMessageItem = React.memo(ChatMessageItemBase);
