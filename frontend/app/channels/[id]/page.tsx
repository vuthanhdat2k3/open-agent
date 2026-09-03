"use client";

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Bug, MessageSquare, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChannelThread } from "@/components/chat/channel-thread";
import { LoadingSkeleton, ErrorState } from "@/components/shared";
import { useChannelConnections, useChannelMessages } from "@/hooks";
import { useChatStore } from "@/stores";
import { useTranslation } from "@/lib/i18n";

export default function ChannelDetailPage() {
  const { tx } = useTranslation();
  const params = useParams();
  const router = useRouter();
  const connectionId = params.id as string;
  const { debug, toggleDebug } = useChatStore();
  const scrollHostRef = React.useRef<HTMLDivElement>(null);

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

  const {
    data: rawMessages,
    isLoading: isLoadingMessages,
    isError: isErrorMessages,
    refetch: refetchMessages,
    isFetching,
  } = useChannelMessages(connectionId, true);

  // Channel messages from backend are returned newest-first (descending).
  // Sort chronologically (oldest to newest) for chat thread display.
  const messages = React.useMemo(() => {
    if (!rawMessages) return [];
    return [...rawMessages].sort(
      (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    );
  }, [rawMessages]);

  const isLoading = isLoadingConnections || isLoadingMessages;
  const isError = isErrorConnections || isErrorMessages;

  const connection = connections?.find((c) => c.id === connectionId) ?? null;
  const active = connection?.status === "active";
  const errored = connection?.status === "error";

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
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 border-b border-border/70 bg-background px-4 py-2 sm:px-6">
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
            <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
              <MessageSquare className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-foreground">
                {connection.provider === "telegram" ? "Telegram" : "Discord"}
                {connection.bot_username && (
                  <span className="text-muted-foreground font-normal"> @{connection.bot_username}</span>
                )}
              </p>
              <div className="flex items-center gap-2">
                <Badge
                  variant={active ? "success" : errored ? "destructive" : "secondary"}
                  className="mt-0.5 gap-1 text-[10px] py-0 px-1.5 uppercase font-semibold tracking-wider"
                >
                  {connection.status}
                </Badge>
                {messages && messages.length > 0 && (
                  <span className="text-[10px] text-muted-foreground">
                    {messages.length} {tx("tin nhắn", "messages")}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="ml-auto flex items-center gap-1">
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
              <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            </Button>
            <Button
              type="button"
              variant={debug ? "secondary" : "ghost"}
              size="sm"
              className={`h-7 gap-1.5 px-2 text-[10px] transition-colors ${
                debug
                  ? "bg-secondary font-semibold text-primary shadow-sm border border-primary/30"
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
      </div>

      <ChannelThread
        messages={messages ?? []}
        debug={debug}
        scrollHostRef={scrollHostRef}
        onScrollToBottom={scrollToBottom}
      />
    </div>
  );
}
