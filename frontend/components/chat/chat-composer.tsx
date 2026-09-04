"use client";

import * as React from "react";
import { ArrowUp, Loader2, Paperclip, Square, X, Cpu, ShieldCheck, ChevronDown } from "lucide-react";
import { Textarea } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { useUploadFile } from "@/hooks";
import { useTranslation } from "@/lib/i18n";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { UploadedFile, Model, ExecutionPolicy } from "@/types";

interface ChatComposerProps {
  draft: string;
  onDraftChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  streaming?: boolean;
  onStop?: () => void;
  attachments: UploadedFile[];
  onAttachmentsChange: (files: UploadedFile[]) => void;
  /** Floating card for the empty state vs. a plain full-width bar once a
   *  conversation is underway — same internals, different chrome. */
  variant?: "floating" | "docked";
  placeholder?: string;
  className?: string;
  models?: Model[];
  effectiveModel?: Model;
  onModelChange?: (modelId: string) => void;
  executionPolicy?: ExecutionPolicy;
  onExecutionPolicyChange?: (policy: ExecutionPolicy) => void;
}

// Shared by ChatEmptyState (centered, empty thread) and the docked composer
// (active conversation) so attach/send behave identically everywhere. Attach
// uploads through the real /api/files/upload pipeline (same one the /files
// page uses) — the file is referenced by name in the sent message so the
// agent's tools can look it up, not a decorative button.
export function ChatComposer({
  draft,
  onDraftChange,
  onSubmit,
  disabled,
  streaming = false,
  onStop,
  attachments,
  onAttachmentsChange,
  variant = "docked",
  placeholder,
  className,
  models,
  effectiveModel,
  onModelChange,
  executionPolicy,
  onExecutionPolicyChange,
}: ChatComposerProps) {
  const { t, locale, tx } = useTranslation();
  const defaultPlaceholder = tx("Nhập tin nhắn… (Enter để gửi, Shift+Enter để xuống dòng)", "Type a message… (Enter to send, Shift+Enter for newline)");
  const activePlaceholder = placeholder || defaultPlaceholder;
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const upload = useUploadFile();

  const adjustHeight = React.useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "48px";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  const handleFiles = async (fileList: FileList | null) => {
    if (!fileList?.length) return;
    const nextAttachments = [...attachments];
    for (const file of Array.from(fileList)) {
      try {
        const uploaded = await upload.mutateAsync(file);
        nextAttachments.push(uploaded);
      } catch (err: any) {
        toast.error(err?.message || tx("Không thể tải lên tệp", "Could not upload file"));
      }
    }
    if (nextAttachments.length !== attachments.length) {
      onAttachmentsChange(nextAttachments);
    }
  };

  return (
    <div className={cn("relative rounded-xl border border-border bg-card shadow-card", variant === "floating" && "bg-card/80 backdrop-blur-md", className)}>
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-b border-border/60 p-2">
          {attachments.map((file) => (
            <span key={file.id} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/60 py-1 pl-2.5 pr-1 text-[11px] text-muted-foreground">
              <span className="max-w-[10rem] truncate">{file.original_name}</span>
              <button
                type="button"
                onClick={() => onAttachmentsChange(attachments.filter((f) => f.id !== file.id))}
                className="rounded-full p-0.5 hover:bg-destructive/15 hover:text-destructive"
                aria-label={tx(`Xóa ${file.original_name}`, `Remove ${file.original_name}`)}
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      )}

      <label htmlFor="chat-composer" className="sr-only">{tx("Tin nhắn", "Message")}</label>
      <Textarea
        id="chat-composer"
        ref={textareaRef}
        value={draft}
        onChange={(e) => {
          onDraftChange(e.target.value);
          adjustHeight();
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!streaming) onSubmit();
          }
        }}
        placeholder={activePlaceholder}
        className="min-h-[48px] w-full resize-none border-none bg-transparent px-4 py-3 text-sm shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
        style={{ overflow: "hidden" }}
      />

      <div className="flex items-center justify-between p-2">
        <div className="flex items-center gap-1">
          <input ref={fileInputRef} type="file" multiple hidden onChange={(e) => { void handleFiles(e.target.files); e.target.value = ""; }} />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-foreground"
            onClick={() => fileInputRef.current?.click()}
            disabled={upload.isPending}
            aria-label={tx("Đính kèm tệp", "Attach file")}
            title={tx("Đính kèm tệp", "Attach file")}
          >
            {upload.isPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Paperclip className="h-4 w-4" aria-hidden="true" />}
          </Button>

          {executionPolicy && onExecutionPolicyChange && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button type="button" variant="ghost" size="sm" disabled={streaming} className="h-7 gap-1.5 rounded-full px-2.5 text-xs font-medium text-muted-foreground hover:text-foreground">
                  <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                  <span className="hidden sm:inline max-w-[8rem] truncate">
                    {executionPolicy === "read-only" ? tx("Chỉ đọc", "Read-only") : executionPolicy === "full-access" ? tx("Toàn quyền tự động", "Full access") : tx("Cần phê duyệt", "Manual approval")}
                  </span>
                  <ChevronDown className="h-3 w-3 opacity-60" aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-64">
                <DropdownMenuLabel>{tx("Quyền thực thi hệ thống", "System Execution Policy")}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {[
                  { value: "read-only", label: tx("Chỉ đọc", "Read-only"), description: tx("Chỉ cho phép truy vấn an toàn, chặn ghi và chạy mã", "Safe queries only, blocks writes and execution") },
                  { value: "manual", label: tx("Cần phê duyệt", "Manual approval"), description: tx("Yêu cầu người dùng duyệt trước khi ghi hoặc chạy mã", "Requires user approval for mutating or dangerous actions") },
                  { value: "full-access", label: tx("Toàn quyền tự động", "Full access"), description: tx("Tự động chạy mọi công cụ mà không cần phê duyệt", "Autonomous execution for all permitted tools") },
                ].map((option) => (
                  <DropdownMenuItem
                    key={option.value}
                    onSelect={() => onExecutionPolicyChange(option.value as ExecutionPolicy)}
                    className={`flex flex-col items-start gap-0.5 py-1.5 ${option.value === executionPolicy ? "font-semibold text-foreground bg-primary/10" : undefined}`}
                  >
                    <span className="text-xs font-medium">{option.label}</span>
                    <span className="text-[10px] text-muted-foreground leading-tight font-normal">{option.description}</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        <div className="flex items-center gap-2">
          {onModelChange && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={streaming || !models || models.length === 0}
                  className="h-7 gap-1.5 rounded-full px-2.5 text-xs font-medium text-muted-foreground hover:text-foreground"
                >
                  <Cpu className="h-3.5 w-3.5" aria-hidden="true" />
                  <span className="max-w-[9rem] truncate font-mono">
                    {effectiveModel?.display_name || effectiveModel?.name || tx("Mô hình", "Model")}
                  </span>
                  <ChevronDown className="h-3 w-3 opacity-60" aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuLabel>{tx("Mô hình AI", "Model")}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {models?.filter((m) => m.active).map((m) => (
                  <DropdownMenuItem key={m.id} onSelect={() => onModelChange(m.id)} className={m.id === effectiveModel?.id ? "font-semibold text-foreground" : undefined}>
                    <span className="flex-1 truncate">{m.display_name || m.name}</span>
                    <span className="ml-2 shrink-0 text-[9px] uppercase tracking-wider text-muted-foreground/60">{m.tier}</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          <Button
            type="button"
            size="icon"
            onClick={streaming ? onStop : onSubmit}
            disabled={streaming ? false : disabled}
            variant={streaming ? "outline" : "default"}
            className="h-8 w-8 rounded-lg"
            aria-label={streaming ? tx("Dừng phản hồi", "Stop streaming") : tx("Gửi tin nhắn", "Send message")}
            title={streaming ? tx("Dừng phản hồi", "Stop streaming") : tx("Gửi tin nhắn", "Send message")}
          >
            {streaming ? <Square className="h-3.5 w-3.5" aria-hidden="true" /> : <ArrowUp className="h-4 w-4" aria-hidden="true" />}
          </Button>
        </div>
      </div>
    </div>
  );
}
