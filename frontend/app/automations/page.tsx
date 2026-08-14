"use client";

import * as React from "react";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Gauge,
  LibraryBig,
  Plug,
  Search,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { getActiveOrgId } from "@/lib/auth";
import { getWorkflowActivity, getWorkflowCatalog, getWorkflowInstallations, installWorkflowTemplate, pauseWorkflowInstallation, resumeWorkflowInstallation, deleteWorkflowInstallation, type WorkflowCatalogItem, type WorkflowInstallation } from "@/lib/automations/api";
import { workflowIcon } from "@/lib/automations/icons";

const categories = [
  { value: "", label: "All workflows" },
  { value: "daily_planning", label: "Daily planning" },
  { value: "meetings", label: "Meetings" },
  { value: "follow_up", label: "Follow-up" },
  { value: "customer_intelligence", label: "Customer intelligence" },
  { value: "reporting", label: "Reporting" },
];

function integrationLabel(value: string) {
  return ({ gmail: "Gmail", google_calendar: "Calendar", google_drive: "Drive" } as Record<string, string>)[value] ?? value;
}

function costLabel(value: string) {
  return value === "low" ? "Low cost" : value === "medium" ? "Medium cost" : "High cost";
}

function approvalLabel(value: string) {
  if (value === "none") return "No external actions";
  if (value === "trusted_rule_eligible") return "Trusted rule eligible";
  return "Approval required";
}

