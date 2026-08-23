"use client";

import * as React from "react";
import { toast } from "sonner";
import { Cpu, Plus, Pencil, Trash2, Search } from "lucide-react";
import { useModels, useCreateModel, useDeleteModel, useUpdateModel, useProviders } from "@/hooks";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { ModelForm } from "@/components/models/model-form";
import { ConfirmDialog, ErrorState, LoadingSkeleton } from "@/components/shared";
import type { Model } from "@/types";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export default function ModelsPage() {
  const [open, setOpen] = React.useState(false);
  const [editOpen, setEditOpen] = React.useState(false);
  const [editTarget, setEditTarget] = React.useState<Model | null>(null);
  const [query, setQuery] = React.useState("");
  const [activeFilter, setActiveFilter] = React.useState<string>("all");
  const [providerFilter, setProviderFilter] = React.useState<string>("all");
  const activeOption = activeFilter === "all" ? undefined : activeFilter === "active";
  const providerOption = providerFilter === "all" ? undefined : providerFilter;

  const { data, isLoading, isError, refetch } = useModels(true, {
    withInactive: true,
    active: activeOption,
    provider: providerOption,
    q: query,
  });
  const providers = useProviders(true);
  const create = useCreateModel();
  const del = useDeleteModel();
  const update = useUpdateModel();

  const toggleEnabled = async (model: Model) => {
    try {
      await update.mutateAsync({ id: model.id, enabled: !model.enabled });
      toast.success(`${model.display_name} ${model.enabled ? "disabled" : "enabled"}`);
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader icon={Cpu} title="Models" description="Discover, search, and enable models available to agents" actions={
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild><Button className="gap-2 active-tactile transition-transform"><Plus className="h-4 w-4" /> New Model</Button></DialogTrigger>
          <DialogContent><DialogHeader><DialogTitle>New Model</DialogTitle></DialogHeader><ModelForm providers={providers.data ?? []} onSubmit={async (values) => { try { await create.mutateAsync(values); toast.success("Model created"); setOpen(false); } catch (error: any) { toast.error(error.message); } }} /></DialogContent>
        </Dialog>
      } />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1 max-w-md">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search model name or provider" className="pl-9" aria-label="Search models" />
        </div>

        <div className="flex items-center gap-3">
          <div className="w-40">
            <select
              value={activeFilter}
              onChange={(e) => setActiveFilter(e.target.value)}
              className="flex h-10 w-full cursor-pointer rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground shadow-inner-edge transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Filter by active status"
            >
              <option value="all">All Status</option>
              <option value="active">Active Only</option>
              <option value="inactive">Inactive Only</option>
            </select>
          </div>

          <div className="w-48">
            <select
              value={providerFilter}
              onChange={(e) => setProviderFilter(e.target.value)}
              className="flex h-10 w-full cursor-pointer rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground shadow-inner-edge transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Filter by provider"
            >
              <option value="all">All Providers</option>
              {providers.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name || p.key}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent><DialogHeader><DialogTitle>Edit Model</DialogTitle></DialogHeader>{editTarget && <ModelForm initial={editTarget} providers={providers.data ?? []} onSubmit={async (values) => { try { await update.mutateAsync({ id: editTarget.id, ...values }); toast.success("Model updated"); setEditOpen(false); setEditTarget(null); } catch (error: any) { toast.error(error.message); } }} />}</DialogContent>
      </Dialog>

      {isLoading ? <LoadingSkeleton variant="grid" /> : isError ? <ErrorState title="Unable to load models" description="Model data could not be loaded." onRetry={() => void refetch()} /> : data && data.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 stagger">
          {data.map((model) => {
            const provider = providers.data?.find((item) => item.id === model.provider_id);
            return <Card key={model.id} glass className="card-lift flex flex-col p-5">
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-center gap-3"><div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-primary/25 bg-primary/10 text-primary shadow-inner-edge"><Cpu className="h-5 w-5" /></div><div className="min-w-0"><p className="truncate text-sm font-semibold tracking-tight text-foreground">{model.display_name}</p><p className="mt-0.5 w-fit truncate rounded-md border border-border/30 bg-muted/65 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground/80">{provider ? `${provider.key}/${model.name}` : model.name}</p></div></div>
                <div className="flex items-center gap-1"><Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-foreground" aria-label={`Edit ${model.display_name}`} onClick={() => { setEditTarget(model); setEditOpen(true); }}><Pencil className="h-4 w-4" /></Button><ConfirmDialog trigger={<Button size="icon" variant="ghost" className="h-10 w-10 text-muted-foreground hover:text-destructive" aria-label={`Delete ${model.display_name}`}><Trash2 className="h-4 w-4" /></Button>} title={`Delete ${model.display_name}?`} description="This model configuration will be permanently removed." confirmLabel="Delete model" destructive onConfirm={() => del.mutateAsync(model.id).then(() => undefined)} /></div>
              </div>
              <div className="mt-4 flex flex-wrap gap-1.5"><Badge variant="outline" className="border-border/60 font-mono text-muted-foreground">{provider?.key ?? "provider"}</Badge><Badge variant="outline" className="border-border/60 font-mono text-muted-foreground">{model.tier}</Badge><Badge variant="outline" className="border-border/60 text-muted-foreground">{model.source}</Badge>{model.active ? <Badge variant="success" className="text-[10px] font-semibold uppercase tracking-wider">active</Badge> : <Badge variant="secondary" className="text-[10px] font-semibold uppercase tracking-wider">inactive</Badge>}</div>
              <div className="mt-4 flex items-center justify-between rounded-lg border border-border/50 bg-muted/20 p-2.5"><div><p className="text-xs font-medium">Use in Agent / Chat</p><p className="text-[10px] text-muted-foreground">{model.active ? "Available for selection" : "Not available until active"}</p></div><Button size="sm" variant={model.enabled ? "default" : "outline"} onClick={() => void toggleEnabled(model)}>{model.enabled ? "Enabled" : "Enable"}</Button></div>
              <div className="mt-4 space-y-1.5 border-t border-border/40 pt-3 font-mono text-[11px] text-muted-foreground"><div className="flex justify-between"><span>context:</span><span className="font-semibold text-foreground">{model.context_window.toLocaleString()}</span></div><div className="flex justify-between"><span>input / 1k:</span><span className="font-semibold text-foreground">${model.input_cost_per_1k}</span></div><div className="flex justify-between"><span>output / 1k:</span><span className="font-semibold text-foreground">${model.output_cost_per_1k}</span></div>{model.last_seen_at && <div className="flex justify-between gap-3"><span>last seen:</span><span className="truncate text-foreground">{new Date(model.last_seen_at).toLocaleString()}</span></div>}</div>
            </Card>;
          })}
        </div>
      ) : <EmptyState icon={Cpu} title="No models found" description="Discover models from a provider or register one manually." action={<Button className="gap-2" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> New Model</Button>} />}
    </div>
  );
}
