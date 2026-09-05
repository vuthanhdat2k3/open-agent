"use client";

import * as React from "react";
import { BellRing, CheckCheck } from "lucide-react";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "@/hooks";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTranslation } from "@/lib/i18n";

function relativeTime(iso: string, locale: string) {
  const ms = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(ms / 60000);
  if (minutes < 1) return locale === "vi" ? "Vừa xong" : "Just now";
  if (minutes < 60) return locale === "vi" ? `${minutes} phút trước` : `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return locale === "vi" ? `${hours} giờ trước` : `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return locale === "vi" ? `${days} ngày trước` : `${days}d ago`;
}

export function NotificationBell() {
  const notifications = useNotifications(true);
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();
  const { t, locale, tx } = useTranslation();

  const items = notifications.data ?? [];
  const unread = items.filter((n) => !n.read_at).length;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative h-10 w-10 rounded-xl"
          aria-label={tx(`${unread} thông báo chưa đọc`, `${unread} unread notifications`)}
        >
          <BellRing className="h-4 w-4" aria-hidden="true" />
          {unread > 0 && (
            <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold text-primary-foreground">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[min(24rem,calc(100vw-2rem))] p-2">
        <DropdownMenuLabel className="flex items-center justify-between px-3 py-2">
          <span>{t("pages.notifications.title", "Notifications")}</span>
          {unread > 0 && (
            <button
              type="button"
              className="flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
              onClick={() => markAllRead.mutate()}
            >
              <CheckCheck className="h-3 w-3" aria-hidden="true" />
              {tx("Đánh dấu đã đọc", "Mark all read")}
            </button>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {items.slice(0, 8).map((item) => (
          <DropdownMenuItem
            key={item.id}
            className="block cursor-pointer rounded-xl p-3"
            onSelect={() => {
              if (!item.read_at) markRead.mutate(item.id);
              if (item.link_url) window.location.href = item.link_url;
            }}
          >
            <div className="flex items-center justify-between gap-2">
              <span className={`truncate text-sm font-semibold ${item.read_at ? "text-muted-foreground" : "text-foreground"}`}>
                {item.title}
              </span>
              {!item.read_at && <span className="h-2 w-2 shrink-0 rounded-full bg-primary" aria-hidden="true" />}
            </div>
            {item.body && (
              <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">{item.body}</div>
            )}
            <div className="mt-1 text-[11px] text-muted-foreground">{relativeTime(item.created_at, locale)}</div>
          </DropdownMenuItem>
        ))}
        {!notifications.isLoading && items.length === 0 && (
          <div className="px-3 py-6 text-center text-sm text-muted-foreground">
            {tx("Chưa có thông báo nào", "No notifications yet")}
          </div>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
