"use client";

import * as React from "react";
import { Bot, ChevronDown, Cpu, MessageSquare, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Agent, Model, Session } from "@/types";

interface ChatHeaderControlsProps {
  agents?: Agent[];
  models?: Model[];
  sessions?: Session[];
  agentId: string | null;
  sessionId: string | null;
  currentAgent?: Agent;
  currentAgentModel?: Model;
  pendingSessionModelId: string;
  streaming: boolean;
  updateAgentPending: boolean;
  onAgentChange: (agentId: string) => void;
  onDefaultModelChange: (modelId: string) => void;
  onSessionChange: (sessionId: string) => void;
  onNewSession: () => void;
  onDeleteSession: (sessionId: string) => Promise<void>;
  // Plain users chat with the org's one primary (orchestrator) agent. They
  // may choose an admin-configured model, but never switch agents.
  canSwitchAgent: boolean;
  canSwitchModel: boolean;
}

const triggerClass = "h-7 gap-1.5 rounded-full px-2.5 text-xs font-medium text-muted-foreground hover:text-foreground";

// Compact ChatGPT/Claude-style header dropdowns, replacing the old sidebar
// panel — agent/model/session switching now lives inline with the
// conversation instead of a separate column. Same data/callbacks as the
// former ChatSidebarPanel, just a different (denser) presentation.
export function ChatHeaderControls({
  agents,
  models,
  sessions,
  agentId,
  sessionId,
  currentAgent,
  currentAgentModel,
  pendingSessionModelId,
  streaming,
  updateAgentPending,
  onAgentChange,
  onDefaultModelChange,
  onSessionChange,
  onNewSession,
  onDeleteSession,
  canSwitchAgent,
  canSwitchModel,
}: ChatHeaderControlsProps) {
  const agentSessions = sessions?.filter((s) => s.agent_id === agentId) ?? [];
  const effectiveModelId = pendingSessionModelId || currentAgentModel?.id || "";
  const effectiveModel = models?.find((m) => m.id === effectiveModelId) ?? currentAgentModel;
  const currentSession = sessions?.find((s) => s.id === sessionId);

  return (
    <div className="flex min-w-0 items-center gap-1">
      {canSwitchAgent ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="ghost" size="sm" className={triggerClass}>
              <Bot className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="max-w-[8rem] truncate">{currentAgent?.name ?? "Select agent"}</span>
              <ChevronDown className="h-3 w-3 opacity-60" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            <DropdownMenuLabel>Active agent</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {agents?.map((a) => (
              <DropdownMenuItem key={a.id} onSelect={() => onAgentChange(a.id)} className={a.id === agentId ? "font-semibold text-foreground" : undefined}>
                {a.name}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
        <span className={`${triggerClass} pointer-events-none inline-flex`}>
          <Bot className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="max-w-[8rem] truncate">{currentAgent?.name ?? "Assistant"}</span>
        </span>
      )}

      {canSwitchModel ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="ghost" size="sm" disabled={streaming || updateAgentPending} className={triggerClass}>
              <Cpu className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="max-w-[9rem] truncate font-mono">{effectiveModel?.display_name || effectiveModel?.name || "Model"}</span>
              <ChevronDown className="h-3 w-3 opacity-60" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-64">
            <DropdownMenuLabel>{canSwitchAgent ? "Default model" : "Model"}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {models?.filter((m) => m.active).map((m) => (
              <DropdownMenuItem key={m.id} onSelect={() => onDefaultModelChange(m.id)} className={m.id === effectiveModelId ? "font-semibold text-foreground" : undefined}>
                <span className="flex-1 truncate">{m.display_name || m.name}</span>
                <span className="ml-2 shrink-0 text-[9px] uppercase tracking-wider text-muted-foreground/60">{m.tier}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : !canSwitchAgent ? (
        <span className={`${triggerClass} pointer-events-none inline-flex`}>
          <Cpu className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="max-w-[9rem] truncate font-mono">{effectiveModel?.display_name || effectiveModel?.name || "Model"}</span>
        </span>
      ) : null}

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="sm" className={triggerClass}>
            <MessageSquare className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="max-w-[9rem] truncate">{currentSession?.title ?? "New chat"}</span>
            <ChevronDown className="h-3 w-3 opacity-60" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-72">
          <DropdownMenuItem onSelect={onNewSession} className="gap-2 font-medium">
            <Plus className="h-3.5 w-3.5" aria-hidden="true" /> New session
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuLabel>Sessions</DropdownMenuLabel>
          {agentSessions.length === 0 && (
            <div className="px-2 py-3 text-center text-[11px] text-muted-foreground/60">No sessions yet.</div>
          )}
          {agentSessions.map((s) => (
            <DropdownMenuItem
              key={s.id}
              className={`group gap-2 ${s.id === sessionId ? "font-semibold text-foreground" : undefined}`}
              onSelect={(event) => {
                const target = event.target as HTMLElement;
                if (target.closest("[data-delete-trigger]")) {
                  event.preventDefault();
                  return;
                }
                onSessionChange(s.id);
              }}
            >
              <span className="flex-1 truncate">{s.title}</span>
              <button
                type="button"
                data-delete-trigger
                aria-label={`Delete session ${s.title}`}
                className="shrink-0 rounded p-1 text-muted-foreground/60 opacity-0 transition-opacity hover:bg-destructive/15 hover:text-destructive focus:opacity-100 focus:outline-none focus:ring-1 focus:ring-destructive/50 group-hover:opacity-100"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  void onDeleteSession(s.id);
                }}
              >
                <Trash2 className="h-3 w-3" aria-hidden="true" />
              </button>
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
