"use client";

import * as React from "react";
import DOMPurify from "dompurify";

// react-markdown pulls in highlight.js and KaTeX, which together dominate the
// Chat entry bundle. Only assistant messages need them, so the stack is split
// out and loaded on demand; the Suspense fallback below keeps the message text
// readable while that chunk arrives.
const LazyMarkdownRenderer = React.lazy(() =>
  import("@/components/markdown-renderer").then((m) => ({ default: m.MarkdownRenderer })),
);
import { Wrench, Clock, DollarSign, Terminal, Copy, Check, CheckCircle2, XCircle, Play, Maximize2, ChevronDown, ShieldAlert, ShieldCheck, ShieldX, Bot } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

// html here can be raw SVG returned by an LLM/tool call — treat it as
// untrusted and sanitize before it reaches the DOM (SVG supports
// <script>/onload/onerror just like HTML).
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
    reasoning?: string;
    progress?: string;
    approvalId?: string;
    approvalTool?: string;
    approvalArgs?: unknown;
    approvalStatus?: "pending" | "approved" | "rejected";
  };
};

interface ChatMessageItemProps {
  message: UIMessage;
  debug: boolean;
  hasLiveTools?: boolean;
  onApprovalDecision?: (messageId: string, decision: "approved" | "rejected") => void;
}

