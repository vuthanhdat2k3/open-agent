"use client";

import * as React from "react";
import { Bot, Bug, Trash2 } from "lucide-react";
import { useCurrentRole } from "@/hooks";
import { isAdminRole, isOperator } from "@/lib/roles";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { ChatMessageItem } from "@/components/chat/chat-message-item";
import { ChatEmptyState } from "@/components/chat/chat-empty-state";
import { ChatStatusRow } from "@/components/chat/chat-status-row";
import { ChatHeaderControls } from "@/components/chat/chat-header-controls";
import type { ChatMessage } from "@/lib/chat/projection";
import type { Agent, ExecutionPolicy, Model, Session, UploadedFile } from "@/types";
import { useTranslation } from "@/lib/i18n";

interface ChatThreadProps {
  messages: ChatMessage[];
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
  pendingExecutionPolicy: ExecutionPolicy;
  updateAgentPending: boolean;
  onAgentChange: (agentId: string) => void;
  onDefaultModelChange: (modelId: string) => void;
  onExecutionPolicyChange: (policy: ExecutionPolicy) => void;
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
  pendingExecutionPolicy,
  updateAgentPending,
  onAgentChange,
  onDefaultModelChange,
  onExecutionPolicyChange,
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
    const { locale, tx } = useTranslation();
  const hasPendingApproval = messages.some((m) => m.role === "approval" && m.status === "pending");
  const lastMessage = messages[messages.length - 1];
  // Hide the global ChatStatusRow when the last assistant message is already
  // showing a loading indicator inline — either a streaming text/reasoning block,
  // or a tool_call chip that is still "running".  Both render their own spinner,
  // so showing the status row on top would result in two loading indicators.
  const inMessageStreaming =
    lastMessage?.role === "assistant" &&
    lastMessage.blocks.some(
      (b) =>
        (b.kind === "text" || b.kind === "reasoning") && "streaming" in b && b.streaming ||
        (b.kind === "tool_call" && b.status === "running"),
    );
  const showStatusRow =
    (streaming || statusPhase === "approval") && !hasPendingApproval && !inMessageStreaming;

  const role = useCurrentRole();
  const canSwitchAgent = isAdminRole(role) || isOperator(role);
  const canSwitchModel = Boolean(models?.some((model) => model.active));

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="sticky top-0 z-10 flex shrink-0 items-center gap-2 border-b border-border/60 bg-background px-2 py-1.5 sm:px-4">
        <ChatHeaderControls
          canSwitchAgent={canSwitchAgent}
          canSwitchModel={canSwitchModel}
          agents={agents}
          models={models}
          sessions={sessions}
          agentId={agentId}
          sessionId={sessionId}
          currentAgent={currentAgent}
          currentAgentModel={currentAgentModel}
          pendingSessionModelId={pendingSessionModelId}
          pendingExecutionPolicy={pendingExecutionPolicy}
          streaming={streaming}
          updateAgentPending={updateAgentPending}
          onAgentChange={onAgentChange}
          onDefaultModelChange={onDefaultModelChange}
          onExecutionPolicyChange={onExecutionPolicyChange}
          onSessionChange={onSessionChange}
          onNewSession={onNewSession}
          onDeleteSession={onDeleteSession}
          canUseFullAccess={isAdminRole(role) || isOperator(role)}
        />
        <div className="ml-auto flex items-center gap-1">
          <Button
            type="button"
            variant={debug ? "secondary" : "ghost"}
            size="sm"
            className={`h-7 gap-1 px-2 text-[10px] transition-colors ${
              debug
                ? "bg-secondary font-semibold text-primary shadow-sm border border-primary/30"
                : "text-muted-foreground hover:text-foreground"
            }`}
            onClick={onToggleDebug}
            aria-pressed={debug}
            title={
              debug
                ? tx("Chế độ Debug đang BẬT (mở rộng thẻ tool, đếm token & timing chính xác). Bấm để chuyển sang chế độ Clean.", "Debug mode is ON (expanded tool cards, exact token counts & timings). Click to switch to Clean mode.")
                : tx("Chế độ Debug đang TẮT (chip tool gọn & văn bản sạch). Bấm để bật chế độ Debug.", "Debug mode is OFF (compact tool chips & clean text). Click to enable Debug mode.")
            }
          >
            <Bug className={`h-3.5 w-3.5 ${debug ? "text-primary" : ""}`} aria-hidden="true" />
            <span>{tx("Debug", "Debug")}</span>
            {debug && <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden="true" />}
          </Button>
          {messages.length > 0 && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-muted-foreground hover:text-destructive"
              onClick={onClearMessages}
              aria-label={tx("Xóa hội thoại", "Clear conversation")}
              title={tx("Xóa hội thoại", "Clear conversation")}
            >
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
        className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 sm:p-6"
      >
        {messages.length === 0 ? (
          <ChatEmptyState
            currentAgent={currentAgent}
            models={models}
            effectiveModel={effectiveModel}
            onModelChange={onDefaultModelChange}
            executionPolicy={pendingExecutionPolicy}
            onExecutionPolicyChange={onExecutionPolicyChange}
            draft={draft}
            onDraftChange={onDraftChange}
            onSubmit={onSubmit}
            disabled={composerDisabled}
            attachments={attachments}
            onAttachmentsChange={onAttachmentsChange}
          />
        ) : (
          <div className="mx-auto flex w-full max-w-[var(--dsh-chat-content-width,736px)] flex-1 flex-col gap-4">
            {messages.map((m) => (
              <ChatMessageItem
                key={m.id}
                message={m}
                debug={debug}
                onApprovalDecision={onApprovalDecision}
              />
            ))}
            {showStatusRow && (
              <div className="flex w-full max-w-[92%] items-start gap-2.5 self-start">
                <Avatar className="mt-0.5 h-7 w-7 shrink-0 border border-border bg-muted">
                  <AvatarFallback className="bg-transparent text-foreground">
                    <Bot className="h-3.5 w-3.5 animate-pulse" aria-hidden="true" />
                  </AvatarFallback>
                </Avatar>
                <ChatStatusRow statusPhase={statusPhase} effectiveModel={effectiveModel} />
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  );
}
