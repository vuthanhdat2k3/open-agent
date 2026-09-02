"use client";

import * as React from "react";
import {
  Globe,
  Code2,
  RotateCw,
  ExternalLink,
  Copy,
  Check,
  Download,
  Maximize2,
  Minimize2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { useUrlSearchParam } from "@/hooks";

export interface WebArtifactPreviewProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  content: string;
  initialTab?: "preview" | "code";
  onDownload?: () => void;
}

export function WebArtifactPreviewDialog({
  open,
  onOpenChange,
  title,
  content,
  initialTab = "preview",
  onDownload,
}: WebArtifactPreviewProps) {
  const { tx } = useTranslation();
  const [tab, setTab] = React.useState<"preview" | "code">(initialTab);
  const [copied, setCopied] = React.useState(false);
  const [isFullscreen, setIsFullscreen] = React.useState(false);
  const [iframeKey, setIframeKey] = React.useState(0);
  const [previewParam, setPreviewParam] = useUrlSearchParam("preview");

  React.useEffect(() => {
    if (open) {
      setTab(initialTab);
      setIframeKey((k) => k + 1);
      if (title && previewParam !== title) {
        setPreviewParam(title);
      }
    }
  }, [open, initialTab, title, previewParam, setPreviewParam]);

  const handleOpenChange = React.useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen) {
        setPreviewParam(null);
      }
      onOpenChange(nextOpen);
    },
    [onOpenChange, setPreviewParam],
  );

  const handleCopy = React.useCallback(async () => {
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
  }, [content]);

  const handleOpenInNewTab = React.useCallback(() => {
    const isSvg = title.toLowerCase().endsWith(".svg");
    const mime = isSvg ? "image/svg+xml" : "text/html;charset=utf-8";
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }, [content, title]);

  const handleReload = () => {
    setIframeKey((k) => k + 1);
  };

  const handleDownload = () => {
    if (onDownload) {
      onDownload();
      return;
    }
    const isSvg = title.toLowerCase().endsWith(".svg");
    const mime = isSvg ? "image/svg+xml" : "text/html;charset=utf-8";
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = title.split("/").pop() || "artifact.html";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className={cn(
          "transition-all duration-200 flex flex-col p-0 gap-0 overflow-hidden bg-background border-border/80 shadow-2xl",
          isFullscreen
            ? "fixed inset-0 w-screen h-screen max-w-none max-h-none rounded-none z-50 m-0"
            : "max-w-5xl w-[95vw] sm:w-[90vw] h-[85vh] rounded-xl"
        )}
      >
        {/* Header Toolbar */}
        <DialogHeader className="p-3 px-4 border-b border-border/70 bg-muted/40 flex flex-row items-center justify-between space-y-0 shrink-0">
          <div className="flex items-center gap-2 min-w-0 pr-2">
            <div className="p-1.5 rounded-lg bg-primary/10 text-primary shrink-0">
              <Globe className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <DialogTitle className="text-sm font-semibold truncate font-mono">
                {title}
              </DialogTitle>
              <div className="text-[11px] text-muted-foreground">
                {tx("Xem & chạy trực tiếp ứng dụng web trong Sandbox an toàn", "Interactive live web preview in isolated sandbox")}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0 pr-10">
            {/* Tab selector */}
            <div className="flex items-center bg-muted/80 p-0.5 rounded-lg border border-border/60 mr-2">
              <button
                type="button"
                onClick={() => setTab("preview")}
                className={cn(
                  "flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-all",
                  tab === "preview"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Globe className="h-3.5 w-3.5 text-primary" />
                <span>{tx("Chạy trực tiếp", "Live Preview")}</span>
              </button>
              <button
                type="button"
                onClick={() => setTab("code")}
                className={cn(
                  "flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-all",
                  tab === "code"
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Code2 className="h-3.5 w-3.5" />
                <span>{tx("Mã nguồn", "Source Code")}</span>
              </button>
            </div>

            {/* Actions */}
            {tab === "preview" && (
              <Button
                size="sm"
                variant="outline"
                className="h-8 px-2 text-xs gap-1"
                onClick={handleReload}
                title={tx("Tải lại preview", "Reload preview")}
              >
                <RotateCw className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">{tx("Tải lại", "Reload")}</span>
              </Button>
            )}

            <Button
              size="sm"
              variant="outline"
              className="h-8 px-2 text-xs gap-1"
              onClick={handleOpenInNewTab}
              title={tx("Mở trong tab trình duyệt mới", "Open in new browser tab")}
            >
              <ExternalLink className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{tx("Tab mới", "New Tab")}</span>
            </Button>

            <Button
              size="sm"
              variant="outline"
              className="h-8 px-2 text-xs gap-1"
              onClick={handleCopy}
              title={tx("Sao chép mã nguồn", "Copy code")}
            >
              {copied ? (
                <Check className="h-3.5 w-3.5 text-emerald-500" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
              <span className="hidden sm:inline">
                {copied ? tx("Đã chép", "Copied") : tx("Sao chép", "Copy")}
              </span>
            </Button>

            <Button
              size="sm"
              variant="outline"
              className="h-8 px-2 text-xs gap-1"
              onClick={handleDownload}
              title={tx("Tải tệp xuống", "Download file")}
            >
              <Download className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{tx("Tải về", "Download")}</span>
            </Button>

            <Button
              size="sm"
              variant="ghost"
              className="h-8 w-8 p-0"
              onClick={() => setIsFullscreen((prev) => !prev)}
              title={isFullscreen ? tx("Thu nhỏ", "Exit fullscreen") : tx("Toàn màn hình", "Fullscreen")}
            >
              {isFullscreen ? (
                <Minimize2 className="h-3.5 w-3.5" />
              ) : (
                <Maximize2 className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
        </DialogHeader>

        {/* Content Body */}
        <div className="flex-1 min-h-0 relative bg-background">
          {tab === "preview" ? (
            <iframe
              key={iframeKey}
              title={title}
              srcDoc={content}
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
              className="w-full h-full border-0 bg-white"
            />
          ) : (
            <div className="h-full overflow-auto p-4 bg-muted/20 font-mono text-xs text-foreground select-text">
              <pre className="whitespace-pre-wrap leading-relaxed">
                <code>{content}</code>
              </pre>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
