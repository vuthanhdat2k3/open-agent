"use client";

import { RefreshCw, WifiOff } from "lucide-react";
import { useTranslation } from "@/lib/i18n";

export type ConnectionState = "connected" | "reconnecting" | "disconnected";

interface ChatConnectionBannerProps {
  state: ConnectionState;
}

// Small non-blocking banner shown above the composer when the SSE follow
// stream is retrying or has given up. Does not cover the thread or input —
// only a slim strip so the user can keep reading/typing.
export function ChatConnectionBanner({ state }: ChatConnectionBannerProps) {
  const { tx } = useTranslation();
  if (state === "connected") return null;

  const isReconnecting = state === "reconnecting";

  return (
    <div
      role="status"
      aria-live="polite"
      className={`mb-2 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${
        isReconnecting
          ? "border-warning/40 bg-warning/10 text-warning-foreground"
          : "border-destructive/40 bg-destructive/10 text-destructive"
      }`}
    >
      {isReconnecting ? (
        <RefreshCw className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden="true" />
      ) : (
        <WifiOff className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      )}
      <span>
        {isReconnecting
          ? tx("Đang kết nối lại tới phiên chạy trực tiếp...", "Reconnecting to the live run…")
          : tx("Mất kết nối. Phiên chạy sẽ tiếp tục khi kết nối được khôi phục.", "Connection lost. The run will resume once the connection is back.")}
      </span>
    </div>
  );
}
