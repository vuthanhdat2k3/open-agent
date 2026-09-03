"use client";

import * as React from "react";
import { ArrowDown, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChannelMessageItem } from "./channel-message-item";
import type { ChannelMessage } from "@/types";
import { useTranslation } from "@/lib/i18n";

interface ChannelThreadProps {
  messages: ChannelMessage[];
  debug: boolean;
  scrollHostRef: React.RefObject<HTMLDivElement | null>;
  onScrollToBottom?: () => void;
}

export function ChannelThread({
  messages,
  debug,
  scrollHostRef,
  onScrollToBottom,
}: ChannelThreadProps) {
  const { tx } = useTranslation();
  const [showScrollBottom, setShowScrollBottom] = React.useState(false);
  const autoScrollRef = React.useRef(true);
  const isProgrammaticScrollRef = React.useRef(false);

  const onThreadScroll = React.useCallback(() => {
    const el = scrollHostRef.current;
    if (!el) return;
    if (isProgrammaticScrollRef.current) {
      isProgrammaticScrollRef.current = false;
      return;
    }
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distance > 25) {
      autoScrollRef.current = false;
      setShowScrollBottom(true);
    } else if (distance <= 10) {
      autoScrollRef.current = true;
      setShowScrollBottom(false);
    }
  }, [scrollHostRef]);

  React.useEffect(() => {
    const el = scrollHostRef.current;
    if (!el || !autoScrollRef.current) return;
    isProgrammaticScrollRef.current = true;
    el.scrollTo({ top: el.scrollHeight, behavior: "instant" });
  }, [messages, scrollHostRef]);

  const scrollToBottom = React.useCallback((behavior: ScrollBehavior = "smooth") => {
    const el = scrollHostRef.current;
    if (!el) return;
    autoScrollRef.current = true;
    setShowScrollBottom(false);
    isProgrammaticScrollRef.current = true;
    el.scrollTo({ top: el.scrollHeight, behavior });
  }, [scrollHostRef]);

  if (messages.length === 0) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
        <div className="grid h-14 w-14 place-items-center rounded-2xl border border-border/60 bg-muted/30">
          <MessageSquare className="h-6 w-6 text-muted-foreground/60" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium text-foreground">
            {tx("Chưa có tin nhắn nào", "No messages yet")}
          </p>
          <p className="text-xs text-muted-foreground max-w-xs">
            {tx(
              "Tin nhắn từ kênh sẽ xuất hiện ở đây khi có người gửi tin nhắn cho bot.",
              "Messages from this channel will appear here when someone sends a message to the bot."
            )}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div
        ref={scrollHostRef}
        onScroll={onThreadScroll}
        style={{ overflowAnchor: "none" }}
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 sm:p-6"
      >
        <div className="mx-auto flex w-full max-w-[var(--dsh-chat-content-width,736px)] flex-1 flex-col gap-4">
          {messages.map((m) => (
            <ChannelMessageItem key={m.id} message={m} debug={debug} />
          ))}
        </div>
      </div>

      {showScrollBottom && onScrollToBottom && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => scrollToBottom("smooth")}
          className="absolute bottom-3 left-1/2 -translate-x-1/2 z-20 h-7 gap-1.5 rounded-full border border-border/80 bg-background/95 px-3 text-[11px] font-medium text-foreground shadow-md backdrop-blur transition-all hover:bg-muted active:scale-95"
          aria-label={tx("Cuộn xuống dưới", "Scroll to bottom")}
        >
          <ArrowDown className="h-3 w-3 text-primary animate-bounce" aria-hidden="true" />
          <span>{tx("Cuộn xuống dưới", "Scroll to bottom")}</span>
        </Button>
      )}
    </div>
  );
}
