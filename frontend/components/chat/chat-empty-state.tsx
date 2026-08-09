"use client";

import { FolderSearch, ListTodo, Sparkles } from "lucide-react";
import { ChatComposer } from "@/components/chat/chat-composer";
import type { Agent, Model, UploadedFile } from "@/types";

interface ChatEmptyStateProps {
  currentAgent?: Agent;
  effectiveModel?: Model;
  draft: string;
  onDraftChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  attachments: UploadedFile[];
  onAttachmentsChange: (files: UploadedFile[]) => void;
}

const QUICK_ACTIONS = [
  { icon: FolderSearch, label: "List recent files", prompt: "List the 5 most recently modified files I have access to." },
  { icon: ListTodo, label: "Summarize my day", prompt: "Summarize what needs my attention today." },
  { icon: Sparkles, label: "What can you do?", prompt: "What can you help me with?" },
];

// Adapted from RuixenMoonChat (21st.dev / ruixen.ui): a moon-glow backdrop, a
// heading block that floats in the upper area (flex-1), and a composer +
// quick-action pills grouped together near the bottom (not pinned to the
// edge). The composer is the same ChatComposer used once a conversation is
// active, so attach/send behave identically in both states.
export function ChatEmptyState({ currentAgent, effectiveModel, draft, onDraftChange, onSubmit, disabled, attachments, onAttachmentsChange }: ChatEmptyStateProps) {
  return (
    <div className="relative m-auto flex min-h-0 w-full flex-1 flex-col items-center overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10"
        style={{
          background:
            "radial-gradient(38rem 26rem at 50% 18%, hsl(var(--foreground) / 0.10), transparent 65%), radial-gradient(60rem 40rem at 50% 120%, hsl(var(--foreground) / 0.06), transparent 60%)",
        }}
      />

      <div className="flex w-full flex-1 flex-col items-center justify-center text-center">
        <h2 className="text-balance text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
          {currentAgent?.name ?? "OpenAgent"}
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Build something amazing — just start typing below.
          {effectiveModel && <span className="ml-1 font-mono text-xs text-foreground/60">({effectiveModel.display_name || effectiveModel.name})</span>}
        </p>
      </div>

      <div className="mb-[14vh] w-full max-w-2xl px-4">
        <ChatComposer
          draft={draft}
          onDraftChange={onDraftChange}
          onSubmit={onSubmit}
          disabled={disabled}
          attachments={attachments}
          onAttachmentsChange={onAttachmentsChange}
          variant="floating"
          placeholder="Type your request…"
        />

        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
          {QUICK_ACTIONS.map(({ icon: Icon, label, prompt }) => (
            <button
              key={label}
              type="button"
              onClick={() => onDraftChange(prompt)}
              className="active-tactile inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3.5 py-1.5 text-xs font-medium text-muted-foreground shadow-inner-edge transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
