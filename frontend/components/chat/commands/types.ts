import type { Agent, ExecutionPolicy, Model, UsageSummary } from "@/types";

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
  /** Available agents */
  agents: Agent[];
  /** Current agent id */
  currentAgentId: string | undefined;
  /** Usage summary rows (per agent/model) */
  usage: UsageSummary[];
  /** Callback to switch model */
  onModelChange: (modelId: string) => void;
  /** Callback to switch execution policy */
  onExecutionPolicyChange: (policy: ExecutionPolicy) => void;
  /** Callback to clear conversation history */
  onClear: () => void;
  /** Callback to reset session (new conversation) */
  onReset: () => void;
  /** Callback to switch agent */
  onAgentChange: (agentId: string) => void;
  /** Callback to send a message programmatically (for /compact) */
  onSend: (message: string) => void;
  /** Callback to set draft text */
  onDraftChange: (draft: string) => void;
  /** Toast-like notification */
  notify: (message: string, kind?: "success" | "error" | "info") => void;
  /** Translation function */
  tx: (vietnamese: string, english: string) => string;
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
