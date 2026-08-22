"use client";

import * as React from "react";
import DOMPurify from "dompurify";
import { Terminal, Wrench, Play, CheckCircle2, XCircle, ChevronDown, Maximize2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { ToolCallBlock } from "@/lib/chat/projection";

function sanitizeSvg(html: string): string {
  return DOMPurify.sanitize(html, { USE_PROFILES: { svg: true, svgFilters: true } });
}

function SvgPreview({ html }: { html: string }) {
  const clean = sanitizeSvg(html);
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          className="group relative block max-w-full cursor-zoom-in rounded-lg"
          aria-label="Phóng to xem ảnh SVG"
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
}

export function ToolCallCard({ block }: ToolCallCardProps) {
  const isCodeTool = block.name === "run_code" || block.name === "write_file";
  const isSvg =
    block.result != null &&
    (block.result.trim().startsWith("<svg") || block.result.includes("xmlns=\"http://www.w3.org/2000/svg\""));

  let targetPath: string | null = null;
  let codeStr = block.argsText;
  try {
    const parsed = JSON.parse(block.argsText);
    if (parsed.path) targetPath = parsed.path;
    if (parsed.code) codeStr = parsed.code;
    else if (parsed.content && parsed.path) codeStr = parsed.content;
  } catch {
    // Keep argsText
  }

  const isRunning = block.status === "running";
  const isError = block.status === "error";

  return (
    <div className="w-full shrink-0 rounded-xl border border-border bg-card/80 backdrop-blur-md shadow-card overflow-hidden my-1">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border/60 bg-muted/30 px-3 py-1.5 text-[10px] font-semibold text-foreground">
        <div className="flex items-center gap-1.5 min-w-0">
          {isCodeTool ? (
            <Terminal className="h-3.5 w-3.5 shrink-0 text-primary" />
          ) : (
            <Wrench className="h-3.5 w-3.5 shrink-0 text-warning" />
          )}
          <span className="uppercase tracking-wider font-bold shrink-0">
            {isCodeTool ? "Code Execution" : "Tool Call"}
          </span>
          <Badge variant="outline" className="font-mono text-[9px] bg-muted text-foreground border-border shrink-0">
            {block.name}
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
              <Play className="h-2.5 w-2.5 animate-pulse" /> Running
            </span>
          ) : isError ? (
            <span className="flex items-center gap-1 text-destructive">
              <XCircle className="h-3 w-3" /> Failed
            </span>
          ) : (
            <span className="flex items-center gap-1 text-success">
              <CheckCircle2 className="h-3 w-3" /> Done
            </span>
          )}
        </div>
      </div>

      {/* Arguments / Code content */}
      <Collapsible defaultOpen={isRunning || !block.result}>
        <CollapsibleTrigger className="group flex w-full cursor-pointer items-center justify-between bg-muted/10 px-3 py-1 text-[9px] font-mono uppercase tracking-wider text-muted-foreground select-none hover:bg-muted/20">
          <span>Arguments / Payload</span>
          <ChevronDown className="h-3 w-3 transition-transform duration-200 group-data-[state=closed]:-rotate-90" />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <pre className="block w-full min-h-[40px] max-h-60 overflow-y-auto overflow-x-auto p-3 font-mono text-[10.5px] text-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-all bg-muted/40 border-b border-border/40">
            {codeStr || "No arguments"}
          </pre>
        </CollapsibleContent>
      </Collapsible>

      {/* Live progress stream */}
      {block.progress && isRunning ? (
        <div className="border-t border-border/40">
          <div className="flex items-center gap-1.5 bg-muted/20 px-3 py-1 text-[9px] uppercase tracking-wider text-muted-foreground/70">
            <Play className="h-2.5 w-2.5 text-primary animate-pulse" /> Live output
          </div>
          <pre className="block max-h-40 overflow-y-auto overflow-x-auto p-3 font-mono text-[10.5px] text-muted-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-all bg-muted/30">
            {block.progress}
          </pre>
        </div>
      ) : null}

      {/* Result Section */}
      {block.result != null && (
        <div className="border-t border-border/60 bg-muted/10">
          <div className="flex items-center gap-1.5 bg-muted/30 px-3 py-1 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
            <span>Result</span>
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
