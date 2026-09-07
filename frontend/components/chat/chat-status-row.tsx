"use client";

import * as React from "react";
import type { Model } from "@/types";
import { useTranslation } from "@/lib/i18n";

interface ChatStatusRowProps {
  statusPhase: string;
  effectiveModel?: Model;
}

export function ChatStatusRow({ statusPhase, effectiveModel }: ChatStatusRowProps) {
  const { tx } = useTranslation();
  const modelName = effectiveModel?.display_name || effectiveModel?.name;
  const label =
    statusPhase === "approval"
      ? tx("Đang chờ phê duyệt…", "Waiting for approval…")
      : statusPhase.startsWith("tool:")
        ? tx(`Đang chạy ${statusPhase.slice(5)}…`, `Running ${statusPhase.slice(5)}…`)
        : statusPhase === "result"
          ? tx("Đang xử lý kết quả…", "Processing result…")
          : statusPhase === "answering"
            ? tx("Đang soạn phản hồi…", "Writing response…")
            : modelName
              ? tx(`${modelName} đang suy nghĩ…`, `${modelName} is thinking…`)
              : tx("Đang suy nghĩ…", "Thinking…");

  return (
    <div className="flex w-full max-w-[min(525px,85%)] items-center self-start py-1 text-[13px] font-medium leading-6 select-none">
      <span
        className="inline-flex items-center tracking-normal font-sans"
        style={{
          background: "linear-gradient(90deg, hsl(var(--foreground) / 0.5) 0%, hsl(var(--foreground) / 0.5) 40%, hsl(var(--foreground)) 50%, hsl(var(--foreground) / 0.5) 60%, hsl(var(--foreground) / 0.5) 100%)",
          backgroundPosition: "100% 0",
          backgroundSize: "250% 100%",
          WebkitBackgroundClip: "text",
          WebkitTextFillColor: "transparent",
          animation: "dsh-turn-status-shimmer 1.8s linear infinite"
        }}
      >
        {label}
      </span>
      {effectiveModel && !label.includes(modelName ?? "") && (
        <span className="ml-2 font-mono text-xs text-muted-foreground/60">
          ({effectiveModel.display_name || effectiveModel.name})
        </span>
      )}
    </div>
  );
}
