"use client";

import { ChatComposer } from "@/components/chat/chat-composer";
import { ChatConnectionBanner, type ConnectionState } from "@/components/chat/chat-connection-banner";
import type { UploadedFile } from "@/types";

interface ChatInputProps {
  draft: string;
  onDraftChange: (value: string) => void;
  onSubmit: () => void;
  streaming: boolean;
  disabled: boolean;
  connectionState: ConnectionState;
  attachments: UploadedFile[];
  onAttachmentsChange: (files: UploadedFile[]) => void;
}

// Docked composer for an active conversation. `onSubmit` arrives already
// resolved by the page (stop while streaming, send otherwise) — passed
// through as both onSubmit/onStop since ChatComposer just picks the right
// one based on `streaming`.
export function ChatInput({ draft, onDraftChange, onSubmit, streaming, disabled, connectionState, attachments, onAttachmentsChange }: ChatInputProps) {
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
      />
    </div>
  );
}
