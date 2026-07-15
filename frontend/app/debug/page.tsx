"use client";

import * as React from "react";
import { Bug, MessageSquare, BarChart3 } from "lucide-react";
import { useDebugSessions, useSessionTree, useUsageSummary } from "@/hooks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
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
  const [sel, setSel] = React.useState<string | null>(null);
  const tree = useSessionTree(sel);

  return (
    <div className="space-y-6">
      <PageHeader icon={Bug} title="Debug" description="Inspect sessions, messages, and token usage" />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 stagger">
        <Card glass className="flex flex-col">
          <CardHeader className="flex flex-row items-center gap-3 border-b border-border/60 bg-muted/20">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 text-primary shadow-inner-edge">
              <MessageSquare className="h-4 w-4" />
            </div>
            <CardTitle className="text-sm font-semibold tracking-tight">Active Sessions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 pt-6">
            <div className="space-y-1.5">
              <span className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground/80">Select debug session</span>
              <Select value={sel || ""} onChange={(e) => setSel(e.target.value || null)}>
                <option value="">— select session —</option>
                {sessions.data?.map((s) => (
                  <option key={s.id} value={s.id}>{s.title}</option>
                ))}
              </Select>
            </div>

            {tree.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-20 w-full" />
                ))}
              </div>
            ) : tree.data ? (
              <div className="space-y-3 max-h-[50vh] overflow-y-auto pr-1">
                {tree.data.messages.map((m: any) => (
                  <div
                    key={m.id}
                    className="rounded-xl border border-border bg-card/65 p-3.5 text-xs transition-all duration-200 hover:border-primary/40 hover:bg-card"
                  >
                    <div className="mb-2 flex items-center justify-between">
                      <Badge variant="outline" className="text-[10px] bg-muted/40 font-semibold px-2 py-0.5">{m.role}</Badge>
                      {m.meta?.cost_usd != null && (
                        <span className="font-mono text-[10px] text-muted-foreground/85 bg-muted/30 px-1.5 py-0.5 rounded border border-border/30">
                          ${Number(m.meta.cost_usd).toFixed(6)} · {m.meta.latency_ms}ms
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

        <Card glass className="flex flex-col">
          <CardHeader className="flex flex-row items-center gap-3 border-b border-border/60 bg-muted/20">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 text-primary shadow-inner-edge">
              <BarChart3 className="h-4 w-4" />
            </div>
            <CardTitle className="text-sm font-semibold tracking-tight">Usage Per Agent/Model</CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            {usage.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : usage.data?.length ? (
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
                      <TableCell className="font-medium text-xs">{u.agent_name}</TableCell>
                      <TableCell className="text-muted-foreground text-xs">{u.model_name}</TableCell>
                      <TableCell className="text-right tabular-nums text-xs">{u.calls}</TableCell>
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
    </div>
  );
}
