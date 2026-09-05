import type { Model, ExecutionPolicy } from "@/types";

/** Context passed to slash command handlers */
export interface SlashCommandContext {
  /** Current draft text */
  draft: string;
  /** Available models */
  models: Model[];
  /** Current effective model */
  effectiveModel: Model | undefined;
  /** Current execution policy */
  executionPolicy: ExecutionPolicy | undefined;
  /** Callback to switch model */
  onModelChange: (modelId: string) => void;
  /** Callback to switch execution policy */
  onExecutionPolicyChange: (policy: ExecutionPolicy) => void;
  /** Callback to clear conversation */
  onClear: () => void;
  /** Callback to reset session */
  onReset: () => void;
  /** Callback to set draft text */
  onDraftChange: (draft: string) => void;
  /** Translation function */
  t: (vietnamese: string, english: string) => string;
}

/** One slash command definition */
export interface SlashCommand {
  /** Command name without the leading slash */
  readonly name: string;
  /** Short description shown in menu */
  readonly description: string;
  /** Optional usage hint */
  readonly usage?: string;
  /** Whether this command needs arguments */
  readonly requiresArgs?: boolean;
  /** Get autocomplete options for this command (optional) */
  getOptions?: (ctx: SlashCommandContext) => SlashCommandOption[];
  /** Execute the command. Returns true if menu should close. */
  execute: (args: string, ctx: SlashCommandContext) => boolean | Promise<boolean>;
}

/** One option in a command's autocomplete popup */
export interface SlashCommandOption {
  readonly id: string;
  readonly label: string;
  readonly detail?: string;
}

/** Parsed slash command from input */
export interface ParsedSlashCommand {
  /** Full command text including slash */
  raw: string;
  /** Command name */
  name: string;
  /** Arguments after command name */
  args: string;
  /** Cursor position in the input */
  cursorPos: number;
}
