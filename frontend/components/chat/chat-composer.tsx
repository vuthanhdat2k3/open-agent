"use client";

import * as React from "react";
import { ArrowUp, Loader2, Paperclip, Square, X, Cpu, ShieldCheck, ChevronDown, Eye, AlertCircle } from "lucide-react";
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
import { FileAttachmentCard } from "./file-attachment-card";
import { SlashCommandMenu } from "./slash-command-menu";
import { SLASH_COMMANDS, filterCommands, getCommand } from "./commands/registry";
import type { SlashCommand, SlashCommandOption } from "./commands/types";
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
  /** Callback to clear conversation history */
  onClear?: () => void;
  /** Callback to reset session (new conversation) */
  onReset?: () => void;
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
  onClear,
  onReset,
}: ChatComposerProps) {
  const { t, locale, tx } = useTranslation();
  const defaultPlaceholder = tx("Nhập tin nhắn… (Enter để gửi, Shift+Enter để xuống dòng). Gõ / để xem lệnh.", "Type a message… (Enter to send, Shift+Enter for newline). Type / for commands.");
  const activePlaceholder = placeholder || defaultPlaceholder;
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);
  const upload = useUploadFile();

  // Slash command state
  const [showSlashMenu, setShowSlashMenu] = React.useState(false);
  const [slashQuery, setSlashQuery] = React.useState("");
  const [slashActiveIndex, setSlashActiveIndex] = React.useState(0);
  const [slashCommand, setSlashCommand] = React.useState<SlashCommand | null>(null);
  const [slashOptions, setSlashOptions] = React.useState<SlashCommandOption[]>([]);

  const adjustHeight = React.useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "48px";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  const isImageFile = (filename: string) => /\.(png|jpe?g|gif|webp)$/i.test(filename || "");
  const hasImageAttachment = attachments.some((f) => isImageFile(f.original_name));
  const modelSupportsVision = Boolean(effectiveModel?.supports_vision);
  const recommendedVisionModel = React.useMemo(() => {
    return models?.find((m) => m.active && m.supports_vision);
  }, [models]);

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

  // Slash command handlers
  const closeSlashMenu = React.useCallback(() => {
    setShowSlashMenu(false);
    setSlashQuery("");
    setSlashCommand(null);
    setSlashOptions([]);
    setSlashActiveIndex(0);
  }, []);

  const executeCommand = React.useCallback(
    async (cmd: SlashCommand, args: string) => {
      const context = {
        draft,
        models: models || [],
        effectiveModel,
        executionPolicy,
        onModelChange: onModelChange || (() => {}),
        onExecutionPolicyChange: onExecutionPolicyChange || (() => {}),
        onClear: onClear || (() => {}),
        onReset: onReset || (() => {}),
        onDraftChange,
        tx,
      };
      try {
        await cmd.execute(args, context);
      } catch (err) {
        console.error(`[slash-command] /${cmd.name} failed:`, err);
      }
      closeSlashMenu();
    },
    [draft, models, effectiveModel, executionPolicy, onModelChange, onExecutionPolicyChange, onClear, onReset, onDraftChange, tx, closeSlashMenu]
  );

  const handleSelectCommand = React.useCallback(
    (cmd: SlashCommand) => {
      // If command has options, show them
      if (cmd.getOptions) {
        const options = cmd.getOptions({
          draft,
          models: models || [],
          effectiveModel,
          executionPolicy,
          onModelChange: onModelChange || (() => {}),
          onExecutionPolicyChange: onExecutionPolicyChange || (() => {}),
          onClear: onClear || (() => {}),
          onReset: onReset || (() => {}),
          onDraftChange,
          tx,
        });
        setSlashCommand(cmd);
        setSlashOptions(options);
        setSlashActiveIndex(0);
      } else {
        // Execute immediately
        executeCommand(cmd, "");
      }
    },
    [draft, models, effectiveModel, executionPolicy, onModelChange, onExecutionPolicyChange, onClear, onReset, onDraftChange, tx, executeCommand]
  );

  const handleSelectOption = React.useCallback(
    (option: SlashCommandOption) => {
      if (slashCommand) {
        executeCommand(slashCommand, option.id);
      }
    },
    [slashCommand, executeCommand]
  );

  const handleSend = React.useCallback(() => {
    if (streaming) return;

    // If slash menu is open, handle selection
    if (showSlashMenu) {
      if (slashCommand && slashOptions.length > 0) {
        handleSelectOption(slashOptions[slashActiveIndex] || slashOptions[0]);
      } else {
        const filtered = filterCommands(slashQuery);
        if (filtered.length > 0) {
          handleSelectCommand(filtered[slashActiveIndex] || filtered[0]);
        }
      }
      return;
    }

    if (hasImageAttachment && !modelSupportsVision) {
      if (recommendedVisionModel && onModelChange) {
        toast.error(
          tx(
            `Mô hình "${effectiveModel?.display_name || effectiveModel?.name || "hiện tại"}" không hỗ trợ đọc ảnh. Vui lòng bấm "Đổi sang ${recommendedVisionModel.display_name || recommendedVisionModel.name}" hoặc chọn mô hình có Vision.`,
            `Model "${effectiveModel?.display_name || effectiveModel?.name || "selected"}" does not support images. Please click "Switch to ${recommendedVisionModel.display_name || recommendedVisionModel.name}" or select a Vision model.`
          )
        );
      } else {
        toast.error(
          tx(
            "Vui lòng chọn mô hình có hỗ trợ Vision (biểu tượng con mắt) hoặc gỡ ảnh đính kèm trước khi gửi.",
            "Please select a Vision-capable model (Eye icon) or remove the image attachment before sending."
          )
        );
      }
      return;
    }
    onSubmit();
  }, [
    streaming,
    showSlashMenu,
    slashCommand,
    slashOptions,
    slashActiveIndex,
    slashQuery,
    handleSelectOption,
    handleSelectCommand,
    hasImageAttachment,
    modelSupportsVision,
    recommendedVisionModel,
    onModelChange,
    effectiveModel,
    onSubmit,
    tx,
  ]);

  return (
    <div className={cn("relative rounded-xl border border-border bg-card shadow-card", variant === "floating" && "bg-card/80 backdrop-blur-md", className)}>
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 border-b border-border/60 p-2">
          {attachments.map((file) => (
            <FileAttachmentCard
              key={file.id}
              attachment={{
                id: file.id,
                name: file.original_name,
                size: file.size,
                content_type: file.content_type,
              }}
              variant="composer"
              onRemove={() => onAttachmentsChange(attachments.filter((f) => f.id !== file.id))}
            />
          ))}
        </div>
      )}

      {hasImageAttachment && !modelSupportsVision && (
        <div className="mx-2 mt-2 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs text-amber-700 dark:text-amber-300">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 text-amber-500" aria-hidden="true" />
            <span>
              {tx(
                `Mô hình "${effectiveModel?.display_name || effectiveModel?.name || "hiện tại"}" không hỗ trợ xử lý hình ảnh (Vision). Vui lòng chuyển sang mô hình có Vision để gửi ảnh.`,
                `Current model "${effectiveModel?.display_name || effectiveModel?.name || "selected"}" does not support image analysis (Vision). Please switch to a Vision-capable model.`
              )}
            </span>
          </div>
          {recommendedVisionModel && onModelChange && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-6 shrink-0 gap-1 border-amber-500/40 bg-amber-500/20 px-2 text-[11px] font-medium text-amber-900 hover:bg-amber-500/30 dark:text-amber-100"
              onClick={() => onModelChange(recommendedVisionModel.id)}
            >
              <Eye className="h-3 w-3" aria-hidden="true" />
              {tx(
                `Đổi sang ${recommendedVisionModel.display_name || recommendedVisionModel.name}`,
                `Switch to ${recommendedVisionModel.display_name || recommendedVisionModel.name}`
              )}
            </Button>
          )}
        </div>
      )}

      <label htmlFor="chat-composer" className="sr-only">{tx("Tin nhắn", "Message")}</label>
      <div className="relative">
        <Textarea
          id="chat-composer"
          ref={textareaRef}
          value={draft}
          onChange={(e) => {
            const value = e.target.value;
            onDraftChange(value);
            adjustHeight();

            // Detect slash command: find the word at cursor position
            const textarea = textareaRef.current;
            if (textarea) {
              const cursorPos = textarea.selectionStart || 0;
              const textBeforeCursor = value.slice(0, cursorPos);
              const lastSlashIndex = textBeforeCursor.lastIndexOf("/");
              const lastSpaceIndex = textBeforeCursor.lastIndexOf(" ");
              const lastNewlineIndex = textBeforeCursor.lastIndexOf("\n");

              // The token start is the char right after the last space/newline
              const tokenBoundary = Math.max(lastSpaceIndex, lastNewlineIndex);
              const inSlashToken = lastSlashIndex > tokenBoundary && textBeforeCursor.startsWith("/", lastSlashIndex);

              if (inSlashToken) {
                // We're inside a /token — keep the menu open and update the query
                const query = textBeforeCursor.slice(lastSlashIndex + 1);
                if (!query.includes(" ")) {
                  // Still typing the command name
                  if (!showSlashMenu) {
                    setShowSlashMenu(true);
                    setSlashActiveIndex(0);
                  }
                  setSlashQuery(query);
                  setSlashCommand(null);
                  setSlashOptions([]);
                } else {
                  // Command name typed, possibly entering args
                  const spaceIdx = query.indexOf(" ");
                  const cmdName = query.slice(0, spaceIdx);
                  const cmd = getCommand(cmdName);
                  if (cmd) {
                    const args = query.slice(spaceIdx + 1);
                    setSlashQuery(cmdName);
                    setSlashCommand(cmd);
                    setSlashActiveIndex(0);
                    if (cmd.getOptions) {
                      setSlashOptions(cmd.getOptions({
                        draft,
                        models: models || [],
                        effectiveModel,
                        executionPolicy,
                        onModelChange: onModelChange || (() => {}),
                        onExecutionPolicyChange: onExecutionPolicyChange || (() => {}),
                        onClear: onClear || (() => {}),
                        onReset: onReset || (() => {}),
                        onDraftChange,
                        tx,
                      }));
                    } else {
                      setSlashOptions([]);
                    }
                  } else {
                    closeSlashMenu();
                  }
                }
              } else if (showSlashMenu) {
                // Cursor moved outside any slash token
                closeSlashMenu();
              }
            }
          }}
          onKeyDown={(e) => {
            // Handle slash menu navigation
            if (showSlashMenu) {
              const items = slashCommand ? slashOptions : filterCommands(slashQuery);
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setSlashActiveIndex((prev) => Math.min(prev + 1, items.length - 1));
                return;
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setSlashActiveIndex((prev) => Math.max(prev - 1, 0));
                return;
              }
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
                return;
              }
              if (e.key === "Escape") {
                e.preventDefault();
                closeSlashMenu();
                return;
              }
            }

            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!streaming) handleSend();
            }
          }}
          placeholder={activePlaceholder}
          className="min-h-[48px] w-full resize-none border-none bg-transparent px-4 py-3 text-sm shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
          style={{ overflow: "hidden" }}
        />

        {showSlashMenu && (
          <SlashCommandMenu
            commands={slashCommand ? [] : filterCommands(slashQuery)}
            activeIndex={slashActiveIndex}
            options={slashOptions}
            showOptions={!!slashCommand}
            onSelectCommand={handleSelectCommand}
            onSelectOption={handleSelectOption}
            onClose={closeSlashMenu}
          />
        )}
      </div>

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
                  <span className="max-w-[4.5rem] sm:max-w-[8rem] md:max-w-[10rem] truncate font-mono">
                    {effectiveModel?.display_name || effectiveModel?.name || tx("Mô hình", "Model")}
                  </span>
                  {effectiveModel?.supports_vision && (
                    <span title={tx("Hỗ trợ Vision", "Vision supported")} className="flex items-center">
                      <Eye className="h-3 w-3 text-primary shrink-0" aria-hidden="true" />
                    </span>
                  )}
                  <ChevronDown className="h-3 w-3 opacity-60" aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-72">
                <DropdownMenuLabel>{tx("Mô hình AI", "Model")}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {models?.filter((m) => m.active).map((m) => (
                  <DropdownMenuItem
                    key={m.id}
                    onSelect={() => onModelChange(m.id)}
                    className={cn(
                      "flex items-center justify-between gap-2 py-1.5",
                      m.id === effectiveModel?.id && "font-semibold text-foreground bg-accent/40"
                    )}
                  >
                    <span className="flex-1 truncate">{m.display_name || m.name}</span>
                    <div className="flex items-center gap-1.5 shrink-0">
                      {m.supports_vision && (
                        <span className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[9px] font-medium bg-primary/10 text-primary border border-primary/20">
                          <Eye className="h-2.5 w-2.5" />
                          Vision
                        </span>
                      )}
                      <span className="text-[9px] uppercase tracking-wider text-muted-foreground/60">{m.tier}</span>
                    </div>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          <Button
            type="button"
            size="icon"
            onClick={streaming ? onStop : handleSend}
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
