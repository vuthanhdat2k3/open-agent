"use client";

import * as React from "react";
import { Bug, MessageSquare, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChatMessageItem, type UIMessage } from "@/components/chat/chat-message-item";
import { ChatEmptyState } from "@/components/chat/chat-empty-state";
import { ChatStatusRow } from "@/components/chat/chat-status-row";
import type { Agent, Model } from "@/types";

interface ChatThreadProps {
  messages: UIMessage[];
  debug: boolean;
  streaming: boolean;
  statusPhase: string;
  currentAgent?: Agent;
  effectiveModel?: Model;
  onToggleDebug: () => void;
  onClearMessages: () => void;
  onApprovalDecision: (messageId: string, decision: "approved" | "rejected") => void;
  scrollHostRef: React.RefObject<HTMLDivElement | null>;
  bottomRef: React.RefObject<HTMLDivElement | null>;
  onThreadScroll: () => void;
}

// Presentation-only thread surface. All streaming state (messages array,
// statusPhase, refs for scroll tracking) is owned and mutated by the page;
// this component only renders what it is given.
export function ChatThread({
  messages,
  debug,
  streaming,
  statusPhase,
  currentAgent,
  effectiveModel,
  onToggleDebug,
  onClearMessages,
  onApprovalDecision,
  scrollHostRef,
  bottomRef,
  onThreadScroll,
}: ChatThreadProps) {
  const hasLiveTools = messages.some((m) => m.role === "tool_call" || m.role === "tool_result");
  const hasPendingApproval = messages.some((m) => m.role === "approval" && m.meta?.approvalStatus === "pending");

  return (
    <Card glass className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <CardHeader className="flex flex-row items-center gap-3 space-y-0 border-b border-border/80 bg-muted/20 px-4 py-3">
        <div className="grid h-8 w-8 place-items-center rounded-xl border border-primary/25 bg-primary/10 text-primary shadow-inner-edge">
          <MessageSquare className="h-4 w-4" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1">
          <CardTitle className="text-sm font-semibold tracking-tight">Conversation Thread</CardTitle>
          {currentAgent && (
            <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
              {currentAgent.name}
              {effectiveModel && <span className="text-muted-foreground/60"> · {effectiveModel.display_name || effectiveModel.name}</span>}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1">
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
            <Button type="button" variant="ghost" size="icon" className="h-10 w-10 text-muted-foreground hover:text-destructive" onClick={onClearMessages} aria-label="Clear conversation" title="Clear conversation">
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent ref={scrollHostRef} onScroll={onThreadScroll} className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <ChatEmptyState currentAgent={currentAgent} effectiveModel={effectiveModel} />
        ) : (
          <>
            {messages.map((m) => (
              <ChatMessageItem key={m.id} message={m} debug={debug} hasLiveTools={hasLiveTools} onApprovalDecision={onApprovalDecision} />
            ))}
            {(streaming || statusPhase === "approval") && !hasPendingApproval && (
              <ChatStatusRow statusPhase={statusPhase} effectiveModel={effectiveModel} />
            )}
            <div ref={bottomRef} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
