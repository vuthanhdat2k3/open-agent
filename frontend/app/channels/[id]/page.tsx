"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, MessageSquare, User, Bot } from "lucide-react";
import {
  useChannelConnections,
  useChannelMessages,
} from "@/hooks";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ErrorState, LoadingSkeleton } from "@/components/shared";
import { useTranslation } from "@/lib/i18n";
import Link from "next/link";
import type { ChannelMessage } from "@/types";

function MessageBubble({ message }: { message: ChannelMessage }) {
  const isInbound = message.direction === "inbound";
  return (
    <div className={`flex gap-3 ${isInbound ? "justify-start" : "justify-end"}`}>
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
          isInbound ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
        }`}
      >
        {isInbound ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={`max-w-[70%] rounded-lg px-4 py-2 ${
          isInbound
            ? "bg-muted text-foreground"
            : "bg-primary text-primary-foreground"
        }`}
      >
        <div className="text-xs font-semibold mb-1 opacity-70">
          {isInbound ? message.sender_name || "User" : "Agent"}
        </div>
        <div className="text-sm whitespace-pre-wrap">{message.content}</div>
        <div className="text-[10px] mt-1 opacity-50">
          {new Date(message.created_at).toLocaleString()}
        </div>
      </div>
    </div>
  );
}

export default function ChannelDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { tx } = useTranslation();
  const { data: connections } = useChannelConnections();
  const { data: messages, isLoading, isError, refetch } = useChannelMessages(id, true);

  const connection = connections?.find((c) => c.id === id);

  if (!connection && !isLoading) {
    return (
      <ErrorState
        title={tx("Không tìm thấy kênh", "Channel not found")}
        description={tx("Kênh này không tồn tại.", "This channel does not exist.")}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/channels">
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary">
            <MessageSquare className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-lg font-semibold">
              {connection?.provider === "telegram" ? "Telegram" : "Discord"}
              {connection?.bot_username && (
                <span className="text-muted-foreground font-normal">
                  {" "}@{connection.bot_username}
                </span>
              )}
            </h1>
            <Badge
              variant={connection?.status === "active" ? "success" : "secondary"}
              className="mt-1 text-[10px] py-0 px-1.5"
            >
              {connection?.status}
            </Badge>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-card p-4 min-h-[400px] max-h-[600px] overflow-y-auto">
        {isLoading ? (
          <LoadingSkeleton variant="page" />
        ) : isError ? (
          <ErrorState
            title={tx("Không thể tải tin nhắn", "Unable to load messages")}
            onRetry={() => void refetch()}
          />
        ) : messages && messages.length > 0 ? (
          <div className="space-y-4">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground text-sm">
            {tx("Chưa có tin nhắn nào.", "No messages yet.")}
          </div>
        )}
      </div>
    </div>
  );
}
