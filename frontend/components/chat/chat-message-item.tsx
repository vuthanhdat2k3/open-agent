"use client";

import * as React from "react";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { Wrench, CornerDownRight, Clock, DollarSign, Terminal, Code, CheckCircle2, XCircle, Play, FileCode, Maximize2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";

function SvgPreview({ html }: { html: string }) {
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
            dangerouslySetInnerHTML={{ __html: html }}
          />
          <span className="absolute inset-0 flex items-center justify-center rounded-lg bg-black/0 opacity-0 transition-all group-hover:bg-black/20 group-hover:opacity-100">
            <Maximize2 className="h-6 w-6 text-white drop-shadow" />
          </span>
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-4xl p-3">
        <div
          className="max-h-[85vh] overflow-auto [&>svg]:w-auto [&>svg]:h-auto [&>svg]:max-w-full [&>svg]:mx-auto"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </DialogContent>
    </Dialog>
  );
}

export type UIMessage = {
  id: string;
  role: string;
  content: string;
  meta?: {
    model?: string;
    in_tokens?: number;
    out_tokens?: number;
    cost_usd?: number;
    latency_ms?: number;
    toolName?: string;
    tools?: any[];
  };
};

interface ChatMessageItemProps {
  message: UIMessage;
  debug: boolean;
  hasLiveTools?: boolean;
}

