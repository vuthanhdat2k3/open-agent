"use client";

import * as React from "react";
import { Bug, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatMessageItem, type UIMessage } from "@/components/chat/chat-message-item";
import { ChatEmptyState } from "@/components/chat/chat-empty-state";
import { ChatStatusRow } from "@/components/chat/chat-status-row";
import { ChatHeaderControls } from "@/components/chat/chat-header-controls";
import type { Agent, Model, Session, UploadedFile } from "@/types";

interface ChatThreadProps {
  messages: UIMessage[];
  debug: boolean;
  streaming: boolean;
  statusPhase: string;
  agents?: Agent[];
  models?: Model[];
  sessions?: Session[];
  agentId: string | null;
  sessionId: string | null;
  currentAgent?: Agent;
  currentAgentModel?: Model;
  effectiveModel?: Model;
  pendingSessionModelId: string;
  updateAgentPending: boolean;
  onAgentChange: (agentId: string) => void;
  onDefaultModelChange: (modelId: string) => void;
  onSessionChange: (sessionId: string) => void;
  onNewSession: () => void;
  onDeleteSession: (sessionId: string) => Promise<void>;
  onToggleDebug: () => void;
  onClearMessages: () => void;
  onApprovalDecision: (messageId: string, decision: "approved" | "rejected") => void;
  draft: string;
  onDraftChange: (value: string) => void;
  onSubmit: () => void;
  composerDisabled: boolean;
  attachments: UploadedFile[];
  onAttachmentsChange: (files: UploadedFile[]) => void;
  scrollHostRef: React.RefObject<HTMLDivElement | null>;
  bottomRef: React.RefObject<HTMLDivElement | null>;
  onThreadScroll: () => void;
}

// Full-bleed thread surface (no card chrome — the page itself is the
// surface now, matching the moon-chat full-screen aesthetic). Agent/model/
// session switching lives inline in the header (ChatHeaderControls) instead
// of a sidebar column. All streaming state is owned and mutated by the
// page; this component only renders what it is given.
export function ChatThread({
  messages,
  debug,
  streaming,
  statusPhase,
  agents,
  models,
  sessions,
  agentId,
  sessionId,
  currentAgent,
  currentAgentModel,
  effectiveModel,
  pendingSessionModelId,
  updateAgentPending,
  onAgentChange,
  onDefaultModelChange,
  onSessionChange,
  onNewSession,
  onDeleteSession,
  onToggleDebug,
  onClearMessages,
  onApprovalDecision,
  draft,
  onDraftChange,
  onSubmit,
  composerDisabled,
  attachments,
  onAttachmentsChange,
  scrollHostRef,
  bottomRef,
  onThreadScroll,
}: ChatThreadProps) {
  const hasLiveTools = messages.some((m) => m.role === "tool_call" || m.role === "tool_result");
  const hasPendingApproval = messages.some((m) => m.role === "approval" && m.meta?.approvalStatus === "pending");

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="sticky top-0 z-10 flex shrink-0 items-center gap-2 border-b border-border/60 bg-background px-2 py-1.5 sm:px-4">
        <ChatHeaderControls
          agents={agents}
          models={models}
          sessions={sessions}
          agentId={agentId}
          sessionId={sessionId}
          currentAgent={currentAgent}
          currentAgentModel={currentAgentModel}
          pendingSessionModelId={pendingSessionModelId}
          streaming={streaming}
          updateAgentPending={updateAgentPending}
          onAgentChange={onAgentChange}
          onDefaultModelChange={onDefaultModelChange}
          onSessionChange={onSessionChange}
          onNewSession={onNewSession}
          onDeleteSession={onDeleteSession}
        />
        <div className="ml-auto flex items-center gap-1">
          <Button
            type="button"
            variant={debug ? "secondary" : "ghost"}
            size="sm"
            className={`h-7 gap-1 px-2 text-[10px] ${debug ? "font-semibold text-primary" : "text-muted-foreground"}`}
            onClick={onToggleDebug}
            title="Toggle debug trace (thinking, tool calls, results)"
          >
            <Bug className="h-3.5 w-3.5" aria-hidden="true" /> Debug
          </Button>
          {messages.length > 0 && (
            <Button type="button" variant="ghost" size="icon" className="h-8 w-8 text-muted-foreground hover:text-destructive" onClick={onClearMessages} aria-label="Clear conversation" title="Clear conversation">
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          )}
        </div>
      </div>

      <div
        ref={scrollHostRef}
        onScroll={onThreadScroll}
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4 sm:p-6"
      >
        {messages.length === 0 ? (
          <ChatEmptyState
            currentAgent={currentAgent}
            effectiveModel={effectiveModel}
            draft={draft}
            onDraftChange={onDraftChange}
            onSubmit={onSubmit}
            disabled={composerDisabled}
            attachments={attachments}
            onAttachmentsChange={onAttachmentsChange}
          />
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-3">
            {messages.map((m) => (
              <ChatMessageItem key={m.id} message={m} debug={debug} hasLiveTools={hasLiveTools} onApprovalDecision={onApprovalDecision} />
            ))}
            {(streaming || statusPhase === "approval") && !hasPendingApproval && (
              <ChatStatusRow statusPhase={statusPhase} effectiveModel={effectiveModel} />
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  );
}
