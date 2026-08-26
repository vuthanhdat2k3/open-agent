"use client";

import * as React from "react";
import DOMPurify from "dompurify";
import {
  Terminal,
  Wrench,
  Play,
  CheckCircle2,
  XCircle,
  ChevronDown,
  Maximize2,
  Bot,
  Brain,
  Sparkles,
  Loader2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { ToolCallBlock } from "@/lib/chat/projection";
import { useTranslation } from "@/lib/i18n";

const LazyMarkdownRenderer = React.lazy(() =>
  import("@/components/markdown-renderer").then((m) => ({ default: m.MarkdownRenderer })),
);

function sanitizeSvg(html: string): string {
  return DOMPurify.sanitize(html, { USE_PROFILES: { svg: true, svgFilters: true } });
}

function SvgPreview({ html }: { html: string }) {
    const { t, locale } = useTranslation();
  const clean = sanitizeSvg(html);
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          className="group relative block max-w-full cursor-zoom-in rounded-lg"
          aria-label={t("pages.chat.enlargeSvg", "Phóng to xem ảnh SVG")}
        >
          <div
            className="max-w-full max-h-[360px] overflow-auto rounded-lg border border-border/40 bg-card p-2 shadow-sm [&>svg]:w-auto [&>svg]:h-auto [&>svg]:max-w-full [&>svg]:max-h-[340px]"
            dangerouslySetInnerHTML={{ __html: clean }}
          />
          <span className="absolute inset-0 flex items-center justify-center rounded-lg bg-black/0 opacity-0 transition-[background-color,opacity] group-hover:bg-black/20 group-hover:opacity-100">
            <Maximize2 className="h-6 w-6 text-white drop-shadow" />
          </span>
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-4xl p-3">
        <div
          className="max-h-[85vh] overflow-auto [&>svg]:w-auto [&>svg]:h-auto [&>svg]:max-w-full [&>svg]:mx-auto"
          dangerouslySetInnerHTML={{ __html: clean }}
        />
      </DialogContent>
    </Dialog>
  );
}

interface ToolCallCardProps {
  block: ToolCallBlock;
  compact?: boolean;
}

