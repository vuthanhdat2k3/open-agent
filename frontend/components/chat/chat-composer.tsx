"use client";

import * as React from "react";
import { ArrowUp, Loader2, Paperclip, Square, X } from "lucide-react";
import { Textarea } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useUploadFile } from "@/hooks";
import { useTranslation } from "@/lib/i18n";
import type { UploadedFile } from "@/types";

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
    for (const file of Array.from(fileList)) {
      try {
        const uploaded = await upload.mutateAsync(file);
        onAttachmentsChange([...attachments, uploaded]);
      } catch {
        // useUploadFile's mutation error is surfaced via its own isError
        // state where callers show it; nothing more to do per-file here.
      }
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
                aria-label={`Remove ${file.original_name}`}
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>
      )}

      <label htmlFor="chat-composer" className="sr-only">{tx("Message", "Message")}</label>
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
        <input ref={fileInputRef} type="file" multiple hidden onChange={(e) => { void handleFiles(e.target.files); e.target.value = ""; }} />
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-foreground"
          onClick={() => fileInputRef.current?.click()}
          disabled={upload.isPending}
          aria-label="Attach file"
          title={tx("Attach file", "Attach file")}
        >
          {upload.isPending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Paperclip className="h-4 w-4" aria-hidden="true" />}
        </Button>

        <Button
          type="button"
          size="icon"
          onClick={streaming ? onStop : onSubmit}
          disabled={streaming ? false : disabled}
          variant={streaming ? "outline" : "default"}
          className="h-8 w-8 rounded-lg"
          aria-label={streaming ? "Stop streaming" : "Send message"}
          title={streaming ? "Stop streaming" : "Send message"}
        >
          {streaming ? <Square className="h-3.5 w-3.5" aria-hidden="true" /> : <ArrowUp className="h-4 w-4" aria-hidden="true" />}
        </Button>
      </div>
    </div>
  );
}
