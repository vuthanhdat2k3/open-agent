"use client";

import { ChatComposer } from "@/components/chat/chat-composer";
import { ChatConnectionBanner, type ConnectionState } from "@/components/chat/chat-connection-banner";
import type { Model, ExecutionPolicy, UploadedFile } from "@/types";

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
}

// Docked composer for an active conversation. `onSubmit` arrives already
// resolved by the page (stop while streaming, send otherwise) — passed
// through as both onSubmit/onStop since ChatComposer just picks the right
// one based on `streaming`.
export function ChatInput({ 
  draft, onDraftChange, onSubmit, streaming, disabled, connectionState, attachments, onAttachmentsChange,
  models, effectiveModel, onModelChange, executionPolicy, onExecutionPolicyChange
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
      />
    </div>
  );
}
