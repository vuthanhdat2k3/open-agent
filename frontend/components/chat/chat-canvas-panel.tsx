"use client";

import * as React from "react";
import {
  X,
  Maximize2,
  Minimize2,
  Copy,
  Check,
  Download,
  Play,
  RotateCw,
  ExternalLink,
  Code2,
  Eye,
  FileCode,
  Terminal,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { useCanvasStore } from "@/stores";
import { streamSSE } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { inferLanguage } from "@/lib/chat/canvas-utils";

export function ChatCanvasPanel() {
  const { tx } = useTranslation();
  const { activeItem, isFullscreen, closeCanvas, toggleFullscreen } = useCanvasStore();

  const [activeTab, setActiveTab] = React.useState<"code" | "preview">("code");
  const [copied, setCopied] = React.useState(false);

  // Content fetching state
  const [content, setContent] = React.useState<string>(activeItem?.code || "");
  const [isLoadingContent, setIsLoadingContent] = React.useState(false);
  const [contentError, setContentError] = React.useState<string | null>(null);

  // HTML preview reload key
  const [iframeKey, setIframeKey] = React.useState(0);

  // Sandbox run state
  const [isRunning, setIsRunning] = React.useState(false);
  const [logs, setLogs] = React.useState<string[]>([]);
  const [exitCode, setExitCode] = React.useState<number | null>(null);
  const [runError, setRunError] = React.useState<string | null>(null);
  const logEndRef = React.useRef<HTMLDivElement>(null);

  const lang = (activeItem?.language || (activeItem?.title ? inferLanguage(activeItem.title) : "")).toLowerCase();
  const isHtml = lang === "html" || lang === "htm" || activeItem?.title?.toLowerCase().endsWith(".svg");
  const isRunnable = lang === "python" || lang === "bash" || lang === "sh" || lang === "javascript" || lang === "node";
  const hasPreview = isHtml || isRunnable;

  // Initialize or fetch content whenever activeItem changes
  React.useEffect(() => {
    if (!activeItem) return;

    if (activeItem.initialTab) {
      setActiveTab(activeItem.initialTab);
    } else if (isHtml) {
      setActiveTab("preview");
    } else {
      setActiveTab("code");
    }

    setLogs([]);
    setExitCode(null);
    setRunError(null);

    if (activeItem.code !== undefined) {
      setContent(activeItem.code);
      setIsLoadingContent(false);
      setContentError(null);
      return;
    }

    if (activeItem.contentUrl) {
      setIsLoadingContent(true);
      setContentError(null);
      fetch(activeItem.contentUrl)
        .then(async (res) => {
          if (!res.ok) {
            throw new Error(`Failed to load content (${res.status})`);
          }
          return res.text();
        })
        .then((text) => {
          setContent(text);
          setIsLoadingContent(false);
        })
        .catch((err) => {
          setContentError(err instanceof Error ? err.message : "Error loading content");
          setIsLoadingContent(false);
        });
    }
  }, [activeItem, activeItem?.code, activeItem?.contentUrl, isHtml]);

  // Auto scroll terminal logs
  React.useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, exitCode, runError]);

  if (!activeItem) return null;

  const handleCopy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(content);
      } else {
        const ta = document.createElement("textarea");
        ta.value = content;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore
    }
  };

  const handleDownload = () => {
    if (activeItem.downloadUrl) {
      const a = document.createElement("a");
      a.href = activeItem.downloadUrl;
      a.download = activeItem.title;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      return;
    }

    const isSvg = activeItem.title.toLowerCase().endsWith(".svg");
    const mime = isSvg ? "image/svg+xml" : "text/plain;charset=utf-8";
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = activeItem.title;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleOpenNewTab = () => {
    const isSvg = activeItem.title.toLowerCase().endsWith(".svg");
    const mime = isSvg ? "image/svg+xml" : "text/html;charset=utf-8";
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  };

  const handleRunCode = async () => {
    if (isRunning || !content) return;
    setIsRunning(true);
    setLogs([]);
    setExitCode(null);
    setRunError(null);
    setActiveTab("preview");

    const targetLang = lang === "sh" ? "bash" : lang === "javascript" ? "node" : lang;

    try {
      await streamSSE(
        "/api/sandbox/run",
        { language: targetLang, code: content },
        (ev) => {
          if (ev.event === "stdout") {
            const line = ev.data?.line ?? "";
            setLogs((prev) => [...prev, line]);
          } else if (ev.event === "exit") {
            const code = ev.data?.code ?? 0;
            setExitCode(code);
          } else if (ev.event === "error") {
            setRunError(ev.data?.message || tx("Lỗi thực thi", "Execution error"));
          }
        },
      );
    } catch (e: any) {
      setRunError(e.message || tx("Lỗi thực thi", "Execution error"));
    } finally {
      setIsRunning(false);
    }
  };

  const lines = content.split("\n");

  return (
    <div
      className={cn(
        "flex flex-col bg-background transition-all duration-200 shrink-0",
        isFullscreen
          ? "fixed inset-0 z-50 w-screen h-screen border-l-0"
          : "fixed inset-0 z-40 w-full h-full border-l-0 lg:relative lg:inset-auto lg:z-20 lg:w-[50%] xl:w-[48%] lg:border-l lg:border-border/80 min-h-0 shrink-0",
      )}
    >
      {/* 1. Header Toolbar */}
      <div className="flex h-13 shrink-0 items-center justify-between border-b border-border/70 bg-card/60 px-4 backdrop-blur-xs">
        {/* File / Title info */}
        <div className="flex items-center gap-2 min-w-0 pr-2">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <FileCode className="h-4 w-4" aria-hidden="true" />
          </div>
          <div className="min-w-0 flex flex-col">
            <span className="truncate text-xs font-semibold text-foreground font-mono max-w-[120px] sm:max-w-[180px] lg:max-w-[200px]" title={activeItem.title}>
              {activeItem.title}
            </span>
            {lang && (
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-mono">
                {lang}
              </span>
            )}
          </div>
        </div>

        {/* Tab & Action Controls */}
        <div className="flex items-center gap-1.5 shrink-0">
          {/* Tabs switch */}
          {hasPreview && (
            <div className="flex items-center rounded-lg border border-border/70 bg-muted/60 p-0.5 mr-1">
              <button
                type="button"
                onClick={() => setActiveTab("code")}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                  activeTab === "code"
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Code2 className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{tx("Mã nguồn", "Code")}</span>
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("preview")}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                  activeTab === "preview"
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {isHtml ? <Eye className="h-3.5 w-3.5" aria-hidden="true" /> : <Terminal className="h-3.5 w-3.5" aria-hidden="true" />}
                <span>{isHtml ? tx("Xem trước", "Preview") : tx("Chạy thử", "Run")}</span>
              </button>
            </div>
          )}

          {/* Run button for runnable files */}
          {isRunnable && (
            <Button
              size="sm"
              variant="default"
              className="h-8 gap-1.5 px-2.5 text-xs font-medium bg-emerald-600 hover:bg-emerald-700 text-white"
              onClick={handleRunCode}
              disabled={isRunning || isLoadingContent}
              title={tx("Chạy code trong Sandbox an toàn", "Run code in isolated sandbox")}
            >
              {isRunning ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                  <span className="hidden xl:inline">{tx("Đang chạy...", "Running...")}</span>
                </>
              ) : (
                <>
                  <Play className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
                  <span className="hidden xl:inline">{tx("Chạy", "Run")}</span>
                </>
              )}
            </Button>
          )}

          {/* Copy button */}
          <Button
            size="sm"
            variant="outline"
            className="h-8 gap-1.5 px-2 text-xs"
            onClick={handleCopy}
            disabled={isLoadingContent || !content}
            title={copied ? tx("Đã sao chép", "Copied") : tx("Sao chép mã nguồn", "Copy code")}
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-emerald-500" aria-hidden="true" />
            ) : (
              <Copy className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            <span className="hidden xl:inline">{copied ? tx("Đã chép", "Copied") : tx("Sao chép", "Copy")}</span>
          </Button>

          {/* Download button */}
          <Button
            size="sm"
            variant="outline"
            className="h-8 w-8 p-0"
            onClick={handleDownload}
            disabled={isLoadingContent || !content}
            title={tx("Tải tệp xuống", "Download file")}
          >
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>

          {/* Fullscreen toggle button */}
          <Button
            size="sm"
            variant="ghost"
            className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
            onClick={toggleFullscreen}
            title={isFullscreen ? tx("Thu nhỏ", "Exit fullscreen") : tx("Toàn màn hình", "Fullscreen")}
          >
            {isFullscreen ? (
              <Minimize2 className="h-3.5 w-3.5" aria-hidden="true" />
            ) : (
              <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </Button>

          {/* Close button */}
          <Button
            size="sm"
            variant="ghost"
            className="h-8 w-8 p-0 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            onClick={closeCanvas}
            title={tx("Đóng Canvas (Esc)", "Close Canvas (Esc)")}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {/* 2. Content Body */}
      <div className="relative flex-1 min-h-0 overflow-hidden bg-card/20">
        {isLoadingContent ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin text-primary" aria-hidden="true" />
            <span className="text-xs">{tx("Đang tải nội dung tệp...", "Loading file content...")}</span>
          </div>
        ) : contentError ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-destructive">
            <AlertCircle className="h-8 w-8" aria-hidden="true" />
            <span className="text-sm font-semibold">{tx("Không thể tải nội dung", "Could not load content")}</span>
            <span className="text-xs text-muted-foreground">{contentError}</span>
          </div>
        ) : activeTab === "code" ? (
          /* Code View with Line Numbers */
          <div className="flex h-full w-full overflow-auto font-mono text-xs select-text">
            {/* Line numbers column */}
            <div
              className="sticky left-0 flex flex-col shrink-0 select-none border-r border-border/40 bg-muted/20 px-3 py-4 text-right text-[11px] text-muted-foreground/60"
              aria-hidden="true"
            >
              {lines.map((_, idx) => (
                <span key={idx} className="leading-relaxed">
                  {idx + 1}
                </span>
              ))}
            </div>

            {/* Code lines */}
            <div className="flex-1 min-w-0 p-4">
              <pre className="m-0 whitespace-pre leading-relaxed text-foreground/90 font-mono">
                <code>{content}</code>
              </pre>
            </div>
          </div>
        ) : isHtml ? (
          /* Live HTML / Web Preview */
          <div className="flex h-full flex-col">
            <div className="flex h-9 shrink-0 items-center justify-between border-b border-border/60 bg-muted/40 px-3">
              <span className="text-[11px] text-muted-foreground font-mono">
                {tx("Sandbox HTML Preview", "Sandbox HTML Preview")}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2 text-[11px] gap-1 text-muted-foreground hover:text-foreground"
                  onClick={() => setIframeKey((k) => k + 1)}
                  title={tx("Tải lại preview", "Reload preview")}
                >
                  <RotateCw className="h-3 w-3" aria-hidden="true" />
                  <span>{tx("Tải lại", "Reload")}</span>
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2 text-[11px] gap-1 text-muted-foreground hover:text-foreground"
                  onClick={handleOpenNewTab}
                  title={tx("Mở trang trong tab mới", "Open in new tab")}
                >
                  <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  <span>{tx("Tab mới", "New tab")}</span>
                </Button>
              </div>
            </div>
            <div className="flex-1 min-h-0 bg-white">
              <iframe
                key={iframeKey}
                title={activeItem.title}
                srcDoc={content}
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                className="h-full w-full border-0"
              />
            </div>
          </div>
        ) : (
          /* Live Code Execution Console Output */
          <div className="flex h-full flex-col overflow-hidden">
            {/* Top mini code view */}
            <div className="max-h-[45%] flex-1 overflow-auto border-b border-border/70 bg-muted/10 p-4 font-mono text-xs">
              <pre className="m-0 whitespace-pre-wrap leading-relaxed text-muted-foreground font-mono">
                <code>{content}</code>
              </pre>
            </div>

            {/* Bottom terminal logs */}
            <div className="flex flex-1 flex-col min-h-0 bg-zinc-950 text-zinc-100 font-mono text-xs">
              <div className="flex h-8 shrink-0 items-center justify-between border-b border-zinc-800 px-3">
                <div className="flex items-center gap-1.5 text-zinc-400 text-[11px]">
                  <Terminal className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{tx("Sandbox Terminal Console", "Sandbox Terminal Console")}</span>
                </div>
                {exitCode !== null && (
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px] font-semibold",
                      exitCode === 0 ? "bg-emerald-950 text-emerald-400 border border-emerald-800" : "bg-rose-950 text-rose-400 border border-rose-800",
                    )}
                  >
                    exit: {exitCode}
                  </span>
                )}
              </div>

              <div className="flex-1 min-h-0 overflow-auto p-3 space-y-1 select-text">
                {logs.length === 0 && !isRunning && !runError && (
                  <div className="text-zinc-500 text-[11px] italic">
                    {tx("Bấm 'Chạy' để thực thi mã nguồn trong sandbox.", "Click 'Run' to execute code in sandbox.")}
                  </div>
                )}
                {logs.map((line, idx) => (
                  <div key={idx} className="whitespace-pre-wrap leading-tight text-zinc-200">
                    {line}
                  </div>
                ))}
                {runError && (
                  <div className="text-rose-400 text-xs font-semibold pt-1">
                    {runError}
                  </div>
                )}
                <div ref={logEndRef} />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
