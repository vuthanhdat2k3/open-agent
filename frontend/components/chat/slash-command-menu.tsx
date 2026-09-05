"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import {
  Cpu,
  Sliders,
  ShieldCheck,
  Bot,
  Sparkles,
  Info,
  BarChart2,
  Trash2,
  RotateCcw,
  HelpCircle,
  CornerDownLeft,
  ChevronRight,
  Sparkle,
} from "lucide-react";
import type { SlashCommand, SlashCommandOption } from "./commands/types";

interface SlashCommandMenuProps {
  /** Filtered commands to show */
  commands: SlashCommand[];
  /** Currently highlighted index */
  activeIndex: number;
  /** Callback to set highlighted index on mouse enter */
  onHighlightIndex?: (index: number) => void;
  /** Command options (for commands with autocomplete) */
  options: SlashCommandOption[];
  /** Whether to show options list */
  showOptions: boolean;
  /** Callback when command is selected */
  onSelectCommand: (command: SlashCommand) => void;
  /** Callback when option is selected */
  onSelectOption: (option: SlashCommandOption) => void;
  /** Callback to close menu */
  onClose: () => void;
}

export function SlashCommandMenu({
  commands,
  activeIndex,
  onHighlightIndex,
  options,
  showOptions,
  onSelectCommand,
  onSelectOption,
  onClose,
}: SlashCommandMenuProps) {
  const { tx } = useTranslation();
  const menuRef = React.useRef<HTMLDivElement>(null);
  const itemRefs = React.useRef<(HTMLButtonElement | null)[]>([]);

  // Keep itemRefs length in sync
  React.useEffect(() => {
    itemRefs.current = itemRefs.current.slice(0, showOptions ? options.length : commands.length);
  }, [showOptions, options.length, commands.length]);

  // Auto-scroll the active item into view when navigating with arrow keys
  React.useEffect(() => {
    const el = itemRefs.current[activeIndex];
    if (el) {
      el.scrollIntoView({
        block: "nearest",
        behavior: "smooth",
      });
    }
  }, [activeIndex]);

  // Close on click outside
  React.useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [onClose]);

  // Close on Escape
  React.useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const getCommandIcon = (icon?: string) => {
    switch (icon) {
      case "cpu":
        return <Cpu className="h-3.5 w-3.5 text-blue-500" />;
      case "sliders":
        return <Sliders className="h-3.5 w-3.5 text-indigo-500" />;
      case "shield":
        return <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />;
      case "bot":
        return <Bot className="h-3.5 w-3.5 text-purple-500" />;
      case "sparkles":
        return <Sparkles className="h-3.5 w-3.5 text-amber-500" />;
      case "info":
        return <Info className="h-3.5 w-3.5 text-sky-500" />;
      case "chart":
        return <BarChart2 className="h-3.5 w-3.5 text-teal-500" />;
      case "trash":
        return <Trash2 className="h-3.5 w-3.5 text-rose-500" />;
      case "rotate":
        return <RotateCcw className="h-3.5 w-3.5 text-orange-500" />;
      case "help":
      default:
        return <HelpCircle className="h-3.5 w-3.5 text-violet-500" />;
    }
  };

  // Sub-options list (e.g., choosing a model or policy)
  if (showOptions && options.length > 0) {
    return (
      <div
        ref={menuRef}
        className="absolute bottom-full left-0 right-0 mb-2 max-h-72 overflow-hidden flex flex-col rounded-xl border border-border/80 bg-card/95 backdrop-blur-md shadow-2xl ring-1 ring-black/5 dark:ring-white/10 z-30 animate-in fade-in-0 zoom-in-95 duration-150"
      >
        <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/40 bg-muted/30 text-[11px] font-medium text-muted-foreground">
          <span>{tx("Chọn một tùy chọn:", "Select an option:")}</span>
          <span>{options.length} {tx("lựa chọn", "options")}</span>
        </div>

        <div className="overflow-y-auto p-1.5 space-y-0.5 max-h-56">
          {options.map((option, idx) => {
            const isActive = idx === activeIndex;
            return (
              <button
                key={option.id}
                ref={(el) => { itemRefs.current[idx] = el; }}
                type="button"
                className={cn(
                  "w-full flex items-center justify-between gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors",
                  isActive
                    ? "bg-primary/10 text-foreground font-medium ring-1 ring-primary/25"
                    : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"
                )}
                onMouseEnter={() => onHighlightIndex?.(idx)}
                onClick={() => onSelectOption(option)}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <div className={cn(
                    "flex h-5 w-5 shrink-0 items-center justify-center rounded-md border",
                    isActive ? "border-primary/40 bg-primary/20 text-primary" : "border-border/60 bg-muted/60"
                  )}>
                    <ChevronRight className="h-3 w-3" />
                  </div>
                  <span className="truncate">{option.label}</span>
                </div>
                {option.detail && (
                  <span className="shrink-0 text-[10px] text-muted-foreground/70 font-mono bg-muted/50 px-1.5 py-0.5 rounded border border-border/30">
                    {option.detail}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex items-center justify-between px-3 py-1.5 border-t border-border/40 bg-muted/20 text-[10px] text-muted-foreground">
          <div className="flex items-center gap-2">
            <span><kbd className="px-1 rounded bg-muted border border-border/60 text-[9px] font-mono">↑↓</kbd> {tx("di chuyển", "navigate")}</span>
            <span><kbd className="px-1 rounded bg-muted border border-border/60 text-[9px] font-mono">↵ / Tab</kbd> {tx("chọn", "select")}</span>
          </div>
          <span><kbd className="px-1 rounded bg-muted border border-border/60 text-[9px] font-mono">Esc</kbd> {tx("đóng", "close")}</span>
        </div>
      </div>
    );
  }

  // No commands found
  if (commands.length === 0) {
    return (
      <div
        ref={menuRef}
        className="absolute bottom-full left-0 right-0 mb-2 rounded-xl border border-border/80 bg-card/95 backdrop-blur-md p-3.5 shadow-2xl z-30 animate-in fade-in-0 zoom-in-95 duration-150"
      >
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Sparkle className="h-3.5 w-3.5 text-muted-foreground/60" />
          <span>{tx("Không tìm thấy lệnh phù hợp. Nhấn Esc để đóng.", "No matching commands found. Press Esc to dismiss.")}</span>
        </div>
      </div>
    );
  }

  // Commands list
  return (
    <div
      ref={menuRef}
      className="absolute bottom-full left-0 right-0 mb-2 max-h-72 overflow-hidden flex flex-col rounded-xl border border-border/80 bg-card/95 backdrop-blur-md shadow-2xl ring-1 ring-black/5 dark:ring-white/10 z-30 animate-in fade-in-0 zoom-in-95 duration-150"
    >
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border/40 bg-muted/30 text-[11px] font-medium text-muted-foreground">
        <span>{tx("Lệnh nhanh:", "Slash Commands:")}</span>
        <span>{commands.length} {tx("lệnh", "commands")}</span>
      </div>

      <div className="overflow-y-auto p-1.5 space-y-0.5 max-h-56">
        {commands.map((cmd, idx) => {
          const isActive = idx === activeIndex;
          return (
            <button
              key={cmd.name}
              ref={(el) => { itemRefs.current[idx] = el; }}
              type="button"
              className={cn(
                "w-full flex items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-left transition-colors group",
                isActive
                  ? "bg-primary/10 text-foreground ring-1 ring-primary/25"
                  : "hover:bg-muted/70 text-muted-foreground hover:text-foreground"
              )}
              onMouseEnter={() => onHighlightIndex?.(idx)}
              onClick={() => onSelectCommand(cmd)}
            >
              <div className="flex items-center gap-2.5 min-w-0 flex-1">
                <div className={cn(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border transition-colors",
                  isActive ? "border-primary/40 bg-primary/15" : "border-border/60 bg-muted/50 group-hover:bg-muted"
                )}>
                  {getCommandIcon(cmd.icon)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="shrink-0 font-mono text-xs font-bold text-primary">
                      /{cmd.name}
                    </span>
                    <span className="truncate text-xs font-medium text-foreground">
                      {cmd.description}
                    </span>
                  </div>
                  {cmd.usage && (
                    <p className="mt-0.5 text-[10px] text-muted-foreground/60 font-mono truncate">
                      {cmd.usage}
                    </p>
                  )}
                </div>
              </div>

              {isActive && (
                <div className="shrink-0 flex items-center gap-1 text-[10px] font-mono text-primary/80">
                  <span>Enter</span>
                  <CornerDownLeft className="h-2.5 w-2.5" />
                </div>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex items-center justify-between px-3 py-1.5 border-t border-border/40 bg-muted/20 text-[10px] text-muted-foreground">
        <div className="flex items-center gap-2.5">
          <span><kbd className="px-1 rounded bg-muted border border-border/60 text-[9px] font-mono">↑↓</kbd> {tx("di chuyển", "navigate")}</span>
          <span><kbd className="px-1 rounded bg-muted border border-border/60 text-[9px] font-mono">↵ / Tab</kbd> {tx("chọn", "select")}</span>
        </div>
        <span><kbd className="px-1 rounded bg-muted border border-border/60 text-[9px] font-mono">Esc</kbd> {tx("đóng", "close")}</span>
      </div>
    </div>
  );
}
