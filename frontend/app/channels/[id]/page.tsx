"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowDownToLine,
  Bug,
  Filter,
  MessageSquare,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ChannelThread } from "@/components/chat/channel-thread";
import { LoadingSkeleton, ErrorState } from "@/components/shared";
import { useChannelConnections, useChannelMessages } from "@/hooks";
import { useChatStore } from "@/stores";
import { useTranslation } from "@/lib/i18n";

type MessageFilter = "all" | "inbound" | "outbound" | "error";

export default function ChannelDetailPage() {
  const { tx } = useTranslation();
  const params = useParams();
  const router = useRouter();
  const connectionId = params.id as string;
  const { debug, toggleDebug } = useChatStore();
  const scrollHostRef = React.useRef<HTMLDivElement>(null);

  // Filter & Search states
  const [filter, setFilter] = React.useState<MessageFilter>("all");
  const [search, setSearch] = React.useState("");
  const [showSearch, setShowSearch] = React.useState(false);

  // Callback to smoothly scroll to bottom of the channel thread
  const scrollToBottom = React.useCallback(() => {
    const el = scrollHostRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [scrollHostRef]);

  const {
    data: connections,
    isLoading: isLoadingConnections,
    isError: isErrorConnections,
    refetch: refetchConnections,
  } = useChannelConnections();

  // Poll every 3 seconds (3000ms) for snappy real-time chat updates
  const {
    data: rawMessages,
    isLoading: isLoadingMessages,
    isError: isErrorMessages,
    refetch: refetchMessages,
    isFetching,
  } = useChannelMessages(connectionId, true, 3000);

  // Channel messages from backend are returned newest-first (descending).
  // Sort chronologically (oldest to newest) for chat thread display.
  const messages = React.useMemo(() => {
    if (!rawMessages) return [];
    return [...rawMessages].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    );
  }, [rawMessages]);

  // Filtered & searched messages
  const filteredMessages = React.useMemo(() => {
    let list = messages;

    if (filter === "inbound") {
      list = list.filter((m) => m.direction === "inbound");
    } else if (filter === "outbound") {
      list = list.filter((m) => m.direction === "outbound");
    } else if (filter === "error") {
      list = list.filter((m) => m.message_type === "error" || Boolean(m.metadata?.error));
    }

    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(
        (m) =>
          m.content.toLowerCase().includes(q) ||
          (m.sender_name && m.sender_name.toLowerCase().includes(q)) ||
          (m.message_type && m.message_type.toLowerCase().includes(q))
      );
    }

    return list;
  }, [messages, filter, search]);

  const isLoading = isLoadingConnections || isLoadingMessages;
  const isError = isErrorConnections || isErrorMessages;

  const connection = connections?.find((c) => c.id === connectionId) ?? null;
  const active = connection?.status === "active";
  const errored = connection?.status === "error";
  const isDiscord = connection?.provider === "discord";

  if (isLoading) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="border-b border-border/70 bg-background px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-muted animate-pulse" />
            <div className="space-y-2">
              <div className="h-4 w-32 rounded bg-muted animate-pulse" />
              <div className="h-3 w-24 rounded bg-muted animate-pulse" />
            </div>
          </div>
        </div>
        <LoadingSkeleton variant="page" />
      </div>
    );
  }

  if (isError || !connection) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center p-8">
        <ErrorState
          title={tx("Không thể tải kênh", "Unable to load channel")}
          description={tx(
            "Không thể tải thông tin kênh tin nhắn.",
            "Channel information could not be loaded."
          )}
          onRetry={() => {
            void refetchConnections();
            void refetchMessages();
          }}
        />
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-background">
      {/* Primary Header */}
      <div className="shrink-0 border-b border-border/70 bg-background/95 px-4 py-2 backdrop-blur-sm sm:px-6">
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-foreground"
            onClick={() => router.push("/channels")}
            aria-label={tx("Quay lại", "Go back")}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>

          <div className="flex min-w-0 items-center gap-2.5">
            <div
              className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg ${
                isDiscord
                  ? "bg-[#5865F2]/10 text-[#5865F2]"
                  : "bg-[#229ED9]/10 text-[#229ED9]"
              }`}
            >
              <MessageSquare className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-foreground flex items-center gap-1.5">
                <span>{isDiscord ? "Discord" : "Telegram"}</span>
                {connection.bot_username && (
                  <span className="font-normal text-muted-foreground">@{connection.bot_username}</span>
                )}
              </p>
              <div className="flex items-center gap-2">
                <Badge
                  variant={active ? "success" : errored ? "destructive" : "secondary"}
                  className="mt-0.5 gap-1 px-1.5 py-0 text-[10px] font-semibold uppercase tracking-wider"
                >
                  {connection.status}
                </Badge>

                {/* Live Sync Pulse */}
                <div
                  className="hidden items-center gap-1 text-[10px] text-muted-foreground sm:flex"
                  title={tx("Tự động đồng bộ tin nhắn (3s)", "Auto syncing messages (3s)")}
                >
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  </span>
                  <span>Live</span>
                </div>

                {messages && messages.length > 0 && (
                  <span className="text-[10px] text-muted-foreground">
                    {messages.length} {tx("tin nhắn", "messages")}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-1">
            {/* Quick jump to bottom button in header */}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 gap-1 px-2 text-[11px] text-muted-foreground hover:text-foreground"
              onClick={scrollToBottom}
              title={tx("Cuộn xuống tin nhắn mới nhất", "Scroll to latest message")}
              aria-label={tx("Cuộn xuống mới nhất", "Scroll to latest")}
            >
              <ArrowDownToLine className="h-3.5 w-3.5" />
              <span className="hidden md:inline">{tx("Mới nhất", "Latest")}</span>
            </Button>

            {/* Toggle Search Bar */}
            <Button
              type="button"
              variant={showSearch || search ? "secondary" : "ghost"}
              size="sm"
              className="h-7 gap-1 px-2 text-[11px] text-muted-foreground hover:text-foreground"
              onClick={() => setShowSearch((s) => !s)}
              title={tx("Tìm kiếm tin nhắn", "Search messages")}
            >
              <Search className="h-3.5 w-3.5" />
              <span className="hidden md:inline">{tx("Tìm kiếm", "Search")}</span>
            </Button>

            {/* Refresh Button */}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 px-2 text-[10px] text-muted-foreground hover:text-foreground"
              onClick={() => void refetchMessages()}
              disabled={isFetching}
              aria-label={tx("Làm mới", "Refresh")}
              title={tx("Làm mới", "Refresh")}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin text-primary" : ""}`} />
            </Button>

            {/* Debug Mode Button */}
            <Button
              type="button"
              variant={debug ? "secondary" : "ghost"}
              size="sm"
              className={`h-7 gap-1.5 px-2 text-[10px] transition-colors ${
                debug
                  ? "border border-primary/30 bg-secondary font-semibold text-primary shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={toggleDebug}
              aria-pressed={debug}
              title={
                debug
                  ? tx("Chế độ Debug đang BẬT", "Debug mode is ON")
                  : tx("Chế độ Debug đang TẮT", "Debug mode is OFF")
              }
            >
              <Bug className={`h-3.5 w-3.5 ${debug ? "text-primary" : ""}`} />
              <span>{tx("Debug", "Debug")}</span>
              {debug && <span className="h-1.5 w-1.5 rounded-full bg-primary" />}
            </Button>
          </div>
        </div>

        {/* Filter & Search Toolbar */}
        {(showSearch || search || filter !== "all") && (
          <div className="mt-2.5 flex flex-wrap items-center gap-2 pt-2 border-t border-border/50 animate-in fade-in slide-in-from-top-1">
            {/* Search input */}
            <div className="relative flex-1 min-w-[200px]">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={tx("Tìm nội dung hoặc người gửi...", "Search content or sender...")}
                className="h-7 pl-8 pr-7 text-xs bg-muted/30"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch("")}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label={tx("Xóa tìm kiếm", "Clear search")}
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>

            {/* Filter chips */}
            <div className="flex items-center gap-1">
              <Filter className="h-3 w-3 text-muted-foreground mr-1" />
              {(
                [
                  { id: "all", label: tx("Tất cả", "All") },
                  { id: "inbound", label: tx("Người dùng", "User") },
                  { id: "outbound", label: tx("Bot", "Bot") },
                  { id: "error", label: tx("Lỗi", "Errors") },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setFilter(tab.id)}
                  className={`rounded-full px-2.5 py-0.5 text-[10.5px] font-medium transition-colors ${
                    filter === tab.id
                      ? "bg-primary text-primary-foreground shadow-xs"
                      : "bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
                >
                  {tab.label}
                </button>
              ))}

              {(search || filter !== "all") && (
                <span className="ml-2 text-[10px] text-muted-foreground">
                  {filteredMessages.length}/{messages.length} {tx("tin", "msgs")}
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Main Channel Message Thread */}
      <ChannelThread
        messages={filteredMessages}
        debug={debug}
        scrollHostRef={scrollHostRef}
        onScrollToBottom={scrollToBottom}
        isFiltered={search.trim().length > 0 || filter !== "all"}
      />
    </div>
  );
}
