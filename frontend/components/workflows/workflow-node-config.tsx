"use client";

import * as React from "react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Agent, GraphNode, Workflow } from "@/types";

interface WorkflowNodeConfigProps {
  node: GraphNode | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agents: Agent[] | undefined;
  workflows: Workflow[] | undefined;
  currentWorkflowId: string | null;
  onUpdate: (patch: Partial<GraphNode>) => void;
  onDeleteNode?: (id: string) => void;
}

export function WorkflowNodeConfig({
  node,
  open,
  onOpenChange,
  agents,
  workflows,
  currentWorkflowId,
  onUpdate,
  onDeleteNode,
}: WorkflowNodeConfigProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="bg-card/95 backdrop-blur-xl flex flex-col justify-between overflow-y-auto">
        <div>
          <SheetHeader>
            <SheetTitle>Node configuration</SheetTitle>
            <SheetDescription>
              {node ? `Editing "${node.label || node.id}" (${node.kind})` : "No node selected"}
            </SheetDescription>
          </SheetHeader>

        {node && (
          <div className="mt-6 space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                Label name
              </Label>
              <Input
                className="text-xs"
                value={node.label}
                onChange={(e) => onUpdate({ label: e.target.value })}
                placeholder="Label name"
              />
            </div>

            {node.kind === "agent" && (
              <div className="space-y-1.5">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                  Target agent
                </Label>
                <Select
                  className="text-xs w-full"
                  value={node.agent_id || ""}
                  onChange={(e) => onUpdate({ agent_id: e.target.value })}
                >
                  {agents?.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </Select>
              </div>
            )}

            {node.kind === "merge" && (
              <div className="space-y-1.5">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                  Merge logic
                </Label>
                <Select
                  className="text-xs w-full"
                  value={node.merge_mode || "all"}
                  onChange={(e) => onUpdate({ merge_mode: e.target.value as "all" | "any" })}
                >
                  <option value="all">Wait all ancestors</option>
                  <option value="any">Wait any ancestor</option>
                </Select>
              </div>
            )}

            {node.kind === "tool" && (
              <div className="space-y-1.5">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                  Tool to invoke
                </Label>
                <Input
                  className="text-xs"
                  value={node.config?.tool || ""}
                  onChange={(e) => onUpdate({ config: { ...node.config, tool: e.target.value } })}
                  placeholder="e.g. read_attachment"
                />
              </div>
            )}

            {node.kind === "approval" && (
              <div className="space-y-1.5">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                  Tool name (optional)
                </Label>
                <Input
                  className="text-xs"
                  value={node.config?.tool_name || ""}
                  onChange={(e) => onUpdate({ config: { ...node.config, tool_name: e.target.value } })}
                  placeholder="e.g. send_email"
                />
                <p className="rounded-lg border border-warning/30 bg-warning/10 px-2.5 py-2 text-[11px] text-warning">
                  The workflow will pause here and wait for a human decision via Approvals.
                </p>
              </div>
            )}

            {node.kind === "scheduler" && (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                    Schedule Expression (Cron or Interval)
                  </Label>
                  <Input
                    className="text-xs"
                    value={node.config?.cron || ""}
                    onChange={(e) => onUpdate({ config: { ...node.config, cron: e.target.value } })}
                    placeholder="e.g. 0 7 * * 1-5 (Weekdays 07:30)"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                    Schedule Display Label
                  </Label>
                  <Input
                    className="text-xs"
                    value={node.config?.schedule_label || ""}
                    onChange={(e) => onUpdate({ config: { ...node.config, schedule_label: e.target.value } })}
                    placeholder="e.g. Weekdays at 07:30"
                  />
                </div>
              </div>
            )}

            {node.kind === "integration" && (
              <div className="space-y-1.5">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                  Data Source / Integration
                </Label>
                <Select
                  className="text-xs w-full"
                  value={node.config?.source || "gmail"}
                  onChange={(e) => onUpdate({ config: { ...node.config, source: e.target.value } })}
                >
                  <option value="gmail">Gmail Inbound & Threads</option>
                  <option value="google_calendar">Google Calendar Meetings</option>
                  <option value="google_drive">Google Drive Documents</option>
                  <option value="gmail_and_calendar">Gmail + Google Calendar</option>
                  <option value="webhook">Custom Webhook Event</option>
                </Select>
              </div>
            )}

            {node.kind === "triager" && (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                    Triage Policy / Routing Rules
                  </Label>
                  <Input
                    className="text-xs"
                    value={node.config?.policy || ""}
                    onChange={(e) => onUpdate({ config: { ...node.config, policy: e.target.value } })}
                    placeholder="e.g. rank_by_urgency, classify_intent"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                    Target Categories (comma-separated)
                  </Label>
                  <Input
                    className="text-xs"
                    value={node.config?.categories || ""}
                    onChange={(e) => onUpdate({ config: { ...node.config, categories: e.target.value } })}
                    placeholder="e.g. sales, support, inquiry, spam"
                  />
                </div>
              </div>
            )}

            {node.kind === "sub_workflow" && (
              <div className="space-y-1.5">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                  Workflow to run
                </Label>
                <Select
                  className="text-xs w-full"
                  value={node.config?.workflow_id || ""}
                  onChange={(e) => onUpdate({ config: { ...node.config, workflow_id: e.target.value } })}
                >
                  <option value="">Select a workflow…</option>
                  {workflows
                    ?.filter((w) => w.id !== currentWorkflowId)
                    .map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                </Select>
              </div>
            )}
          </div>
        )}
        </div>

        {node && onDeleteNode && (
          <div className="mt-8 border-t border-border/40 pt-4">
            <Button
              variant="outline"
              className="w-full gap-2 border-destructive/40 text-destructive hover:bg-destructive hover:text-destructive-foreground transition-all duration-150"
              onClick={() => {
                onDeleteNode(node.id);
                onOpenChange(false);
              }}
            >
              <Trash2 className="h-4 w-4" /> Delete node
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
