"use client";

import * as React from "react";
import { CheckCircle2, Loader2, Wrench, XCircle, Bot, Terminal, Globe } from "lucide-react";
import type { ToolCallBlock } from "@/lib/chat/projection";
import { WebArtifactPreviewDialog } from "@/components/workspace/web-artifact-preview-dialog";
import { useTranslation } from "@/lib/i18n";

interface ToolCallChipProps {
  block: ToolCallBlock;
}

export function ToolCallChip({ block }: ToolCallChipProps) {
  const { tx } = useTranslation();
  const [showWebPreview, setShowWebPreview] = React.useState(false);
  const isSubagent = block.name === "call_agent" || block.name.startsWith("delegate_to_") || Boolean(block.subagent);
  const isCode = block.name === "run_code" || block.name === "write_file";
  const isWeb = block.name === "preview_web_artifact";

  let codeStr = "";
  let targetPath = "";
  if (typeof block.arguments === "string") {
    codeStr = block.arguments;
  } else if (block.arguments && typeof block.arguments === "object") {
    const rawCode = (block.arguments as any).code || (block.arguments as any).content || "";
    codeStr = typeof rawCode === "string" ? rawCode : JSON.stringify(rawCode, null, 2);
    targetPath = (block.arguments as any).path || (block.arguments as any).filename || "";
  }

  const isWebFile = Boolean(
    block.name === "preview_web_artifact" ||
    (targetPath && (targetPath.endsWith(".html") || targetPath.endsWith(".htm") || targetPath.endsWith(".svg"))) ||
    (codeStr && (codeStr.includes("<!DOCTYPE html>") || codeStr.includes("<html") || (codeStr.includes("<svg") && codeStr.includes("</svg>"))))
  );

  const statusIcon =
    block.status === "running" ? (
      <Loader2 className="h-3 w-3 animate-spin text-primary" aria-hidden="true" />
    ) : block.status === "error" ? (
      <XCircle className="h-3 w-3 text-destructive" aria-hidden="true" />
    ) : (
      <CheckCircle2 className="h-3 w-3 text-success" aria-hidden="true" />
    );

  const kindIcon = isSubagent ? (
    <Bot className="h-3 w-3 text-indigo-400" aria-hidden="true" />
  ) : isWeb ? (
    <Globe className="h-3 w-3 text-primary" aria-hidden="true" />
  ) : isCode ? (
    <Terminal className="h-3 w-3 text-primary/80" aria-hidden="true" />
  ) : (
    <Wrench className="h-3 w-3 text-muted-foreground/60" aria-hidden="true" />
  );

  const subagentName = block.subagent?.agentName || (block.name.startsWith("delegate_to_") ? block.name.replace(/^delegate_to_/, "").replace(/_/g, " ") : null);
  const displayName = subagentName ? `subagent: ${subagentName}` : block.name;

  return (
    <>
      <span
        className="inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-muted/30 px-2.5 py-0.5 text-[11px] text-muted-foreground select-none"
        title={`${displayName} — ${block.status}`}
      >
        {statusIcon}
        {kindIcon}
        <span className="font-mono text-[10.5px]">{displayName}</span>
        {isWebFile && codeStr && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setShowWebPreview(true);
            }}
            className="ml-1 inline-flex items-center gap-1 rounded bg-primary/15 hover:bg-primary/25 text-primary text-[10px] font-medium px-1.5 py-0.5 transition-colors cursor-pointer"
            title={tx("Mở xem trước trực tiếp", "Open live preview")}
          >
            <Globe className="h-2.5 w-2.5" />
            <span>{tx("Xem trước", "Preview")}</span>
          </button>
        )}
      </span>

      {showWebPreview && (
        <WebArtifactPreviewDialog
          open={showWebPreview}
          onOpenChange={setShowWebPreview}
          title={targetPath || block.name}
          content={codeStr}
          initialTab="preview"
        />
      )}
    </>
  );
}


