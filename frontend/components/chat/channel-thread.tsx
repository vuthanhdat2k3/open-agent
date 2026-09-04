"use client";

import * as React from "react";
import { ArrowDown, MessageSquare } from "lucide-react";
import { ChannelMessageItem } from "./channel-message-item";
import type { ChannelMessage } from "@/types";
import { useTranslation } from "@/lib/i18n";

export interface ChannelThreadProps {
  messages: ChannelMessage[];
  debug: boolean;
  scrollHostRef: React.RefObject<HTMLDivElement | null>;
  onScrollToBottom?: () => void;
  isFiltered?: boolean;
}

function formatDateDivider(dateStr: string, locale: string) {
  try {
    const d = new Date(dateStr);
    const now = new Date();
    const isToday =
      d.getDate() === now.getDate() &&
      d.getMonth() === now.getMonth() &&
      d.getFullYear() === now.getFullYear();
    if (isToday) return locale === "vi" ? "Hôm nay" : "Today";

    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday =
      d.getDate() === yesterday.getDate() &&
      d.getMonth() === yesterday.getMonth() &&
      d.getFullYear() === yesterday.getFullYear();
    if (isYesterday) return locale === "vi" ? "Hôm qua" : "Yesterday";

    return d.toLocaleDateString(locale === "vi" ? "vi-VN" : "en-US", {
      weekday: "short",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

export function ChannelThread({
  messages,
  debug,
  scrollHostRef,
  onScrollToBottom,
  isFiltered = false,
}: ChannelThreadProps) {
  const { tx, locale } = useTranslation();
  const [showScrollBottom, setShowScrollBottom] = React.useState(false);
  const [unreadNewCount, setUnreadNewCount] = React.useState(0);

  const bottomAnchorRef = React.useRef<HTMLDivElement>(null);
  const contentContainerRef = React.useRef<HTMLDivElement>(null);
  const autoScrollRef = React.useRef(true);
  const userScrolledUpRef = React.useRef(false);
  const isProgrammaticScrollRef = React.useRef(false);
  const initialScrolledRef = React.useRef(false);
  const prevCountRef = React.useRef(0);

  // Scroll to bottom helper
  const scrollToBottom = React.useCallback(
    (behavior: ScrollBehavior = "smooth") => {
      const el = scrollHostRef.current;
      if (!el) return;
      userScrolledUpRef.current = false;
      autoScrollRef.current = true;
      setShowScrollBottom(false);
      setUnreadNewCount(0);
      isProgrammaticScrollRef.current = true;

      el.scrollTo({ top: el.scrollHeight, behavior });
      bottomAnchorRef.current?.scrollIntoView({ behavior, block: "end" });

      if (onScrollToBottom) {
        onScrollToBottom();
      }
    },
    [scrollHostRef, onScrollToBottom]
  );

  // Initial sticky scroll to the newest message on mount / first message arrival
  React.useEffect(() => {
    if (!initialScrolledRef.current && messages.length > 0) {
      const el = scrollHostRef.current;
      if (el) {
        // Immediate instant scroll
        el.scrollTop = el.scrollHeight;
        bottomAnchorRef.current?.scrollIntoView({ behavior: "instant", block: "end" });
        initialScrolledRef.current = true;

        // Double micro-tick passes to guarantee bottom position after Markdown & KaTeX render
        const rafId = requestAnimationFrame(() => {
          if (scrollHostRef.current) {
            scrollHostRef.current.scrollTop = scrollHostRef.current.scrollHeight;
          }
        });
        const t1 = setTimeout(() => {
          if (scrollHostRef.current && !userScrolledUpRef.current) {
            scrollHostRef.current.scrollTop = scrollHostRef.current.scrollHeight;
          }
        }, 80);
        const t2 = setTimeout(() => {
          if (scrollHostRef.current && !userScrolledUpRef.current) {
            scrollHostRef.current.scrollTop = scrollHostRef.current.scrollHeight;
          }
        }, 220);

        return () => {
          cancelAnimationFrame(rafId);
          clearTimeout(t1);
          clearTimeout(t2);
        };
      }
    }
  }, [messages.length, scrollHostRef]);

  // Keep pinned to bottom when content container expands (e.g. lazy markdown components),
  // provided the user hasn't explicitly scrolled up.
  React.useEffect(() => {
    const contentEl = contentContainerRef.current;
    if (!contentEl) return;

    const ro = new ResizeObserver(() => {
      const el = scrollHostRef.current;
      if (el && autoScrollRef.current && !userScrolledUpRef.current) {
        el.scrollTop = el.scrollHeight;
      }
    });

    ro.observe(contentEl);
    return () => ro.disconnect();
  }, [scrollHostRef]);

  // Handle message updates: auto-scroll if at bottom, or increment unread count if user scrolled up
  React.useEffect(() => {
    const prev = prevCountRef.current;
    prevCountRef.current = messages.length;

    if (messages.length > prev && prev > 0) {
      if (userScrolledUpRef.current) {
        // User is reviewing history — do not yank down; increment badge
        setUnreadNewCount((c) => c + (messages.length - prev));
        setShowScrollBottom(true);
      } else if (autoScrollRef.current) {
        // User is at bottom — stick with new messages
        const el = scrollHostRef.current;
        if (el) {
          isProgrammaticScrollRef.current = true;
          el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
        }
      }
    }
  }, [messages.length, scrollHostRef]);

  // Scroll event handler
  const onThreadScroll = React.useCallback(() => {
    const el = scrollHostRef.current;
    if (!el) return;

    if (isProgrammaticScrollRef.current) {
      isProgrammaticScrollRef.current = false;
      return;
    }

    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distance > 35) {
      userScrolledUpRef.current = true;
      autoScrollRef.current = false;
      setShowScrollBottom(true);
    } else if (distance <= 15) {
      userScrolledUpRef.current = false;
      autoScrollRef.current = true;
      setShowScrollBottom(false);
      setUnreadNewCount(0);
    }
  }, [scrollHostRef]);

  // Wheel gesture handler (detect immediate scroll up vs down)
  const onThreadWheel = React.useCallback(
    (e: React.WheelEvent<HTMLDivElement>) => {
      if (e.deltaY < 0) {
        // Scrolling up -> lock auto-scroll off immediately
        userScrolledUpRef.current = true;
        autoScrollRef.current = false;
        setShowScrollBottom(true);
      } else if (e.deltaY > 0) {
        // Scrolling down -> if close to bottom, re-engage auto-scroll
        const el = scrollHostRef.current;
        if (el) {
          const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
          if (distance <= 20) {
            userScrolledUpRef.current = false;
            autoScrollRef.current = true;
            setShowScrollBottom(false);
            setUnreadNewCount(0);
          }
        }
      }
    },
    [scrollHostRef]
  );

  // Touch gesture handlers for mobile
  const touchStartYRef = React.useRef<number | null>(null);
  const onThreadTouchStart = React.useCallback((e: React.TouchEvent<HTMLDivElement>) => {
    if (e.touches.length > 0) {
      touchStartYRef.current = e.touches[0].clientY;
    }
  }, []);

  const onThreadTouchMove = React.useCallback(
    (e: React.TouchEvent<HTMLDivElement>) => {
      if (touchStartYRef.current !== null && e.touches.length > 0) {
        const currentY = e.touches[0].clientY;
        if (currentY > touchStartYRef.current + 5) {
          // Swiping down = scrolling up
          userScrolledUpRef.current = true;
          autoScrollRef.current = false;
          setShowScrollBottom(true);
        } else if (currentY < touchStartYRef.current - 5) {
          // Swiping up = scrolling down
          const el = scrollHostRef.current;
          if (el) {
            const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
            if (distance <= 20) {
              userScrolledUpRef.current = false;
              autoScrollRef.current = true;
              setShowScrollBottom(false);
              setUnreadNewCount(0);
            }
          }
        }
      }
    },
    [scrollHostRef]
  );

  if (messages.length === 0) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
        <div className="grid h-14 w-14 place-items-center rounded-2xl border border-border/60 bg-muted/30">
          <MessageSquare className="h-6 w-6 text-muted-foreground/60" />
        </div>
        <div className="space-y-1">
          <p className="text-sm font-medium text-foreground">
            {isFiltered
              ? tx("Không tìm thấy tin nhắn phù hợp", "No matching messages found")
              : tx("Chưa có tin nhắn nào", "No messages yet")}
          </p>
          <p className="max-w-xs text-xs text-muted-foreground">
            {isFiltered
              ? tx("Thử đổi bộ lọc hoặc từ khóa tìm kiếm.", "Try changing the filter or search keywords.")
              : tx(
                  "Tin nhắn từ kênh sẽ xuất hiện ở đây khi có người gửi tin nhắn cho bot.",
                  "Messages from this channel will appear here when someone sends a message to the bot."
                )}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
      <div
        ref={scrollHostRef}
        onScroll={onThreadScroll}
        onWheel={onThreadWheel}
        onTouchStart={onThreadTouchStart}
        onTouchMove={onThreadTouchMove}
        style={{ overflowAnchor: "none" }}
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 sm:p-6"
      >
        <div
          ref={contentContainerRef}
          className="mx-auto flex w-full max-w-[var(--dsh-chat-content-width,736px)] flex-1 flex-col gap-3"
        >
          {messages.map((m, idx) => {
            const prevMsg = idx > 0 ? messages[idx - 1] : null;
            const curDate = new Date(m.created_at).toDateString();
            const prevDate = prevMsg ? new Date(prevMsg.created_at).toDateString() : null;
            const showDateDivider = curDate !== prevDate;

            return (
              <React.Fragment key={m.id}>
                {showDateDivider && (
                  <div className="my-2 flex items-center justify-center gap-3 select-none">
                    <div className="h-px flex-1 bg-border/40" />
                    <span className="rounded-full border border-border/40 bg-muted/60 px-3 py-0.5 text-[10.5px] font-medium text-muted-foreground shadow-xs">
                      {formatDateDivider(m.created_at, locale)}
                    </span>
                    <div className="h-px flex-1 bg-border/40" />
                  </div>
                )}
                <ChannelMessageItem message={m} debug={debug} />
              </React.Fragment>
            );
          })}
          <div ref={bottomAnchorRef} className="h-px w-full pointer-events-none" aria-hidden="true" />
        </div>
      </div>

      {/* Floating Modern Scroll-To-Bottom Button */}
      {showScrollBottom && (
        <div className="pointer-events-none absolute bottom-4 left-0 right-0 z-30 flex justify-center">
          <button
            type="button"
            onClick={() => scrollToBottom("smooth")}
            className="pointer-events-auto flex items-center gap-2 rounded-full border border-border/80 bg-background/95 px-4 py-2 text-xs font-semibold text-foreground shadow-xl backdrop-blur-md transition-all duration-200 hover:scale-105 hover:bg-muted hover:border-primary/40 active:scale-95 animate-in fade-in zoom-in-95"
            aria-label={tx("Cuộn xuống dưới", "Scroll to bottom")}
          >
            <ArrowDown className="h-3.5 w-3.5 text-primary animate-bounce" aria-hidden="true" />
            {unreadNewCount > 0 ? (
              <span className="flex items-center gap-1.5 text-primary">
                <span className="font-bold">
                  {tx(`${unreadNewCount} tin nhắn mới`, `${unreadNewCount} new messages`)}
                </span>
                <span className="flex h-2 w-2 rounded-full bg-primary animate-ping" />
              </span>
            ) : (
              <span>{tx("Cuộn xuống mới nhất", "Scroll to latest")}</span>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
