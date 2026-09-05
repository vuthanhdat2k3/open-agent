"use client";

import * as React from "react";
import {
  FileText,
  FileSpreadsheet,
  FileCode,
  FileArchive,
  File,
  Download,
  Maximize2,
  X,
  Eye,
  ImageIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";

export interface AttachmentItem {
  id: string;
  name: string;
  size?: number;
  content_type?: string;
  error?: string;
  download_url?: string;
  content_url?: string;
}

export interface FileAttachmentCardProps {
  attachment: AttachmentItem;
  variant?: "message" | "composer";
  onRemove?: () => void;
  className?: string;
}

export function formatFileSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return "";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function isImageAttachment(att: { name: string; content_type?: string }): boolean {
  if (att.content_type?.startsWith("image/")) return true;
  return /\.(png|jpe?g|gif|webp|svg|bmp|ico)$/i.test(att.name || "");
}

function getFileMeta(name: string) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  if (["pdf"].includes(ext)) {
    return {
      type: "pdf",
      icon: FileText,
      color: "text-rose-500",
      bg: "bg-rose-500/10 border-rose-500/20",
    };
  }
  if (["csv", "xlsx", "xls", "tsv"].includes(ext)) {
    return {
      type: "spreadsheet",
      icon: FileSpreadsheet,
      color: "text-emerald-500",
      bg: "bg-emerald-500/10 border-emerald-500/20",
    };
  }
  if (["json", "yaml", "yml", "js", "ts", "tsx", "jsx", "py", "sql", "sh", "bash", "html", "css", "rs", "go", "cpp", "c"].includes(ext)) {
    return {
      type: "code",
      icon: FileCode,
      color: "text-purple-500",
      bg: "bg-purple-500/10 border-purple-500/20",
    };
  }
  if (["zip", "tar", "gz", "7z", "rar"].includes(ext)) {
    return {
      type: "archive",
      icon: FileArchive,
      color: "text-amber-500",
      bg: "bg-amber-500/10 border-amber-500/20",
    };
  }
  return {
    type: "file",
    icon: File,
    color: "text-blue-500",
    bg: "bg-blue-500/10 border-blue-500/20",
  };
}

