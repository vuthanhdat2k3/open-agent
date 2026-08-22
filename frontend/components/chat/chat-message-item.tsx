"use client";

import * as React from "react";
import { Copy, Check, ShieldCheck, ShieldX, ShieldAlert, Bot, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import type { ChatMessage, AssistantBlock } from "@/lib/chat/projection";
import { TextBlock } from "./blocks/text-block";
import { ReasoningRow } from "./blocks/reasoning-row";
import { ToolCallCard } from "./blocks/tool-call-card";
import { StatsLine } from "./blocks/stats-line";

export interface ChatMessageItemProps {
  message: ChatMessage;
  debug: boolean;
  onApprovalDecision?: (messageId: string, decision: "approved" | "rejected") => void;
}

function ChatMessageItemBase({ message: m, debug, onApprovalDecision }: ChatMessageItemProps) {
  const [copied, setCopied] = React.useState(false);

  const copyText = React.useCallback(async (text: string) => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        const didCopy = document.execCommand("copy");
        textarea.remove();
        if (!didCopy) throw new Error("copy command failed");
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      // Ignore clipboard failure
    }
  }, []);

  // 1. User message (DeepSeek Harness User_Bubble: r22, max-w-[525px], 16px/24px font)
  if (m.role === "user") {
    return (
      <div key={m.id} className="group flex w-full flex-col items-end gap-1.5 self-end">
        <div className="flex max-w-[min(525px,85%)] flex-col items-end gap-1">
          <div
            className="cursor-text select-text whitespace-pre-wrap break-words rounded-[22px] px-4 py-2.5 text-[15px] leading-6 text-foreground shadow-sm"
            style={{ backgroundColor: "var(--dsh-specific-bubble)" }}
          >
            {m.content || "…"}
          </div>
          <button
            type="button"
            onClick={() => void copyText(m.content)}
            className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none group-hover:opacity-100"
            aria-label={copied ? "User message copied" : "Copy user message"}
            title={copied ? "Copied" : "Copy message"}
          >
            {copied ? <Check className="h-3 w-3" aria-hidden="true" /> : <Copy className="h-3 w-3" aria-hidden="true" />}
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
    );
  }

  // 2. Approval message
  if (m.role === "approval") {
    const status = m.status;
    const args =
      typeof m.argsSnapshot === "string"
        ? m.argsSnapshot
        : JSON.stringify(m.argsSnapshot ?? {}, null, 2);

    return (
      <div
        key={m.id}
        className="animate-scale-in self-start w-full max-w-[92%] rounded-xl border border-warning/40 bg-warning/[0.06] p-3 shadow-card my-1"
      >
        <div className="flex items-center gap-2 text-xs font-semibold">
          {status === "approved" ? (
            <ShieldCheck className="h-4 w-4 text-success" />
          ) : status === "rejected" ? (
            <ShieldX className="h-4 w-4 text-destructive" />
          ) : (
            <ShieldAlert className="h-4 w-4 text-warning" />
          )}
          <span>
            {status === "pending"
              ? "Approval required"
              : status === "approved"
              ? "Approved"
              : "Rejected"}
          </span>
          {m.toolName && (
            <Badge variant="outline" className="font-mono text-[9px]">
              {m.toolName}
            </Badge>
          )}
        </div>
        <pre className="mt-2 max-h-48 overflow-auto rounded-lg border border-border/50 bg-black/30 p-2 font-mono text-[10px] leading-relaxed whitespace-pre-wrap break-all">
          {args}
        </pre>
        {status === "pending" && onApprovalDecision ? (
          <div className="mt-3 flex gap-2">
            <Button
              size="sm"
              className="h-8 gap-1.5 text-xs"
              onClick={() => onApprovalDecision(m.id, "approved")}
            >
              <ShieldCheck className="h-3.5 w-3.5" /> Approve
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-8 gap-1.5 text-xs"
              onClick={() => onApprovalDecision(m.id, "rejected")}
            >
              <ShieldX className="h-3.5 w-3.5" /> Reject
            </Button>
          </div>
        ) : null}
      </div>
    );
  }

  // 3. Error message
  if (m.role === "error") {
    return (
      <div
        key={m.id}
        role="alert"
        className="animate-scale-in self-start w-full max-w-[92%] rounded-xl border border-destructive/40 bg-destructive/[0.06] p-3 text-sm text-destructive shadow-card my-1"
      >
        <div className="flex items-center gap-2 font-semibold">
          <XCircle className="h-4 w-4" />
          <span>Model error</span>
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

  return (
    <div key={m.id} className="group flex w-full max-w-[92%] items-start gap-2.5 self-start">
      <Avatar className="mt-0.5 h-7 w-7 shrink-0 border border-border bg-muted">
        <AvatarFallback className="bg-transparent text-foreground">
          <Bot className="h-3.5 w-3.5" aria-hidden="true" />
        </AvatarFallback>
      </Avatar>

      <div className="min-w-0 flex-1 space-y-2 pt-0.5">
        {m.blocks.map((block) => {
          switch (block.kind) {
            case "reasoning":
              return <ReasoningRow key={block.id} content={block.content} streaming={block.streaming} />;
            case "tool_call":
              return <ToolCallCard key={block.id} block={block} />;
            case "text":
              return <TextBlock key={block.id} content={block.content} streaming={block.streaming} />;
            case "stats":
              return <StatsLine key={block.id} block={block} />;
            default:
              return null;
          }
        })}

        {fullTextContent && (
          <div className="flex items-center gap-1.5 pt-0.5">
            <button
              type="button"
              onClick={() => void copyText(fullTextContent)}
              className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none group-hover:opacity-100"
              aria-label={copied ? "Message copied" : "Copy message"}
              title={copied ? "Copied" : "Copy message"}
            >
              {copied ? <Check className="h-3 w-3" aria-hidden="true" /> : <Copy className="h-3 w-3" aria-hidden="true" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export const ChatMessageItem = React.memo(ChatMessageItemBase);
