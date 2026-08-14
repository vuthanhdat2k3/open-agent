"use client";

import * as React from "react";
import { useDeferredValue, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
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
import { getWorkflowCatalog, type WorkflowCatalogItem } from "@/lib/automations/api";
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

function TemplateCard({ item, onOpen }: { item: WorkflowCatalogItem; onOpen: (item: WorkflowCatalogItem) => void }) {
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
          <Button type="button" size="sm" variant={item.capabilities.can_install ? "default" : "outline"} disabled={!item.capabilities.can_install} aria-label={item.capabilities.can_install ? `Set up ${item.name}` : `${item.name} preview only`}>{item.capabilities.can_install ? <>Set up <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" /></> : "Preview only"}</Button>
        </div>
      </CardContent>
    </Card>
  );
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
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [selected, setSelected] = useState<WorkflowCatalogItem | null>(null);
  const deferredSearch = useDeferredValue(search);
  const orgId = getActiveOrgId();
  const catalog = useQuery({
    queryKey: ["workflow-catalog", orgId, deferredSearch, category],
    queryFn: () => getWorkflowCatalog({ query: deferredSearch, category }),
    staleTime: 60_000,
  });
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
          <h2 className="flex items-center gap-2 text-lg font-semibold"><LibraryBig className="h-4 w-4" aria-hidden="true" />Discover workflows</h2>
          <p className="mt-1 text-sm text-muted-foreground">Choose a routine by the result you want, not by technical configuration.</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative"><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden="true" /><Input aria-label="Search workflows" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search workflows" className="w-full pl-9 sm:w-56" /></div>
          <select aria-label="Filter workflows by category" value={category} onChange={(event) => setCategory(event.target.value)} className="h-10 rounded-lg border border-border bg-background px-3 text-sm text-foreground shadow-inner-edge focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            {categories.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </div>
      </div>
      {catalog.isLoading ? <LoadingSkeleton variant="grid" /> : catalog.isError ? <ErrorState title="Unable to load workflows" description="The workflow catalog could not be loaded." onRetry={() => void catalog.refetch()} /> : items.length === 0 ? <EmptyState icon={LibraryBig} title="No workflows found" description="Try clearing your search or category filter." action={<Button type="button" variant="outline" onClick={() => { setSearch(""); setCategory(""); }}>Clear filters</Button>} /> : <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 stagger">{items.map((item) => <TemplateCard key={`${item.key}-${item.version}`} item={item} onOpen={setSelected} />)}</div>}
      <TemplateDetails item={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