export function ChatMessageItem({ message: m, debug, hasLiveTools }: ChatMessageItemProps) {
  // Always render tool execution cards for rich user feedback
  if (m.role === "user") {
    return (
      <div
        key={m.id}
        className="animate-scale-in self-end max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-xs text-primary-foreground shadow-3d-card leading-relaxed select-text font-medium"
      >
        {m.content || "…"}
      </div>
    );
  }

  if (m.role === "tool_call") {
    const trimmed = m.content.trim();
    let parsedArgs: any = null;
    let codeStr = m.content;
    let lang = "python";
    try {
      parsedArgs = JSON.parse(m.content);
      if (parsedArgs.code) {
        codeStr = parsedArgs.code;
        lang = parsedArgs.language || "python";
      } else if (parsedArgs.content && parsedArgs.path) {
        codeStr = parsedArgs.content;
        lang = parsedArgs.path.endsWith(".py") ? "python" : parsedArgs.path.endsWith(".svg") ? "svg" : "code";
      } else {
        codeStr = JSON.stringify(parsedArgs, null, 2);
      }
    } catch {}

    const isCodeTool = m.meta?.toolName === "run_code" || m.meta?.toolName === "write_file";

    return (
      <div
        key={m.id}
        className="animate-scale-in self-start w-full max-w-[92%] shrink-0 rounded-xl border border-primary/30 bg-card/80 backdrop-blur-md shadow-3d-card overflow-hidden"
      >
        <div className="flex items-center justify-between border-b border-border/60 bg-muted/30 px-3 py-1.5 text-[10px] font-semibold text-foreground">
          <div className="flex items-center gap-1.5">
            {isCodeTool ? <Terminal className="h-3.5 w-3.5 text-primary" /> : <Wrench className="h-3.5 w-3.5 text-amber-500" />}
            <span className="uppercase tracking-wider font-bold">
              {isCodeTool ? "Code Execution" : "Tool Call"}
            </span>
            <Badge variant="outline" className="ml-1 font-mono text-[9px] bg-primary/10 text-primary border-primary/20">
              {m.meta?.toolName || "tool"}
            </Badge>
            {parsedArgs?.path && (
              <span className="font-mono text-[10px] text-muted-foreground bg-muted/40 px-1.5 py-0.2 rounded border border-border/30">
                {parsedArgs.path}
              </span>
            )}
          </div>
          <span className="flex items-center gap-1 text-[10px] font-mono text-muted-foreground/80">
            <Play className="h-2.5 w-2.5 text-primary animate-pulse" /> Running
          </span>
        </div>
        <pre className="block w-full min-h-[60px] max-h-60 overflow-y-auto overflow-x-auto p-3 font-mono text-[10.5px] text-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-all bg-black/40">
          {codeStr}
        </pre>
      </div>
    );
  }

  if (m.role === "tool_result") {
    const isError = m.content.toLowerCase().includes("error") || m.content.includes("exit code: 1");
    const isSvg = m.content.trim().startsWith("<svg") || m.content.includes("xmlns=\"http://www.w3.org/2000/svg\"");

    return (
      <div
        key={m.id}
        className="animate-scale-in self-start w-full max-w-[92%] shrink-0 rounded-xl border border-border/70 bg-card/90 backdrop-blur-md shadow-3d-card overflow-hidden"
      >
        <div className="flex items-center justify-between border-b border-border/60 bg-muted/30 px-3 py-1.5 text-[10px] font-semibold text-foreground">
          <div className="flex items-center gap-1.5">
            {isError ? (
              <XCircle className="h-3.5 w-3.5 text-destructive" />
            ) : (
              <CheckCircle2 className="h-3.5 w-3.5 text-success" />
            )}
            <span className="uppercase tracking-wider font-bold">
              {isError ? "Execution Failed" : "Execution Output"}
            </span>
            {m.meta?.toolName && (
              <Badge variant="outline" className="ml-1 font-mono text-[9px] bg-muted/40 border-border/40">
                {m.meta.toolName}
              </Badge>
            )}
          </div>
        </div>

        {/* Live SVG vector preview if result contains SVG markup */}
        {isSvg ? (
          <div className="p-4 bg-muted/20 flex flex-col items-center justify-center border-b border-border/40">
            <SvgPreview html={m.content} />
          </div>
        ) : null}

        <pre className="block w-full min-h-[60px] max-h-60 overflow-y-auto overflow-x-auto p-3 font-mono text-[10.5px] text-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-all bg-black/40">
          {m.content}
        </pre>
      </div>
    );
  }

  // Assistant message
  const showHistoricalTools = debug && !hasLiveTools && m.meta?.tools && m.meta.tools.length > 0;

  return (
    <React.Fragment key={m.id}>
      {showHistoricalTools && (m.meta?.tools ?? []).map((t: any, idx: number) => {
        let argsText = String(t.arguments ?? "");
        try {
          if (typeof t.arguments === "object")
            argsText = JSON.stringify(t.arguments, null, 2);
          else if (typeof t.arguments === "string")
            argsText = JSON.stringify(JSON.parse(t.arguments), null, 2);
        } catch {}

        return (
          <React.Fragment key={`hist-tool-${m.id}-${idx}`}>
            <div className="animate-scale-in self-start w-full max-w-[92%] shrink-0 rounded-xl border border-primary/30 bg-card/80 backdrop-blur-md shadow-3d-card overflow-hidden mb-2">
              <div className="flex items-center gap-1.5 border-b border-border/60 bg-muted/30 px-3 py-1.5 text-[10px] font-semibold text-foreground">
                <Terminal className="h-3.5 w-3.5 text-primary" />
                <span className="uppercase tracking-wider font-bold">Executed Tool</span>
                <Badge variant="outline" className="ml-1 font-mono text-[9px] bg-primary/10 text-primary border-primary/20">
                  {t.name}
                </Badge>
              </div>
              <pre className="block w-full min-h-[60px] max-h-96 overflow-y-auto overflow-x-hidden p-3 font-mono text-[10.5px] text-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-words bg-black/40">
                {argsText}
              </pre>
            </div>

            <div className="animate-scale-in self-start w-full max-w-[92%] shrink-0 rounded-xl border border-border/70 bg-card/90 backdrop-blur-md shadow-3d-card overflow-hidden mb-3">
              <div className="flex items-center gap-1.5 border-b border-border/60 bg-muted/30 px-3 py-1.5 text-[10px] font-semibold text-foreground">
                <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                <span className="uppercase tracking-wider font-bold">Execution Output</span>
                <Badge variant="outline" className="ml-1 font-mono text-[9px]">
                  {t.name}
                </Badge>
              </div>
              {String(t.result ?? "").trim().startsWith("<svg") || String(t.result ?? "").includes("xmlns=\"http://www.w3.org/2000/svg\"") ? (
                <div className="p-4 bg-muted/20 flex flex-col items-center justify-center border-b border-border/40">
                  <SvgPreview html={t.result} />
                </div>
              ) : null}
              <pre className="block w-full min-h-[60px] max-h-96 overflow-y-auto overflow-x-hidden p-3 font-mono text-[10.5px] leading-relaxed scrollbar-thin whitespace-pre-wrap break-words bg-black/40">
                {t.result}
              </pre>
            </div>
          </React.Fragment>
        );
      })}

      <div className="animate-scale-in self-start max-w-[85%] space-y-1">
        <div className="rounded-2xl rounded-bl-sm border border-border/80 bg-card/90 px-4 py-3 text-xs shadow-3d-card select-text leading-relaxed backdrop-blur-md">
          {m.content ? (
            <MarkdownRenderer content={m.content} />
          ) : (
            <span className="flex items-center gap-2 text-muted-foreground">
              <span className="inline-flex gap-0.5">
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:0ms]" />
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:150ms]" />
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:300ms]" />
              </span>
              {debug && <span className="text-[11px]">Thinking…</span>}
            </span>
          )}
        </div>
        {m.meta?.cost_usd != null && (
          <div className="flex items-center gap-3 px-1 text-[10px] text-muted-foreground/60">
            {m.meta.latency_ms != null && (
              <span className="flex items-center gap-0.5">
                <Clock className="h-2.5 w-2.5" />
                {(m.meta.latency_ms / 1000).toFixed(1)}s
              </span>
            )}
            {m.meta.in_tokens != null && (
              <span>{m.meta.in_tokens + (m.meta.out_tokens ?? 0)} tokens</span>
            )}
            {m.meta.cost_usd != null && (
              <span className="flex items-center gap-0.5">
                <DollarSign className="h-2.5 w-2.5" />
                {m.meta.cost_usd.toFixed(5)}
              </span>
            )}
            {m.meta.tools?.length ? (
              <span className="flex items-center gap-0.5">
                <Wrench className="h-2.5 w-2.5" />
                {m.meta.tools.length} tool{m.meta.tools.length > 1 ? "s" : ""}
              </span>
            ) : null}
            {m.meta.model && (
              <span className="font-mono ml-auto">{m.meta.model}</span>
            )}
          </div>
        )}
      </div>
    </React.Fragment>
  );
}
