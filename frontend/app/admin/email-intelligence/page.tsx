"use client";

import * as React from "react";
import { Activity, Database, GitBranch, Search, ShieldAlert, Timer } from "lucide-react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { useTranslation } from "@/lib/i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ErrorState, LoadingSkeleton } from "@/components/shared";
import { useQuery } from "@tanstack/react-query";
import { getActiveOrgId } from "@/lib/auth";
import { emailIntelligenceQueryKeys } from "@/lib/email-intelligence/query-keys";

type Overview = { connections: { total: number; healthy: number; unhealthy: number }; queue: { ready: number; retrying: number; oldest_age_seconds: number; dead_letter: number }; reviews: { open: number; due_soon: number; breached: number }; scheduler: { healthy: boolean; missed_occurrences: number } };

function useAdminResource<T>(resource: string, enabled: boolean) {
  const orgId = getActiveOrgId();
  return useQuery({
    queryKey: ["admin-email-intelligence", orgId, resource],
    queryFn: () => api.get<T>(`/api/admin/email-intelligence/${resource}`),
    enabled,
    refetchInterval: 30_000,
  });
}

export default function EmailOperationsPage() {
  const { t, dict, locale } = useTranslation();
  const orgId = getActiveOrgId();
  const overview = useQuery({ queryKey: emailIntelligenceQueryKeys(orgId).adminOverview, queryFn: () => api.get<Overview>("/api/admin/email-intelligence/overview"), refetchInterval: 30_000 });
  const [tab, setTab] = React.useState("overview");
  const [traceId, setTraceId] = React.useState("");
  const queue = useAdminResource<Array<Record<string, unknown>>>("queue", tab === "queue");
  const schedulers = useAdminResource<Array<Record<string, unknown>>>("schedulers", tab === "schedulers");
  const reviews = useAdminResource<Array<Record<string, unknown>>>("reviews", tab === "reviews");
  const traces = useQuery({ queryKey: ["admin-trace", orgId, traceId], queryFn: () => api.get<{ events: Array<Record<string, unknown>> }>(`/api/admin/email-intelligence/traces?correlation_id=${encodeURIComponent(traceId)}`), enabled: tab === "traces" && traceId.length > 2 });

  if (overview.isLoading) return <LoadingSkeleton variant="grid" />;
  if (overview.isError || !overview.data) return <ErrorState title="Unable to load operations" description="Admin email intelligence health is unavailable." onRetry={() => void overview.refetch()} />;
  const data = overview.data;
  const resource = tab === "queue" ? queue : tab === "schedulers" ? schedulers : reviews;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Activity}
        title={dict.pages.emailGateway.title}
        description={dict.pages.emailGateway.description}
      />
      <div className="grid gap-4 md:grid-cols-4">
        <Metric icon={Database} label="Connections" value={`${data.connections.healthy}/${data.connections.total}`} detail={data.connections.unhealthy ? `${data.connections.unhealthy} unhealthy` : "Healthy"} danger={data.connections.unhealthy > 0} />
        <Metric icon={GitBranch} label="Queue" value={`${data.queue.ready}`} detail={`${data.queue.retrying} retrying · ${data.queue.dead_letter} dead-letter`} danger={data.queue.dead_letter > 0} />
        <Metric icon={ShieldAlert} label="Reviews" value={`${data.reviews.open}`} detail={`${data.reviews.breached} SLA breached`} danger={data.reviews.breached > 0} />
        <Metric icon={Timer} label="Scheduler" value={data.scheduler.healthy ? "Healthy" : "Degraded"} detail={`${data.scheduler.missed_occurrences} missed occurrences`} danger={!data.scheduler.healthy} />
      </div>
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Admin operations sections">
        {[["overview", "Overview"], ["queue", "Queue"], ["schedulers", "Schedulers"], ["reviews", "Reviews"], ["traces", "Traces"]].map(([value, label]) => <Button key={value} size="sm" variant={tab === value ? "default" : "outline"} onClick={() => setTab(value)} role="tab" aria-selected={tab === value}>{label}</Button>)}
      </div>
      {tab === "overview" && <Card><CardHeader><CardTitle>Operational guardrails</CardTitle></CardHeader><CardContent className="space-y-2 text-sm text-muted-foreground"><p>Admin actions remain capability-gated and read-only until the corresponding backend policy is enabled.</p><p>Use correlation IDs to inspect a sanitized lifecycle trace. No provider payloads or secrets are rendered here.</p></CardContent></Card>}
      {tab !== "overview" && tab !== "traces" && (resource.isLoading ? <LoadingSkeleton variant="table" /> : resource.isError ? <ErrorState title="Unable to load resource" description="Retry the operation query." onRetry={() => void resource.refetch()} /> : <OperationsTable rows={resource.data || []} />)}
      {tab === "traces" && <Card><CardHeader><CardTitle>Trace Explorer</CardTitle></CardHeader><CardContent className="space-y-4"><div className="flex gap-2"><Input value={traceId} onChange={(event) => setTraceId(event.target.value)} placeholder="Correlation ID" aria-label="Correlation ID" /><Button onClick={() => void traces.refetch()} disabled={traceId.length < 3}><Search className="mr-1 h-4 w-4" />Search</Button></div>{traces.data?.events?.length ? <OperationsTable rows={traces.data.events} /> : <p className="text-sm text-muted-foreground">Enter a correlation ID to inspect sanitized events.</p>}</CardContent></Card>}
    </div>
  );
}

function Metric({ icon: Icon, label, value, detail, danger }: { icon: typeof Activity; label: string; value: string; detail: string; danger?: boolean }) {
  return <Card><CardContent className="p-4"><div className="flex items-center justify-between"><span className="text-sm text-muted-foreground">{label}</span><Icon className={danger ? "h-4 w-4 text-destructive" : "h-4 w-4 text-primary"} aria-hidden="true" /></div><div className="mt-2 text-2xl font-semibold">{value}</div><p className={danger ? "mt-1 text-xs text-destructive" : "mt-1 text-xs text-muted-foreground"}>{detail}</p></CardContent></Card>;
}

function OperationsTable({ rows }: { rows: Array<Record<string, unknown>> }) {
  if (!rows.length) return <Card><CardContent className="p-6 text-sm text-muted-foreground">No operational records require attention.</CardContent></Card>;
  return <Card><CardContent className="overflow-x-auto p-0"><table className="w-full text-left text-sm"><thead className="border-b border-border/70 text-xs uppercase text-muted-foreground"><tr><th className="p-4">Resource</th><th className="p-4">Status</th><th className="p-4">Time</th><th className="p-4">Risk</th></tr></thead><tbody>{rows.map((row, index) => <tr key={String(row.id || row.event_id || index)} className="border-b border-border/50 last:border-0"><td className="max-w-xs truncate p-4 font-mono text-xs">{String(row.event_type || row.job_key || row.title || row.id || row.event_id)}</td><td className="p-4"><Badge variant={String(row.status || row.sla_status) === "BREACHED" || String(row.status) === "dead_letter" ? "destructive" : "outline"}>{String(row.status || row.sla_status || "unknown")}</Badge></td><td className="p-4 text-xs text-muted-foreground">{String(row.created_at || row.scheduled_for || row.occurred_at || row.opened_at || "—")}</td><td className="p-4 text-xs text-muted-foreground">{String(row.risk_level || row.last_error_code || "—")}</td></tr>)}</tbody></table></CardContent></Card>;
}
