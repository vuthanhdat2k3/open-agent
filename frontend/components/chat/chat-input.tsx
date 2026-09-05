"use client";

import { ChatComposer } from "@/components/chat/chat-composer";
import { ChatConnectionBanner, type ConnectionState } from "@/components/chat/chat-connection-banner";
import type { Agent, Model, ExecutionPolicy, UploadedFile, UsageSummary } from "@/types";
import type { ChatMessage } from "@/lib/chat/projection";

interface ChatInputProps {
  draft: string;
  onDraftChange: (value: string) => void;
  onSubmit: () => void;
  streaming: boolean;
  disabled: boolean;
  connectionState: ConnectionState;
  attachments: UploadedFile[];
  onAttachmentsChange: (files: UploadedFile[]) => void;
  models?: Model[];
  effectiveModel?: Model;
  onModelChange: (modelId: string) => void;
  executionPolicy: ExecutionPolicy;
  onExecutionPolicyChange: (policy: ExecutionPolicy) => void;
  onClear?: () => void;
  onReset?: () => void;
  agents?: Agent[];
  currentAgentId?: string;
  onAgentChange?: (agentId: string) => void;
  usage?: UsageSummary[];
  onSendMessage?: (message: string) => void;
  sessionId?: string;
  messages?: ChatMessage[];
}

// Docked composer for an active conversation. `onSubmit` arrives already
// resolved by the page (stop while streaming, send otherwise) — passed
// through as both onSubmit/onStop since ChatComposer just picks the right
// one based on `streaming`.
export function ChatInput({
  draft, onDraftChange, onSubmit, streaming, disabled, connectionState, attachments, onAttachmentsChange,
  models, effectiveModel, onModelChange, executionPolicy, onExecutionPolicyChange, onClear, onReset,
  agents, currentAgentId, onAgentChange, usage, onSendMessage, sessionId
}: ChatInputProps) {
  return (
    <div className="mt-3">
      <ChatConnectionBanner state={connectionState} />
      <ChatComposer
        draft={draft}
        onDraftChange={onDraftChange}
        onSubmit={onSubmit}
        disabled={disabled}
        streaming={streaming}
        onStop={onSubmit}
        attachments={attachments}
        onAttachmentsChange={onAttachmentsChange}
        variant="docked"
        models={models}
        effectiveModel={effectiveModel}
        onModelChange={onModelChange}
        executionPolicy={executionPolicy}
        onExecutionPolicyChange={onExecutionPolicyChange}
        onClear={onClear}
        onReset={onReset}
        agents={agents}
        currentAgentId={currentAgentId}
        onAgentChange={onAgentChange}
        usage={usage}
        onSendMessage={onSendMessage}
        sessionId={sessionId}
      />
    </div>
  );
}
