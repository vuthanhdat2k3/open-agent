"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { SlashCommand, SlashCommandOption } from "./commands/types";

interface SlashCommandMenuProps {
  /** Filtered commands to show */
  commands: SlashCommand[];
  /** Currently highlighted index */
  activeIndex: number;
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
  options,
  showOptions,
  onSelectCommand,
  onSelectOption,
  onClose,
}: SlashCommandMenuProps) {
  const menuRef = React.useRef<HTMLDivElement>(null);

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

  if (showOptions && options.length > 0) {
    return (
      <div
        ref={menuRef}
        className="absolute bottom-full left-0 right-0 mb-1 max-h-64 overflow-y-auto rounded-lg border border-border bg-card shadow-lg"
      >
        <div className="p-1">
          {options.map((option, idx) => (
            <button
              key={option.id}
              type="button"
              className={cn(
                "w-full flex items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                idx === activeIndex ? "bg-primary/10 text-foreground" : "text-muted-foreground hover:bg-muted"
              )}
              onClick={() => onSelectOption(option)}
            >
              <span className="truncate font-medium">{option.label}</span>
              {option.detail && (
                <span className="shrink-0 text-[10px] text-muted-foreground/60">{option.detail}</span>
              )}
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (commands.length === 0) {
    return (
      <div
        ref={menuRef}
        className="absolute bottom-full left-0 right-0 mb-1 rounded-lg border border-border bg-card p-3 shadow-lg"
      >
        <p className="text-xs text-muted-foreground">Không tìm thấy lệnh. Nhấn Esc để đóng.</p>
      </div>
    );
  }

  return (
    <div
      ref={menuRef}
      className="absolute bottom-full left-0 right-0 mb-1 max-h-64 overflow-y-auto rounded-lg border border-border bg-card shadow-lg"
    >
      <div className="p-1">
        {commands.map((cmd, idx) => (
          <button
            key={cmd.name}
            type="button"
            className={cn(
              "w-full flex items-start justify-between gap-2 rounded-md px-3 py-2 text-left transition-colors",
              idx === activeIndex ? "bg-primary/10" : "hover:bg-muted"
            )}
            onClick={() => onSelectCommand(cmd)}
          >
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="shrink-0 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-mono font-semibold text-primary">
                  /{cmd.name}
                </span>
                <span className="truncate text-sm text-foreground">{cmd.description}</span>
              </div>
              {cmd.usage && (
                <p className="mt-0.5 pl-1 text-[10px] text-muted-foreground/60">{cmd.usage}</p>
              )}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
