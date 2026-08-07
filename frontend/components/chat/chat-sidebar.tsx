"use client";

import * as React from "react";
import { Bot, Cpu, MessageSquare, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ConfirmDialog } from "@/components/shared";
import type { Agent, Model, Session } from "@/types";

interface ChatSidebarProps {
  agents?: Agent[];
  models?: Model[];
  sessions?: Session[];
  agentId: string | null;
  sessionId: string | null;
  currentAgentModel?: Model;
  pendingSessionModelId: string;
  streaming: boolean;
  updateAgentPending: boolean;
  onAgentChange: (agentId: string) => void;
  onDefaultModelChange: (modelId: string) => void;
  onSessionChange: (sessionId: string) => void;
  onNewSession: () => void;
  onDeleteSession: (sessionId: string) => Promise<void>;
}

// Pure presentation: all data comes from props, all mutation goes back
// through the callbacks the page already implements (send/stop/session
// switching, model updates). No fetching or SSE logic lives here.
export function ChatSidebar({
  agents,
  models,
  sessions,
  agentId,
  sessionId,
  currentAgentModel,
  pendingSessionModelId,
  streaming,
  updateAgentPending,
  onAgentChange,
  onDefaultModelChange,
  onSessionChange,
  onNewSession,
  onDeleteSession,
}: ChatSidebarProps) {
  const agentSessions = sessions?.filter((s) => s.agent_id === agentId) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="space-y-4 rounded-xl border border-border/80 bg-card/50 p-4 shadow-card backdrop-blur-xl">
        <div className="space-y-1.5">
          <Label htmlFor="chat-agent" className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
            <Bot className="h-3.5 w-3.5 text-primary" aria-hidden="true" /> Active Agent
          </Label>
          <Select id="chat-agent" name="agent_id" value={agentId ?? ""} onChange={(e) => onAgentChange(e.target.value)} className="w-full text-xs">
            {agents?.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </Select>
          {currentAgentModel && (
            <div className="mt-1 flex items-center gap-1.5 rounded-md border border-border/30 bg-muted/30 px-2 py-1">
              <Cpu className="h-3 w-3 shrink-0 text-primary/70" aria-hidden="true" />
              <span className="truncate text-[10px] font-mono text-muted-foreground">
                {currentAgentModel.display_name || currentAgentModel.name}
              </span>
              <span className="ml-auto shrink-0 text-[9px] uppercase tracking-wider text-muted-foreground/50">
                {currentAgentModel.tier}
              </span>
            </div>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="chat-model" className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
            <Cpu className="h-3.5 w-3.5 text-primary" aria-hidden="true" /> Agent Default Model
          </Label>
          <Select
            id="chat-model"
            name="model_id"
            value={pendingSessionModelId || currentAgentModel?.id || ""}
            onChange={(e) => onDefaultModelChange(e.target.value)}
            disabled={streaming || updateAgentPending}
            className="w-full text-xs"
          >
            {models?.filter((m) => m.active).map((m) => (
              <option key={m.id} value={m.id}>{m.display_name || m.name}</option>
            ))}
          </Select>
        </div>

        <div className="space-y-2">
          <Label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
            <MessageSquare className="h-3.5 w-3.5 text-primary" aria-hidden="true" /> Chat Sessions
          </Label>
          <Button type="button" variant="outline" className="w-full gap-2 text-xs" onClick={onNewSession}>
            <Plus className="h-3.5 w-3.5" aria-hidden="true" /> New Session
          </Button>
          <div className="max-h-[30vh] space-y-1 overflow-y-auto pr-1">
            {agentSessions.map((s) => (
              <div
                key={s.id}
                className={`group flex items-center gap-1 rounded-lg transition-colors duration-200 ${
                  sessionId === s.id
                    ? "bg-primary font-semibold text-primary-foreground shadow-card"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground"
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSessionChange(s.id)}
                  className="block min-h-10 flex-1 truncate rounded-md px-3 py-2 text-left text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {s.title}
                </button>
                <ConfirmDialog
                  trigger={
                    <Button type="button" size="icon" variant="ghost" className="h-10 w-10 shrink-0 text-current/70 hover:bg-destructive/15 hover:text-destructive" aria-label={`Delete session ${s.title}`}>
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>
                  }
                  title={`Delete ${s.title}?`}
                  description="This conversation session and its messages will be removed."
                  confirmLabel="Delete session"
                  destructive
                  onConfirm={() => onDeleteSession(s.id)}
                />
              </div>
            ))}
            {agentSessions.length === 0 && (
              <div className="py-4 text-center text-[11px] text-muted-foreground/60">No active sessions.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