export function ToolCallCard({ block, compact = false }: ToolCallCardProps) {
    const { locale } = useTranslation();
  const isCodeTool = block.name === "run_code" || block.name === "write_file";
  const isSubagent = block.name === "call_agent" || Boolean(block.subagent);
  const isSvg =
    block.result != null &&
    (block.result.trim().startsWith("<svg") || block.result.includes("xmlns=\"http://www.w3.org/2000/svg\""));

  let targetPath: string | null = null;
  let subagentInstruction: string | null = null;
  let codeStr = block.argsText;
  try {
    const parsed = JSON.parse(block.argsText);
    if (parsed.path) targetPath = parsed.path;
    if (parsed.instruction) subagentInstruction = parsed.instruction;
    if (parsed.code) codeStr = parsed.code;
    else if (parsed.content && parsed.path) codeStr = parsed.content;
  } catch {
    // Keep argsText
  }

  const isRunning = block.status === "running";
  const isError = block.status === "error";
  const subagent = block.subagent;

  return (
    <div className={`w-full shrink-0 rounded-xl border border-border bg-card/80 backdrop-blur-md shadow-card overflow-hidden my-1.5 transition-all ${compact ? "border-primary/30" : ""}`}>
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/60 bg-muted/30 px-3 py-1.5 text-[10px] font-semibold text-foreground">
        <div className="flex items-center gap-1.5 min-w-0">
          {isSubagent ? (
            <Bot className="h-3.5 w-3.5 shrink-0 text-indigo-400 animate-pulse" />
          ) : isCodeTool ? (
            <Terminal className="h-3.5 w-3.5 shrink-0 text-primary" />
          ) : (
            <Wrench className="h-3.5 w-3.5 shrink-0 text-warning" />
          )}
          <span className="uppercase tracking-wider font-bold shrink-0">
            {isSubagent ? "Subagent Call" : isCodeTool ? "Code Execution" : "Tool Call"}
          </span>
          <Badge variant="outline" className="font-mono text-[9px] bg-muted text-foreground border-border shrink-0">
            {subagent?.agentName ? `${subagent.agentName}` : block.name}
          </Badge>
          {targetPath && (
            <span className="font-mono text-[10px] text-muted-foreground bg-muted/40 px-1.5 py-0.2 rounded border border-border/30 truncate max-w-[200px]">
              {targetPath}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1 text-[10px] font-mono shrink-0 ml-2">
          {isRunning ? (
            <span className="flex items-center gap-1 text-primary">
              <Loader2 className="h-3 w-3 animate-spin" /> {locale === "vi" ? "Running" : "Running"}</span>
          ) : isError ? (
            <span className="flex items-center gap-1 text-destructive">
              <XCircle className="h-3 w-3" /> {locale === "vi" ? "Thất bại" : "Failed"}</span>
          ) : (
            <span className="flex items-center gap-1 text-success">
              <CheckCircle2 className="h-3 w-3" /> {locale === "vi" ? "Done" : "Done"}</span>
          )}
        </div>
      </div>

      {/* Subagent Specialized View */}
      {isSubagent && (
        <div className="border-b border-border/40 bg-indigo-950/10 p-3 space-y-2.5">
          {subagentInstruction && (
            <div className="text-[11px] text-muted-foreground">
              <span className="font-semibold text-foreground/80">{locale === "vi" ? "Goal:" : "Goal:"}</span>
              {subagentInstruction}
            </div>
          )}

          {/* Subagent Thinking */}
          {subagent?.thinking && (
            <Collapsible defaultOpen={isRunning}>
              <CollapsibleTrigger className="group flex w-full cursor-pointer items-center justify-between rounded bg-muted/30 px-2.5 py-1 text-[10px] font-medium text-indigo-300 hover:bg-muted/50">
                <span className="flex items-center gap-1.5">
                  <Brain className="h-3 w-3 text-indigo-400" />
                  {locale === "vi" ? "Subagent Thinking" : "Subagent Thinking"}{isRunning && <span className="inline-block h-1.5 w-1.5 rounded-full bg-indigo-400 animate-ping" />}
                </span>
                <ChevronDown className="h-3 w-3 transition-transform duration-200 group-data-[state=closed]:-rotate-90" />
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="mt-1 rounded bg-muted/20 p-2.5 text-[11px] text-muted-foreground font-mono leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto border border-border/30">
                  {subagent.thinking}
                  {isRunning && <span className="inline-block h-3 w-1.5 bg-indigo-400 animate-pulse ml-0.5" />}
                </div>
              </CollapsibleContent>
            </Collapsible>
          )}

          {/* Subagent Sub-tools */}
          {subagent?.tools && subagent.tools.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 pt-1">
              <span className="text-[9px] uppercase tracking-wider text-muted-foreground font-semibold">{locale === "vi" ? "Sub-tools:" : "Sub-tools:"}</span>
              {subagent.tools.map((t, i) => (
                <Badge key={i} variant="outline" className="text-[10px] gap-1 font-mono py-0 px-2 bg-muted/40 border-border/60">
                  {t.status === "running" ? (
                    <Loader2 className="h-2.5 w-2.5 animate-spin text-primary" />
                  ) : (
                    <CheckCircle2 className="h-2.5 w-2.5 text-success" />
                  )}
                  {t.name}
                </Badge>
              ))}
            </div>
          )}

          {/* Subagent Response Live Preview */}
          {subagent?.response && (
            <div className="space-y-1 pt-1">
              <div className="flex items-center gap-1.5 text-[10px] font-semibold text-foreground/80">
                <Sparkles className="h-3 w-3 text-indigo-400" />
                {locale === "vi" ? "Subagent Response Stream" : "Subagent Response Stream"}</div>
              <div className="rounded-lg bg-card/60 border border-border/40 p-2.5 text-[12px] text-foreground leading-relaxed max-h-60 overflow-y-auto">
                <React.Suspense fallback={<div className="whitespace-pre-wrap">{subagent.response}</div>}>
                  <LazyMarkdownRenderer content={subagent.response} />
                </React.Suspense>
                {isRunning && <span className="inline-block h-3.5 w-1.5 bg-primary animate-pulse ml-0.5 align-middle" />}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Arguments / Code content */}
      <Collapsible defaultOpen={!isSubagent && (isRunning || !block.result)}>
        <CollapsibleTrigger className="group flex w-full cursor-pointer items-center justify-between bg-muted/10 px-3 py-1 text-[9px] font-mono uppercase tracking-wider text-muted-foreground select-none hover:bg-muted/20">
          <span>{locale === "vi" ? "Arguments / Payload" : "Arguments / Payload"}</span>
          <ChevronDown className="h-3 w-3 transition-transform duration-200 group-data-[state=closed]:-rotate-90" />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <pre className="block w-full min-h-[30px] max-h-60 overflow-y-auto overflow-x-auto p-3 font-mono text-[10.5px] text-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-all bg-muted/40 border-b border-border/40">
            {codeStr || "No arguments"}
          </pre>
        </CollapsibleContent>
      </Collapsible>

      {/* Live progress stream for all tools */}
      {block.progress && isRunning ? (
        <div className="border-t border-border/40">
          <div className="flex items-center gap-1.5 bg-muted/20 px-3 py-1 text-[9px] uppercase tracking-wider text-muted-foreground/70">
            <Play className="h-2.5 w-2.5 text-primary animate-pulse" /> {locale === "vi" ? "Live output & progress" : "Live output & progress"}</div>
          <pre className="block max-h-48 overflow-y-auto overflow-x-auto p-3 font-mono text-[10.5px] text-muted-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-all bg-muted/30">
            {block.progress}
          </pre>
        </div>
      ) : null}

      {/* Result Section */}
      {block.result != null && (
        <div className="border-t border-border/60 bg-muted/10">
          <div className="flex items-center gap-1.5 bg-muted/30 px-3 py-1 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
            <span>{locale === "vi" ? "Result" : "Result"}</span>
          </div>

          {isSvg ? (
            <div className="p-3 bg-muted/20 flex flex-col items-center justify-center border-b border-border/40">
              <SvgPreview html={block.result} />
            </div>
          ) : null}

          <pre className="block w-full min-h-[40px] max-h-60 overflow-y-auto overflow-x-auto p-3 font-mono text-[10.5px] text-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-all bg-muted/20">
            {block.result}
          </pre>
        </div>
      )}
    </div>
  );
}

