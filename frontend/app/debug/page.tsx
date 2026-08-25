"use client";

import * as React from "react";
import { Bug, MessageSquare, BarChart3, GitBranch, Workflow } from "lucide-react";
import { useDebugSessions, useSessionTree, useTaskTree, useUrlSearchParam, useUsageSummary, useWorkflowRun } from "@/hooks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared";
import { PageHeader } from "@/components/page-header";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function DebugPage() {
  const sessions = useDebugSessions();
  const usage = useUsageSummary();
  const [sel, setSel] = useUrlSearchParam("session");
  const [rootRunParam, setRootRunParam] = useUrlSearchParam("root_run");
  const [runParam, setRunParam] = useUrlSearchParam("run");
  const [rootRunDraft, setRootRunDraft] = React.useState(rootRunParam ?? "");
  const [workflowRunDraft, setWorkflowRunDraft] = React.useState(runParam ?? "");
  React.useEffect(() => setRootRunDraft(rootRunParam ?? ""), [rootRunParam]);
  React.useEffect(() => setWorkflowRunDraft(runParam ?? ""), [runParam]);
  const tree = useSessionTree(sel);
  const taskTree = useTaskTree(rootRunParam || null);
  const workflowRun = useWorkflowRun(runParam || null);

  return (
    <div className="space-y-6">
      <PageHeader icon={Bug} title="Debug" description="Inspect sessions, messages, and token usage" />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 stagger">
        <Card glass className="flex flex-col shadow-3d-card overflow-hidden">
          <CardHeader className="flex flex-row items-center gap-3 border-b border-border/60 bg-muted/20">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-primary/10 text-primary shadow-inner-edge border border-primary/25">
              <MessageSquare className="h-4 w-4" />
            </div>
            <CardTitle className="text-sm font-semibold tracking-tight text-foreground">Active Sessions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 pt-6">
            <div className="space-y-1.5">
              <label htmlFor="debug-session" className="text-sm font-semibold text-foreground">Select debug session</label>
              <Select id="debug-session" value={sel || ""} onChange={(e) => setSel(e.target.value || null)}>
                <option value="">â€” select session â€”</option>
                {sessions.data?.map((s) => (
                  <option key={s.id} value={s.id}>{s.title}</option>
                ))}
              </Select>
            </div>

            {sessions.isError ? <ErrorState title="Unable to load sessions" description="Debug sessions could not be loaded." onRetry={() => void sessions.refetch()} /> : tree.isLoading ? <LoadingSkeleton variant="table" /> : tree.isError ? <ErrorState title="Unable to load session messages" description="The selected session could not be inspected." onRetry={() => void tree.refetch()} /> : tree.data ? (
              <div className="space-y-3 max-h-[50vh] overflow-y-auto pr-1">
                {tree.data.messages.map((m: any) => (
                  <div
                    key={m.id}
                    className="rounded-xl border border-border/80 bg-card/65 p-3.5 text-xs transition-[border-color,background-color] duration-200 hover:border-primary/40 hover:bg-card shadow-inner-edge"
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <Badge variant="outline" className="text-[10px] bg-muted/40 font-semibold px-2 py-0.5">{m.role}</Badge>
                      {m.meta?.cost_usd != null && (
                        <span className="font-mono text-[10px] text-muted-foreground/85 bg-muted/30 px-1.5 py-0.5 rounded border border-border/30">
                          ${Number(m.meta.cost_usd).toFixed(6)} Â· {m.meta.latency_ms}ms
                        </span>
                      )}
                    </div>
                    <div className="whitespace-pre-wrap leading-relaxed select-text font-sans text-foreground/90">{m.content}</div>
                    {m.meta?.tools?.length > 0 && (
                      <div className="mt-2.5 pt-2 border-t border-border/40 text-[10px] text-muted-foreground/80 flex items-center gap-1.5">
                        <span>Invoked tools:</span>
                        <span className="font-mono bg-muted/50 px-1.5 py-0.5 rounded text-foreground font-medium">
                          {m.meta.tools.map((t: any) => t.name).join(", ")}
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground/80 py-8 text-center border border-dashed border-border/60 rounded-xl bg-muted/10">
                Select a session to inspect its messages.
              </div>
            )}
          </CardContent>
        </Card>

        <Card glass className="flex flex-col shadow-3d-card overflow-hidden">
          <CardHeader className="flex flex-row items-center gap-3 border-b border-border/60 bg-muted/20">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-primary/10 text-primary shadow-inner-edge border border-primary/25">
              <BarChart3 className="h-4 w-4" />
            </div>
            <CardTitle className="text-sm font-semibold tracking-tight text-foreground">Usage Per Agent/Model</CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            {usage.isLoading ? <LoadingSkeleton variant="table" /> : usage.isError ? <ErrorState title="Unable to load usage" description="Usage data could not be loaded." onRetry={() => void usage.refetch()} /> : usage.data?.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Agent</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead className="text-right">Calls</TableHead>
                    <TableHead className="text-right">In</TableHead>
                    <TableHead className="text-right">Out</TableHead>
                    <TableHead className="text-right">Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {usage.data.map((u, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-medium text-xs text-foreground">{u.agent_name}</TableCell>
                      <TableCell className="text-muted-foreground text-xs font-mono">{u.model_name}</TableCell>
                      <TableCell className="text-right tabular-nums text-xs font-mono">{u.calls}</TableCell>
                      <TableCell className="text-right tabular-nums font-mono text-[11px] text-muted-foreground">
                        {u.input_tokens.toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right tabular-nums font-mono text-[11px] text-muted-foreground">
                        {u.output_tokens.toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right tabular-nums font-mono text-[11px] font-semibold text-primary">
                        ${u.cost_usd.toFixed(6)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <EmptyState icon={BarChart3} title="No usage recorded yet" />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card glass className="shadow-3d-card overflow-hidden">
          <CardHeader className="flex flex-row items-center gap-3 border-b border-border/60 bg-muted/20">
            <GitBranch className="h-4 w-4 text-primary" />
            <CardTitle className="text-sm font-semibold text-foreground">Task Tree</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 pt-6">
            <Input id="debug-root-run" name="root_run_id" value={rootRunDraft} onChange={(e) => setRootRunDraft(e.target.value)} onBlur={() => setRootRunParam(rootRunDraft.trim() || null)} onKeyDown={(e) => { if (e.key === "Enter") setRootRunParam(rootRunDraft.trim() || null); }} placeholder="root_run_id" className="font-mono text-xs" />
            {taskTree.data?.tasks?.map((node) => (
              <div key={node.id} className="rounded-xl border border-border/80 bg-card/50 p-3.5 text-xs shadow-inner-edge">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-foreground">{node.goal}</span>
                  <Badge variant="outline">{node.status}</Badge>
                </div>
                <div className="mt-1 font-mono text-muted-foreground text-[10px]">{node.id}</div>
                {node.children.map((child) => (
                  <div key={child.id} className="mt-3 border-l border-border pl-3">
                    <div className="flex items-center justify-between">
                      <span className="text-foreground">{child.goal}</span>
                      <Badge variant="outline">{child.status}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </CardContent>
        </Card>

        <Card glass className="shadow-3d-card overflow-hidden">
          <CardHeader className="flex flex-row items-center gap-3 border-b border-border/60 bg-muted/20">
            <Workflow className="h-4 w-4 text-primary" />
            <CardTitle className="text-sm font-semibold text-foreground">Workflow Run</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 pt-6">
            <Input id="debug-workflow-run" name="workflow_run_id" value={workflowRunDraft} onChange={(e) => setWorkflowRunDraft(e.target.value)} onBlur={() => setRunParam(workflowRunDraft.trim() || null)} onKeyDown={(e) => { if (e.key === "Enter") setRunParam(workflowRunDraft.trim() || null); }} placeholder="workflow_run_id" className="font-mono text-xs" />
            {workflowRun.data && (
              <div className="space-y-2">
                <Badge variant="outline">{workflowRun.data.status}</Badge>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Node</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Attempt</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {workflowRun.data.nodes.map((node) => (
                      <TableRow key={node.id}>
                        <TableCell className="font-mono text-xs text-foreground">{node.node_id}</TableCell>
                        <TableCell><Badge variant="outline">{node.status}</Badge></TableCell>
                        <TableCell className="text-right font-mono text-xs">{node.attempt}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