function ChatMessageItemBase({ message: m, debug, hasLiveTools, onApprovalDecision }: ChatMessageItemProps) {
  const [copied, setCopied] = React.useState(false);

  const copyMessage = React.useCallback(async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(m.content);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = m.content;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        const didCopy = document.execCommand("copy");
        textarea.remove();
        if (!didCopy) throw new Error("copy command failed");
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      // Clipboard permissions can be denied by the browser; native text
      // selection remains available as the fallback interaction.
    }
  }, [m.content]);

  // Always render tool execution cards for rich user feedback
  if (m.role === "user") {
    return (
      <div key={m.id} className="group flex max-w-[80%] flex-col items-end gap-1 self-end">
        <div className="cursor-text select-text whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-sm leading-relaxed text-secondary-foreground">
          {m.content || "…"}
        </div>
        <button
          type="button"
          onClick={() => void copyMessage()}
          className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none group-hover:opacity-100"
          aria-label={copied ? "User message copied" : "Copy user message"}
          title={copied ? "Copied" : "Copy message"}
        >
          {copied ? <Check className="h-3 w-3" aria-hidden="true" /> : <Copy className="h-3 w-3" aria-hidden="true" />}
          {copied ? "Copied" : "Copy"}
        </button>
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
        className="animate-scale-in self-start w-full max-w-[92%] shrink-0 rounded-xl border border-border bg-card/80 backdrop-blur-md shadow-card overflow-hidden"
      >
        <div className="flex items-center justify-between border-b border-border/60 bg-muted/30 px-3 py-1.5 text-[10px] font-semibold text-foreground">
          <div className="flex items-center gap-1.5">
            {isCodeTool ? <Terminal className="h-3.5 w-3.5 text-primary" /> : <Wrench className="h-3.5 w-3.5 text-warning" />}
            <span className="uppercase tracking-wider font-bold">
              {isCodeTool ? "Code Execution" : "Tool Call"}
            </span>
            <Badge variant="outline" className="ml-1 font-mono text-[9px] bg-muted text-foreground border-border">
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
        <pre className="block w-full min-h-[60px] max-h-60 overflow-y-auto overflow-x-auto p-3 font-mono text-[10.5px] text-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-all bg-muted/50">
          {codeStr}
        </pre>
        {m.meta?.progress ? (
          <div className="border-t border-border/40">
            <div className="flex items-center gap-1.5 bg-muted/20 px-3 py-1 text-[9px] uppercase tracking-wider text-muted-foreground/70">
              <Play className="h-2.5 w-2.5 text-primary animate-pulse" /> Live output
            </div>
            <pre className="block max-h-40 overflow-y-auto overflow-x-auto p-3 font-mono text-[10.5px] text-muted-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-all bg-muted/50">
              {m.meta.progress}
            </pre>
          </div>
        ) : null}
      </div>
    );
  }

  if (m.role === "tool_result") {
    const isError = m.content.toLowerCase().includes("error") || m.content.includes("exit code: 1");
    const isSvg = m.content.trim().startsWith("<svg") || m.content.includes("xmlns=\"http://www.w3.org/2000/svg\"");

    return (
      <div
        key={m.id}
        className="animate-scale-in self-start w-full max-w-[92%] shrink-0 rounded-xl border border-border/70 bg-card/90 backdrop-blur-md shadow-card overflow-hidden"
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

        <pre className="block w-full min-h-[60px] max-h-60 overflow-y-auto overflow-x-auto p-3 font-mono text-[10.5px] text-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-all bg-muted/50">
          {m.content}
        </pre>
      </div>
    );
  }

  if (m.role === "approval") {
    const status = m.meta?.approvalStatus ?? "pending";
    const args = typeof m.meta?.approvalArgs === "string"
      ? m.meta.approvalArgs
      : JSON.stringify(m.meta?.approvalArgs ?? {}, null, 2);
    return (
      <div key={m.id} className="animate-scale-in self-start w-full max-w-[92%] rounded-xl border border-warning/40 bg-warning/[0.06] p-3 shadow-card">
        <div className="flex items-center gap-2 text-xs font-semibold">
          {status === "approved" ? <ShieldCheck className="h-4 w-4 text-success" /> : status === "rejected" ? <ShieldX className="h-4 w-4 text-destructive" /> : <ShieldAlert className="h-4 w-4 text-warning" />}
          <span>{status === "pending" ? "Approval required" : status === "approved" ? "Approved" : "Rejected"}</span>
          {m.meta?.approvalTool && <Badge variant="outline" className="font-mono text-[9px]">{m.meta.approvalTool}</Badge>}
        </div>
        <pre className="mt-2 max-h-48 overflow-auto rounded-lg border border-border/50 bg-black/30 p-2 font-mono text-[10px] leading-relaxed whitespace-pre-wrap break-all">{args}</pre>
        {status === "pending" && onApprovalDecision ? (
          <div className="mt-3 flex gap-2">
            <Button size="sm" className="h-8 gap-1.5 text-xs" onClick={() => onApprovalDecision(m.id, "approved")}>
              <ShieldCheck className="h-3.5 w-3.5" /> Approve
            </Button>
            <Button size="sm" variant="outline" className="h-8 gap-1.5 text-xs" onClick={() => onApprovalDecision(m.id, "rejected")}>
              <ShieldX className="h-3.5 w-3.5" /> Reject
            </Button>
          </div>
        ) : null}
      </div>
    );
  }

  // Assistant message
  // The live activity row owns the empty-state status, so do not render a
  // second placeholder bubble for the same run. A terminal message with cost
  // metadata but no content is a legacy/incomplete response and must remain
  // visible as an actionable error instead of a blank bubble.
  const isIncompleteAssistant = !m.content && !m.meta?.reasoning && m.meta?.cost_usd != null;
  if (!m.content && !m.meta?.reasoning && !isIncompleteAssistant) return null;
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
            <div className="animate-scale-in self-start w-full max-w-[92%] shrink-0 rounded-xl border border-border bg-card/80 backdrop-blur-md shadow-card overflow-hidden mb-2">
              <div className="flex items-center gap-1.5 border-b border-border/60 bg-muted/30 px-3 py-1.5 text-[10px] font-semibold text-foreground">
                <Terminal className="h-3.5 w-3.5 text-primary" />
                <span className="uppercase tracking-wider font-bold">Executed Tool</span>
                <Badge variant="outline" className="ml-1 font-mono text-[9px] bg-muted text-foreground border-border">
                  {t.name}
                </Badge>
              </div>
              <pre className="block w-full min-h-[60px] max-h-96 overflow-y-auto overflow-x-hidden p-3 font-mono text-[10.5px] text-foreground leading-relaxed scrollbar-thin whitespace-pre-wrap break-words bg-muted/50">
                {argsText}
              </pre>
            </div>

            <div className="animate-scale-in self-start w-full max-w-[92%] shrink-0 rounded-xl border border-border/70 bg-card/90 backdrop-blur-md shadow-card overflow-hidden mb-3">
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
              <pre className="block w-full min-h-[60px] max-h-96 overflow-y-auto overflow-x-hidden p-3 font-mono text-[10.5px] leading-relaxed scrollbar-thin whitespace-pre-wrap break-words bg-muted/50">
                {t.result}
              </pre>
            </div>
          </React.Fragment>
        );
      })}

      <div className="group flex max-w-[85%] items-start gap-2.5 self-start">
        <Avatar className="mt-0.5 h-7 w-7 shrink-0 border border-border bg-muted">
          <AvatarFallback className="bg-transparent text-foreground">
            <Bot className="h-3.5 w-3.5" aria-hidden="true" />
          </AvatarFallback>
        </Avatar>
        <div className="min-w-0 flex-1 space-y-1.5 pt-0.5">
        {debug && m.meta?.reasoning ? (
          <Collapsible defaultOpen={!m.content}>
            <div className="rounded-xl border border-dashed border-border/70 bg-muted/15 px-3 py-2">
              <CollapsibleTrigger className="group flex w-full cursor-pointer items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground select-none focus-visible:outline-none">
                {!m.content ? (
                  <span className="inline-flex gap-0.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
                    <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse [animation-delay:150ms]" />
                    <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse [animation-delay:300ms]" />
                  </span>
                ) : (
                  <ChevronDown className="h-3 w-3 shrink-0 transition-transform group-data-[state=closed]:-rotate-90" aria-hidden="true" />
                )}
                Reasoning
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-2 border-t border-dashed border-border/50 pt-2">
                <p className="whitespace-pre-wrap break-words font-mono text-[11px] italic leading-relaxed text-muted-foreground">
                  {m.meta.reasoning}
                </p>
              </CollapsibleContent>
            </div>
          </Collapsible>
        ) : null}
        {(m.content || isIncompleteAssistant) && (
          <div className="select-text text-sm leading-relaxed">
          {m.content ? (
            <React.Suspense
              fallback={<span className="whitespace-pre-wrap break-words">{m.content}</span>}
            >
              <LazyMarkdownRenderer content={m.content} />
            </React.Suspense>
          ) : m.meta?.reasoning ? (
            <span className="text-sm text-muted-foreground">Generating answer…</span>
          ) : isIncompleteAssistant ? (
            <span className="text-sm text-destructive">No answer was generated. Please try again.</span>
          ) : (
            <span className="flex items-center gap-2 text-muted-foreground">
              <span className="inline-flex gap-0.5">
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:0ms]" />
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:150ms]" />
                <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce [animation-delay:300ms]" />
              </span>
              {debug && <span className="text-sm">Thinking…</span>}
            </span>
          )}
          </div>
        )}
        {(m.meta?.cost_usd != null || m.content) && (
          <div className="flex flex-wrap items-center gap-1.5">
            {m.content && (
              <button
                type="button"
                onClick={() => void copyMessage()}
                className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none group-hover:opacity-100"
                aria-label={copied ? "Message copied" : "Copy message"}
                title={copied ? "Copied" : "Copy message"}
              >
                {copied ? <Check className="h-3 w-3" aria-hidden="true" /> : <Copy className="h-3 w-3" aria-hidden="true" />}
                {copied ? "Copied" : "Copy"}
              </button>
            )}
            {m.meta?.cost_usd != null && (
              <>
                {m.meta.latency_ms != null && (
                  <Badge variant="secondary" className="gap-1 font-mono text-[10px]">
                    <Clock className="h-2.5 w-2.5" aria-hidden="true" />
                    {(m.meta.latency_ms / 1000).toFixed(1)}s
                  </Badge>
                )}
                {m.meta.in_tokens != null && (
                  <Badge variant="secondary" className="font-mono text-[10px]">
                    {m.meta.in_tokens + (m.meta.out_tokens ?? 0)} tokens
                  </Badge>
                )}
                <Badge variant="secondary" className="gap-1 font-mono text-[10px]">
                  <DollarSign className="h-2.5 w-2.5" aria-hidden="true" />
                  {m.meta.cost_usd.toFixed(5)}
                </Badge>
                {m.meta.tools?.length ? (
                  <Badge variant="secondary" className="gap-1 font-mono text-[10px]">
                    <Wrench className="h-2.5 w-2.5" aria-hidden="true" />
                    {m.meta.tools.length} tool{m.meta.tools.length > 1 ? "s" : ""}
                  </Badge>
                ) : null}
                {m.meta.model && (
                  <Badge variant="outline" className="ml-auto font-mono text-[10px]">{m.meta.model}</Badge>
                )}
              </>
            )}
          </div>
        )}
        </div>
      </div>
    </React.Fragment>
  );
}

// The thread re-renders on every streamed frame and every run poll, but the
// event reducer only replaces the message objects it actually changed. Memoing
// on those references keeps historical messages (and their markdown/tool-JSON
// parsing) out of the hot path, so cost scales with what changed rather than
// with thread length.
export const ChatMessageItem = React.memo(ChatMessageItemBase);
