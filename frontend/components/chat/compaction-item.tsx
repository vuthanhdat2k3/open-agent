"use client";

import * as React from "react";
import { Sparkles, ChevronDown, ChevronRight } from "lucide-react";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { useTranslation } from "@/lib/i18n";
import type { CompactionMessage } from "@/lib/chat/projection";

export interface CompactionItemProps {
  message: CompactionMessage;
  title?: string;
}

/**
 * Collapsed-by-default compaction marker following DeepSeek Harness CompactionItem.
 * Reports where the model stopped seeing previous history (shadowed history remains visible above it).
 */
export const CompactionItem = React.memo(function CompactionItem({
  message,
  title,
}: CompactionItemProps) {
  const { tx } = useTranslation();
  const [expanded, setExpanded] = React.useState(false);

  const hasSummary = Boolean(message.summary && message.summary.trim().length > 0);
  const open = hasSummary && expanded;

  const summaryText =
    message.shadowedItemCount != null && message.shadowedTokenCount != null
      ? tx(
          `Đã nén ${message.shadowedItemCount} tin nhắn (~${message.shadowedTokenCount.toLocaleString()} tokens)`,
          `Compacted ${message.shadowedItemCount} messages (~${message.shadowedTokenCount.toLocaleString()} tokens)`
        )
      : message.shadowedItemCount != null
        ? tx(
            `Đã nén ${message.shadowedItemCount} tin nhắn`,
            `Compacted ${message.shadowedItemCount} messages`
          )
        : tx("Ngữ cảnh đã được tóm tắt", "Context compacted");

  return (
    <div className="w-full my-2.5 px-1 animate-fade-in select-none">
      <div className="flex flex-col rounded-xl border border-border/60 bg-muted/30 hover:bg-muted/50 transition-colors">
        <button
          type="button"
          disabled={!hasSummary}
          aria-expanded={open}
          onClick={() => setExpanded((v) => !v)}
          className="group flex w-full items-center gap-2.5 px-3 py-2 text-left text-xs font-medium text-muted-foreground transition-all disabled:cursor-default"
        >
          {/* Leading Icon with subtle glow */}
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-amber-500/10 text-amber-500 transition-transform group-hover:scale-105">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
          </div>

          {/* Title & Badge */}
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <span className="font-semibold text-foreground/80">
              {title ?? tx("Tóm tắt ngữ cảnh", "Context Compaction")}
            </span>
            <span className="h-1 w-1 rounded-full bg-border" aria-hidden="true" />
            <span className="truncate text-muted-foreground text-[11px]">
              {summaryText}
            </span>
          </div>

          {/* Trailing Disclosure indicator */}
          {hasSummary && (
            <div className="flex items-center gap-1.5 shrink-0 text-muted-foreground/80 group-hover:text-foreground text-[11px]">
              <span>{open ? tx("Thu gọn", "Collapse") : tx("Xem tóm tắt", "View summary")}</span>
              {open ? (
                <ChevronDown className="h-3.5 w-3.5 transition-transform" aria-hidden="true" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
              )}
            </div>
          )}
        </button>

        {/* Collapsible Markdown Summary */}
        {open && message.summary && (
          <div className="border-t border-border/40 px-3.5 py-3 text-xs bg-background/50 rounded-b-xl">
            <div className="text-[10px] font-semibold tracking-wider text-muted-foreground uppercase mb-1.5">
              {tx("Bản tóm tắt ngữ cảnh cho mô hình:", "Model Context Summary:")}
            </div>
            <div className="text-foreground/90 leading-relaxed max-h-96 overflow-y-auto pr-1">
              <MarkdownRenderer content={message.summary} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
});