function TemplateCard({ item, onOpen, onSetup }: { item: WorkflowCatalogItem; onOpen: (item: WorkflowCatalogItem) => void; onSetup: (item: WorkflowCatalogItem) => void }) {
  const Icon = workflowIcon(item.icon);
  return (
    <Card className="group flex h-full flex-col border-border/80 bg-card/80 transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-3d-elevated" glass>
      <CardHeader className="space-y-3 pb-4">
        <div className="flex items-start justify-between gap-3">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-primary/20 bg-primary/10 text-primary shadow-inner-edge">
            <Icon className="h-5 w-5" aria-hidden="true" />
          </div>
          {item.recommendation.recommended && <Badge variant="info"><Sparkles className="h-3 w-3" aria-hidden="true" />Recommended</Badge>}
        </div>
        <div>
          <CardTitle className="line-clamp-2 text-base leading-6">{item.name}</CardTitle>
          <CardDescription className="mt-2 line-clamp-2 leading-5">{item.description}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4 pt-0">
        <p className="line-clamp-3 text-sm leading-5 text-foreground/85">{item.outcome}</p>
        <div className="mt-auto space-y-3 border-t border-border/60 pt-3 text-xs text-muted-foreground">
          <div className="flex flex-wrap items-center gap-1.5">
            {item.required_integrations.map((integration) => <Badge key={integration} variant="outline"><Plug className="h-3 w-3" aria-hidden="true" />{integrationLabel(integration)}</Badge>)}
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <span className="flex items-center gap-1.5"><Clock3 className="h-3.5 w-3.5" aria-hidden="true" />{item.default_schedule_label}</span>
            <span className="flex items-center gap-1.5"><Gauge className="h-3.5 w-3.5" aria-hidden="true" />{costLabel(item.cost_tier)}</span>
            <span className="flex items-center gap-1.5 sm:col-span-2"><ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />{approvalLabel(item.side_effect_policy)}</span>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => onOpen(item)}>View details</Button>
          <Button type="button" size="sm" variant={item.capabilities.can_install ? "default" : "outline"} disabled={!item.capabilities.can_install} onClick={() => onSetup(item)} aria-label={item.capabilities.can_install ? `Set up ${item.name}` : `${item.name} preview only`}>{item.capabilities.can_install ? <>Set up <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" /></> : "Preview only"}</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SetupDialog({ item, onClose, onInstalled }: { item: WorkflowCatalogItem | null; onClose: () => void; onInstalled: (installation: WorkflowInstallation) => void }) {
  const queryClient = useQueryClient();
  const [step, setStep] = useState(1);
  const [scheduleKind, setScheduleKind] = useState<WorkflowInstallation["schedule"]["kind"]>("daily");
  const [time, setTime] = useState("07:30");
  const [name, setName] = useState("");
  const install = useMutation({
    mutationFn: () => installWorkflowTemplate({ template_key: item!.key, name: name.trim() || undefined, timezone: "Asia/Ho_Chi_Minh", schedule: { kind: scheduleKind, time } }),
    onSuccess: (installation) => {
      void queryClient.invalidateQueries({ queryKey: ["workflow-installations"] });
      onInstalled(installation);
    },
  });
  useEffect(() => {
    if (item) {
      setStep(1);
      setScheduleKind(item.default_schedule_label.toLowerCase().includes("hour") ? "hourly" : item.default_schedule_label.toLowerCase().includes("week") ? "weekdays" : "daily");
      setTime(item.default_schedule_label.match(/\d{2}:\d{2}/)?.[0] ?? "07:30");
      setName(item.name);
    }
  }, [item]);
  return <Dialog open={Boolean(item)} onOpenChange={(open) => { if (!open) onClose(); }}>
    {item && <DialogContent className="max-w-xl">
      <DialogHeader><DialogTitle>Set up {item.name}</DialogTitle><DialogDescription>Choose a safe schedule. You can change it later.</DialogDescription></DialogHeader>
      <div className="flex items-center gap-2 border-b border-border/70 pb-4 text-xs font-medium text-muted-foreground" aria-label="Setup progress">
        {["Schedule", "Review", "Enable"].map((label, index) => { const current = index + 1 === step; const done = index + 1 < step; return <div key={label} className="flex items-center gap-2"><span className={`grid h-6 w-6 place-items-center rounded-full border ${current ? "border-primary bg-primary text-primary-foreground" : done ? "border-success bg-success/15 text-success" : "border-border"}`}>{done ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : index + 1}</span><span className={current ? "text-foreground" : undefined}>{label}</span>{index < 2 && <span className="h-px w-6 bg-border" aria-hidden="true" />}</div>; })}
      </div>
      {step === 1 && <div className="space-y-4">
        <div className="rounded-lg border border-primary/20 bg-primary/[0.04] p-4 text-sm"><p className="font-semibold">What will happen</p><p className="mt-1 leading-6 text-muted-foreground">{item.outcome}</p></div>
        <div className="space-y-2"><label htmlFor="automation-name" className="text-sm font-medium">Automation name</label><Input id="automation-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={160} /></div>
        <div className="grid gap-3 sm:grid-cols-2"><div className="space-y-2"><label htmlFor="automation-frequency" className="text-sm font-medium">Run frequency</label><select id="automation-frequency" value={scheduleKind} onChange={(event) => setScheduleKind(event.target.value as WorkflowInstallation["schedule"]["kind"])} className="h-10 w-full rounded-lg border border-border bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><option value="hourly">Every hour</option><option value="daily">Every day</option><option value="weekdays">Weekdays</option><option value="weekly">Weekly</option><option value="event">When a relevant event arrives</option></select></div><div className="space-y-2"><label htmlFor="automation-time" className="text-sm font-medium">Time · Vietnam</label><Input id="automation-time" type="time" value={time} onChange={(event) => setTime(event.target.value)} disabled={scheduleKind === "hourly" || scheduleKind === "event"} /></div></div>
        <p className="text-xs text-muted-foreground">Timezone: Asia/Ho_Chi_Minh. The server calculates the next run.</p>
      </div>}
      {step === 2 && <div className="space-y-4 text-sm"><div className="rounded-lg border border-border/70 p-4"><p className="font-semibold">Data and safety</p><ul className="mt-3 space-y-3 text-muted-foreground"><li className="flex gap-2"><Plug className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />Uses {item.required_integrations.map(integrationLabel).join(" and ")} when connected.</li><li className="flex gap-2"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />{approvalLabel(item.side_effect_policy)}. External actions are never silently executed.</li><li className="flex gap-2"><Gauge className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />Estimated cost: {costLabel(item.cost_tier)} · up to ${item.estimated_cost_usd.per_run_max ?? "—"}/run.</li></ul></div><p className="text-xs text-muted-foreground">Connection binding and permission checks are enforced by the server before a run is dispatched.</p></div>}
      {step === 3 && <div className="space-y-4 text-sm"><div className="rounded-lg border border-border/70 p-4"><p className="font-semibold">Ready to enable</p><dl className="mt-3 grid gap-3 sm:grid-cols-2"><div><dt className="text-xs text-muted-foreground">Automation</dt><dd className="mt-1 font-medium">{name || item.name}</dd></div><div><dt className="text-xs text-muted-foreground">Schedule</dt><dd className="mt-1 font-medium">{scheduleKind === "hourly" ? "Every hour" : scheduleKind === "event" ? "When a relevant event arrives" : `${scheduleKind === "weekdays" ? "Weekdays" : scheduleKind === "weekly" ? "Weekly" : "Daily"} at ${time}`}</dd></div><div><dt className="text-xs text-muted-foreground">Timezone</dt><dd className="mt-1 font-medium">Asia/Ho_Chi_Minh</dd></div><div><dt className="text-xs text-muted-foreground">Safety</dt><dd className="mt-1 font-medium">{approvalLabel(item.side_effect_policy)}</dd></div></dl></div>{install.isError && <p className="text-sm text-destructive" role="alert">Could not enable this automation. It may already be installed or a connection may need attention.</p>}</div>}
      <DialogFooter><Button type="button" variant="outline" onClick={() => step === 1 ? onClose() : setStep((value) => value - 1)}>{step === 1 ? "Cancel" : "Back"}</Button>{step < 3 ? <Button type="button" onClick={() => setStep((value) => value + 1)} disabled={!name.trim()}>Continue</Button> : <Button type="button" loading={install.isPending} onClick={() => install.mutate()}>Enable automation</Button>}</DialogFooter>
    </DialogContent>}
  </Dialog>;
}

function TemplateDetails({ item, onClose }: { item: WorkflowCatalogItem | null; onClose: () => void }) {
  const Icon = item ? workflowIcon(item.icon) : Zap;
  return (
    <Dialog open={Boolean(item)} onOpenChange={(open) => { if (!open) onClose(); }}>
      {item && <DialogContent className="max-w-xl">
        <DialogHeader>
          <div className="mb-2 grid h-11 w-11 place-items-center rounded-lg border border-primary/20 bg-primary/10 text-primary"><Icon className="h-5 w-5" aria-hidden="true" /></div>
          <DialogTitle>{item.name}</DialogTitle>
          <DialogDescription>{item.description}</DialogDescription>
        </DialogHeader>
        <div className="space-y-5 text-sm">
          <section className="rounded-lg border border-primary/20 bg-primary/[0.04] p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">What you receive</p>
            <p className="mt-2 leading-6 text-foreground">{item.outcome}</p>
          </section>
          <section className="space-y-3">
            <h3 className="font-semibold">How it works</h3>
            <ol className="space-y-3 text-muted-foreground">
              <li className="flex gap-3"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-muted font-mono text-xs text-foreground">1</span><span>Read only the connected data needed for this workflow.</span></li>
              <li className="flex gap-3"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-muted font-mono text-xs text-foreground">2</span><span>Analyze and organize useful information with bounded cost and latency.</span></li>
              <li className="flex gap-3"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-muted font-mono text-xs text-foreground">3</span><span>Send a private result to your Automation Hub and notification bell.</span></li>
            </ol>
          </section>
          <section className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-border/70 p-3"><p className="text-xs text-muted-foreground">Required</p><p className="mt-1 font-medium">{item.required_integrations.map(integrationLabel).join(" · ")}</p></div>
            <div className="rounded-lg border border-border/70 p-3"><p className="text-xs text-muted-foreground">Schedule</p><p className="mt-1 font-medium">{item.default_schedule_label}</p></div>
            <div className="rounded-lg border border-border/70 p-3"><p className="text-xs text-muted-foreground">External actions</p><p className="mt-1 font-medium">{approvalLabel(item.side_effect_policy)}</p></div>
            <div className="rounded-lg border border-border/70 p-3"><p className="text-xs text-muted-foreground">Estimated cost</p><p className="mt-1 font-medium">{costLabel(item.cost_tier)} · up to ${item.estimated_cost_usd.per_run_max ?? "—"}/run</p></div>
          </section>
        </div>
        <DialogFooter><Button type="button" onClick={onClose}>Close</Button></DialogFooter>
      </DialogContent>}
    </Dialog>
  );
}

export default function AutomationsPage() {
  const queryClient = useQueryClient();
  const [view, setView] = useState<"discover" | "active">("discover");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [selected, setSelected] = useState<WorkflowCatalogItem | null>(null);
  const [setupItem, setSetupItem] = useState<WorkflowCatalogItem | null>(null);
  const deferredSearch = useDeferredValue(search);
  const orgId = getActiveOrgId();
  const catalog = useQuery({
    queryKey: ["workflow-catalog", orgId, deferredSearch, category],
    queryFn: () => getWorkflowCatalog({ query: deferredSearch, category }),
    staleTime: 60_000,
  });
  const installations = useQuery({ queryKey: ["workflow-installations", orgId], queryFn: getWorkflowInstallations, enabled: view === "active" });
  const activity = useQuery({ queryKey: ["workflow-activity", orgId], queryFn: getWorkflowActivity, enabled: view === "active" });
  const pause = useMutation({ mutationFn: pauseWorkflowInstallation, onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["workflow-installations", orgId] }) });
  const resume = useMutation({ mutationFn: resumeWorkflowInstallation, onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["workflow-installations", orgId] }) });
  const remove = useMutation({ mutationFn: deleteWorkflowInstallation, onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["workflow-installations", orgId] }) });
  const items = useMemo(() => catalog.data?.data ?? [], [catalog.data?.data]);
  const recommended = useMemo(() => items.filter((item) => item.recommendation.recommended), [items]);

  return (
    <div className="space-y-6">
      <PageHeader icon={Zap} title="Automations" description="Set up helpful routines for email, meetings, customer research, and follow-up." />
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-border/70 bg-card/60 p-4"><p className="text-xs text-muted-foreground">Available workflows</p><p className="mt-1 text-2xl font-semibold tabular-nums">{catalog.isLoading ? "—" : items.length}</p></div>
        <div className="rounded-xl border border-border/70 bg-card/60 p-4"><p className="text-xs text-muted-foreground">Recommended for you</p><p className="mt-1 text-2xl font-semibold tabular-nums">{catalog.isLoading ? "—" : recommended.length}</p></div>
        <div className="rounded-xl border border-border/70 bg-card/60 p-4"><p className="text-xs text-muted-foreground">Safety default</p><p className="mt-1 flex items-center gap-1.5 text-sm font-medium"><CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />External actions need approval</p></div>
      </div>
      <div className="flex flex-col gap-3 border-b border-border/70 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-1 rounded-lg bg-muted/60 p-1" role="tablist" aria-label="Automation views"><button type="button" role="tab" aria-selected={view === "discover"} onClick={() => setView("discover")} className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${view === "discover" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}><LibraryBig className="mr-1.5 inline h-3.5 w-3.5" aria-hidden="true" />Discover</button><button type="button" role="tab" aria-selected={view === "active"} onClick={() => setView("active")} className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${view === "active" ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}><Zap className="mr-1.5 inline h-3.5 w-3.5" aria-hidden="true" />Active</button></div>
          <p className="mt-3 text-sm text-muted-foreground">{view === "discover" ? "Choose a routine by the result you want, not by technical configuration." : "See the routines you have enabled and pause them when needed."}</p>
        </div>
        {view === "discover" && <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative"><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" /><Input aria-label="Search workflows" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search workflows" className="w-full pl-9 sm:w-56" /></div>
          <select aria-label="Filter workflows by category" value={category} onChange={(event) => setCategory(event.target.value)} className="h-10 rounded-lg border border-border bg-background px-3 text-sm text-foreground shadow-inner-edge focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            {categories.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </div>}
      </div>
      {view === "discover" ? (catalog.isLoading ? <LoadingSkeleton variant="grid" /> : catalog.isError ? <ErrorState title="Unable to load workflows" description="The workflow catalog could not be loaded." onRetry={() => void catalog.refetch()} /> : items.length === 0 ? <EmptyState icon={LibraryBig} title="No workflows found" description="Try clearing your search or category filter." action={<Button type="button" variant="outline" onClick={() => { setSearch(""); setCategory(""); }}>Clear filters</Button>} /> : <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 stagger">{items.map((item) => <TemplateCard key={`${item.key}-${item.version}`} item={item} onOpen={setSelected} onSetup={setSetupItem} />)}</div>) : (installations.isLoading ? <LoadingSkeleton variant="table" /> : installations.isError ? <ErrorState title="Unable to load active automations" description="Your enabled workflows could not be loaded." onRetry={() => void installations.refetch()} /> : <div className="space-y-6">{installations.data?.length ? <div className="space-y-3">{installations.data.map((installation) => <Card key={installation.id} glass><CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><h3 className="truncate font-semibold">{installation.name}</h3><Badge variant={installation.status === "paused" ? "warning" : "success"}>{installation.status === "paused" ? "Paused" : "Enabled"}</Badge></div><p className="mt-1 text-sm text-muted-foreground">{installation.schedule.kind === "hourly" ? "Every hour" : installation.schedule.kind === "event" ? "When a relevant event arrives" : `${installation.schedule.kind === "weekdays" ? "Weekdays" : installation.schedule.kind === "weekly" ? "Weekly" : "Daily"} at ${installation.schedule.time ?? "—"}`} · {installation.timezone}</p><p className="mt-1 text-xs text-muted-foreground">Template: {installation.template_key}</p></div><div className="flex flex-wrap items-center gap-2"><Button type="button" size="sm" variant="outline" disabled={pause.isPending || resume.isPending} onClick={() => (installation.status === "paused" ? resume.mutate(installation.id) : pause.mutate(installation.id))}>{installation.status === "paused" ? "Resume" : "Pause"}</Button><Button type="button" size="sm" variant="destructive" disabled={remove.isPending} onClick={() => { if (window.confirm(`Remove ${installation.name}?`)) remove.mutate(installation.id); }}>Remove</Button></div></CardContent></Card>)}</div> : <EmptyState icon={Zap} title="No active automations" description="Discover a workflow and enable it to start building your personal command center." action={<Button type="button" onClick={() => setView("discover")}>Discover workflows</Button>} />}<Card glass><CardHeader><CardTitle className="text-base">Recent activity</CardTitle><CardDescription>Scheduled runs and their canonical server status.</CardDescription></CardHeader><CardContent>{activity.isLoading ? <LoadingSkeleton variant="table" /> : activity.isError ? <p className="text-sm text-destructive">Activity is temporarily unavailable.</p> : activity.data?.items.length ? <div className="space-y-2">{activity.data.items.map((entry) => <div key={entry.id} className="flex flex-col gap-1 rounded-lg border border-border/70 p-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-sm font-medium">{entry.name}</p><p className="text-xs text-muted-foreground">{new Date(entry.scheduled_for).toLocaleString("vi-VN", { timeZone: "Asia/Ho_Chi_Minh" })}</p></div><Badge variant={entry.status === "succeeded" ? "success" : entry.status === "failed" ? "danger" : "warning"}>{entry.status}</Badge></div>)}</div> : <p className="text-sm text-muted-foreground">No runs yet. The scheduler will show the first occurrence here.</p>}</CardContent></Card></div>)}
      <SetupDialog item={setupItem} onClose={() => setSetupItem(null)} onInstalled={(installation) => { setSetupItem(null); setView("active"); void queryClient.invalidateQueries({ queryKey: ["workflow-installations", orgId] }); }} />
      <TemplateDetails item={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
