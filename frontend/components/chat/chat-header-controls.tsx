"use client";

import * as React from "react";
import { Bot, ChevronDown, Cpu, MessageSquare, Plus, ShieldCheck, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useTranslation } from "@/lib/i18n";
import type { Agent, ExecutionPolicy, Model, Session } from "@/types";

interface ChatHeaderControlsProps {
  agents?: Agent[];
  agentId: string | null;
  currentAgent?: Agent;
  onAgentChange: (agentId: string) => void;
  canSwitchAgent: boolean;
}

const triggerClass = "h-7 gap-1.5 rounded-full px-2.5 text-xs font-medium text-muted-foreground hover:text-foreground";

export function ChatHeaderControls({
  agents,
  agentId,
  currentAgent,
  onAgentChange,
  canSwitchAgent,
}: ChatHeaderControlsProps) {
  const { tx } = useTranslation();

  return (
    <div className="flex min-w-0 items-center gap-1">
      {canSwitchAgent ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="ghost" size="sm" className={triggerClass}>
              <Bot className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="max-w-[8rem] truncate">{currentAgent?.name ?? (tx("Chọn agent", "Select agent"))}</span>
              <ChevronDown className="h-3 w-3 opacity-60" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            <DropdownMenuLabel>{tx("Agent đang hoạt động", "Active agent")}</DropdownMenuLabel>
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
          <span className="max-w-[8rem] truncate">{currentAgent?.name ?? (tx("Trợ lý AI", "Assistant"))}</span>
        </span>
      )}
    </div>
  );
}