export function FileAttachmentCard({
  attachment,
  variant = "message",
  onRemove,
  className,
}: FileAttachmentCardProps) {
  const { tx } = useTranslation();
  const [imageOpen, setImageOpen] = React.useState(false);
  const [imgError, setImgError] = React.useState(false);

  const isImg = isImageAttachment(attachment);
  const contentUrl = attachment.content_url || `/api/files/${attachment.id}/content`;
  const downloadUrl = attachment.download_url || contentUrl;
  const formattedSize = formatFileSize(attachment.size);
  const fileMeta = getFileMeta(attachment.name);
  const Icon = fileMeta.icon;

  // 1. Composer Variant (Compact preview before sending)
  if (variant === "composer") {
    if (isImg && !imgError) {
      return (
        <div
          className={cn(
            "group relative flex items-center gap-2 rounded-xl border border-border/80 bg-muted/40 p-1.5 pr-2 transition-all hover:border-border hover:bg-muted/70",
            className,
          )}
        >
          <div className="relative h-10 w-10 shrink-0 overflow-hidden rounded-lg border border-border/50 bg-background/50">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={contentUrl}
              alt={attachment.name}
              onError={() => setImgError(true)}
              className="h-full w-full object-cover"
            />
          </div>
          <div className="flex min-w-0 flex-col">
            <span className="max-w-[12rem] truncate text-xs font-medium text-foreground" title={attachment.name}>
              {attachment.name}
            </span>
            {formattedSize && (
              <span className="text-[10px] text-muted-foreground">{formattedSize}</span>
            )}
          </div>
          {onRemove && (
            <button
              type="button"
              onClick={onRemove}
              className="ml-1 rounded-full p-1 text-muted-foreground transition-colors hover:bg-destructive/15 hover:text-destructive"
              aria-label={tx(`Xóa ${attachment.name}`, `Remove ${attachment.name}`)}
              title={tx("Xóa tệp", "Remove file")}
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          )}
        </div>
      );
    }

    return (
      <div
        className={cn(
          "group relative flex items-center gap-2 rounded-xl border border-border/80 bg-muted/40 p-1.5 pr-2 transition-all hover:border-border hover:bg-muted/70",
          className,
        )}
      >
        <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border", fileMeta.bg)}>
          <Icon className={cn("h-5 w-5", fileMeta.color)} aria-hidden="true" />
        </div>
        <div className="flex min-w-0 flex-col">
          <span className="max-w-[12rem] truncate text-xs font-medium text-foreground" title={attachment.name}>
            {attachment.name}
          </span>
          {formattedSize && (
            <span className="text-[10px] text-muted-foreground">{formattedSize}</span>
          )}
        </div>
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            className="ml-1 rounded-full p-1 text-muted-foreground transition-colors hover:bg-destructive/15 hover:text-destructive"
            aria-label={tx(`Xóa ${attachment.name}`, `Remove ${attachment.name}`)}
            title={tx("Xóa tệp", "Remove file")}
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        )}
      </div>
    );
  }

  // 2. Message Variant (Chat bubble display)
  if (isImg && !imgError) {
    return (
      <>
        <div
          role="button"
          tabIndex={0}
          onClick={() => setImageOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              setImageOpen(true);
            }
          }}
          className={cn(
            "group relative max-w-[280px] cursor-pointer overflow-hidden rounded-2xl border border-border/70 bg-card/80 shadow-sm transition-all duration-200 hover:border-primary/50 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:max-w-[320px]",
            className,
          )}
          title={tx("Nhấn để xem ảnh phóng to", "Click to enlarge image")}
        >
          <div className="relative aspect-[4/3] w-full overflow-hidden bg-muted/40">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={contentUrl}
              alt={attachment.name}
              onError={() => setImgError(true)}
              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
              loading="lazy"
            />
            {/* Hover overlay with zoom hint */}
            <div className="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 backdrop-blur-[1px] transition-opacity duration-200 group-hover:opacity-100">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-black/60 px-3 py-1 text-xs font-medium text-white shadow-sm">
                <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
                {tx("Xem ảnh", "View image")}
              </span>
            </div>
          </div>
          <div className="flex items-center justify-between gap-2 px-3 py-2 text-xs">
            <span className="truncate font-medium text-foreground" title={attachment.name}>
              {attachment.name}
            </span>
            {formattedSize && (
              <span className="shrink-0 text-[11px] text-muted-foreground">{formattedSize}</span>
            )}
          </div>
        </div>

        {/* Lightbox Dialog */}
        <Dialog open={imageOpen} onOpenChange={setImageOpen}>
          <DialogContent className="max-h-[92vh] max-w-4xl p-4 sm:p-6">
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between border-b border-border/60 pb-3 pr-8">
                <div className="flex items-center gap-2 overflow-hidden">
                  <ImageIcon className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                  <DialogTitle className="truncate text-sm font-semibold sm:text-base">
                    {attachment.name}
                  </DialogTitle>
                </div>
                {formattedSize && (
                  <span className="shrink-0 rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                    {formattedSize}
                  </span>
                )}
              </div>
              <DialogDescription className="sr-only">
                {tx("Xem chi tiết ảnh đính kèm", "View attached image preview")}
              </DialogDescription>
              <div className="relative flex max-h-[70vh] items-center justify-center overflow-auto rounded-xl bg-muted/20 p-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={contentUrl}
                  alt={attachment.name}
                  className="max-h-[68vh] w-auto max-w-full rounded-lg object-contain shadow-sm"
                />
              </div>
              <div className="flex items-center justify-end gap-2 pt-1">
                <a
                  href={downloadUrl}
                  download={attachment.name}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-medium text-foreground shadow-sm transition-colors hover:bg-accent hover:text-foreground"
                >
                  <Download className="h-3.5 w-3.5" aria-hidden="true" />
                  {tx("Tải ảnh về", "Download image")}
                </a>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </>
    );
  }

  // Non-image Document card in message bubble
  return (
    <div
      className={cn(
        "group flex max-w-[280px] items-center gap-3 rounded-2xl border border-border/80 bg-card/90 p-2.5 shadow-sm transition-all duration-200 hover:border-border hover:bg-card hover:shadow-md sm:max-w-[320px]",
        className,
      )}
    >
      <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border shadow-xs", fileMeta.bg)}>
        <Icon className={cn("h-5 w-5", fileMeta.color)} aria-hidden="true" />
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-xs font-semibold text-foreground" title={attachment.name}>
          {attachment.name}
        </span>
        <div className="flex items-center gap-2">
          {formattedSize ? (
            <span className="text-[11px] text-muted-foreground">{formattedSize}</span>
          ) : (
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
              {attachment.name.split(".").pop() || "FILE"}
            </span>
          )}
          {attachment.error && (
            <span className="truncate text-[10px] text-destructive" title={attachment.error}>
              • {tx("Lỗi", "Error")}
            </span>
          )}
        </div>
      </div>
      <a
        href={downloadUrl}
        download={attachment.name}
        target="_blank"
        rel="noreferrer"
        className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={tx(`Tải xuống ${attachment.name}`, `Download ${attachment.name}`)}
        title={tx("Tải tệp xuống", "Download file")}
      >
        <Download className="h-4 w-4" aria-hidden="true" />
      </a>
    </div>
  );
}
