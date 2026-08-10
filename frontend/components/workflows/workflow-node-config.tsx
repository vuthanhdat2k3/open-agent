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
import type { Agent, GraphNode, Workflow } from "@/types";

interface WorkflowNodeConfigProps {
  node: GraphNode | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agents: Agent[] | undefined;
  workflows: Workflow[] | undefined;
  currentWorkflowId: string | null;
  onUpdate: (patch: Partial<GraphNode>) => void;
}

export function WorkflowNodeConfig({
  node,
  open,
  onOpenChange,
  agents,
  workflows,
  currentWorkflowId,
  onUpdate,
}: WorkflowNodeConfigProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="bg-card/95 backdrop-blur-xl">
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
      </SheetContent>
    </Sheet>
  );
}
