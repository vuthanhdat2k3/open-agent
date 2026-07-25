"use client";

import * as React from "react";
import { Bot, Cpu, Pencil, Trash2, History, Wrench } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Agent, AgentToolInfo, Model } from "@/types";

interface AgentCardProps {
  agent: Agent;
  models?: Model[];
  tools?: AgentToolInfo[];
  onEdit: (agent: Agent) => void;
  onReleases: (agent: Agent) => void;
  onDelete: (id: string) => void;
}

const tierColor: Record<string, string> = {
  frontier: "border-primary/60 text-primary bg-primary/10",
  balanced: "border-info/60 text-info bg-info/10",
  economy: "border-muted-foreground/40 text-muted-foreground bg-muted/20",
};

export function AgentCard({
  agent,
  models,
  tools,
  onEdit,
  onReleases,
  onDelete,
}: AgentCardProps) {
  const agentModel = models?.find((m) => m.id === agent.model_id);

  const handleDelete = () => {
    if (window.confirm(`Xóa agent "${agent.name}"? Hành động này không thể hoàn tác.`)) {
      onDelete(agent.id);
    }
  };

  return (
    <Card glass className="card-lift flex flex-col p-5 group">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary/25 via-primary/10 to-transparent text-primary shadow-3d-card border border-primary/20">
            <Bot className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="truncate font-semibold text-sm tracking-tight text-foreground">{agent.name}</p>
            {agentModel && (
              <p className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground/70">
                <Cpu className="h-2.5 w-2.5 text-primary/60" />
                <span className="truncate font-mono">{agentModel.display_name || agentModel.name}</span>
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-muted-foreground hover:text-foreground active-tactile transition-transform"
            onClick={() => onReleases(agent)}
            aria-label={`Release history for ${agent.name}`}
          >
            <History className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-muted-foreground hover:text-foreground active-tactile transition-transform"
            onClick={() => onEdit(agent)}
            aria-label={`Edit ${agent.name}`}
          >
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-7 w-7 text-muted-foreground hover:text-destructive active-tactile transition-transform"
            onClick={handleDelete}
            aria-label={`Delete ${agent.name}`}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Description */}
      {agent.description && (
        <p className="mt-3 line-clamp-2 text-xs text-muted-foreground leading-relaxed">{agent.description}</p>
      )}

      <div className="mt-3 flex items-center gap-2 text-[10px] text-muted-foreground">
        <History className="h-3 w-3" />
        Active release v{agent.latest_release_number}
      </div>

      {/* Model badge row */}
      {agentModel && (
        <div className="mt-3 flex items-center gap-1.5 flex-wrap">
          <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider border ${tierColor[agentModel.tier] ?? tierColor.economy}`}>
            {agentModel.tier}
          </span>
          <span className="text-[10px] font-mono text-muted-foreground/60 bg-muted/30 border border-border/30 px-2 py-0.5 rounded-full">
            ctx {agentModel.context_window.toLocaleString()}
          </span>
          <span className="text-[10px] font-mono text-muted-foreground/60 bg-muted/30 border border-border/30 px-2 py-0.5 rounded-full">
            T={agent.temperature.toFixed(1)}
          </span>
          <span className="text-[10px] font-mono text-muted-foreground/60 bg-muted/30 border border-border/30 px-2 py-0.5 rounded-full">
            ×{agent.max_iterations}
          </span>
        </div>
      )}

      {/* Tools */}
      {agent.tools.length > 0 && (
        <div className="mt-4 pt-3 border-t border-border/40 space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground/80">
            Granted tools ({agent.tools.length})
          </div>
          <div className="flex flex-wrap gap-1.5">
            {agent.tools.map((t) => (
              <Badge key={t} variant="outline" className="gap-1 font-mono text-[10px] bg-muted/30 border-border/50">
                <Wrench className="h-2.5 w-2.5" /> {t}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
