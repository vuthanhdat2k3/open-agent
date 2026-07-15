"use client";

import * as React from "react";
import { toast } from "sonner";
import { Cpu, Plus, Pencil, Trash2 } from "lucide-react";
import { useModels, useCreateModel, useDeleteModel, useUpdateModel, useProviders } from "@/hooks";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { ModelForm } from "@/components/models/model-form";
import type { Model } from "@/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export default function ModelsPage() {
  const [open, setOpen] = React.useState(false);
  const [editOpen, setEditOpen] = React.useState(false);
  const [editTarget, setEditTarget] = React.useState<Model | null>(null);
  const { data, isLoading } = useModels();
  const providers = useProviders(open);
  const create = useCreateModel();
  const del = useDeleteModel();
  const update = useUpdateModel();

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Cpu}
        title="Models"
        description="Registered models available to agents"
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="gap-2">
                <Plus className="h-4 w-4" /> New Model
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>New Model</DialogTitle>
              </DialogHeader>
              <ModelForm
                providers={providers.data ?? []}
                onSubmit={async (values) => {
                  try {
                    await create.mutateAsync(values);
                    toast.success("Model created");
                    setOpen(false);
                  } catch (e: any) {
                    toast.error(e.message);
                  }
                }}
              />
            </DialogContent>
          </Dialog>
        }
      />

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Model</DialogTitle>
          </DialogHeader>
          {editTarget && (
            <ModelForm
              initial={editTarget}
              providers={providers.data ?? []}
              onSubmit={async (values) => {
                try {
                  await update.mutateAsync({ id: editTarget.id, ...values });
                  toast.success("Model updated");
                  setEditOpen(false);
                  setEditTarget(null);
                } catch (e: any) {
                  toast.error(e.message);
                }
              }}
            />
          )}
        </DialogContent>
      </Dialog>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      ) : data && data.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 stagger">
          {data.map((m) => {
            const provider = providers.data?.find((p) => p.id === m.provider_id);
            return (
              <Card key={m.id} glass className="card-lift flex flex-col p-5">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 text-primary shadow-inner-edge">
                      <Cpu className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-sm tracking-tight">{m.display_name}</p>
                      <p className="truncate font-mono text-[10px] text-muted-foreground/80 mt-0.5 bg-muted/65 px-1.5 py-0.5 rounded border border-border/30 w-fit">{provider ? `${provider.key}/${m.name}` : m.name}</p>
                    </div>
                  </div>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8 text-muted-foreground hover:text-foreground active-tactile transition-transform"
                    aria-label={`Edit ${m.display_name}`}
                    onClick={() => {
                      setEditTarget(m);
                      setEditOpen(true);
                    }}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8 text-muted-foreground hover:text-destructive active-tactile transition-transform"
                    onClick={() => del.mutate(m.id)}
                    aria-label={`Delete ${m.display_name}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <div className="mt-4 flex flex-wrap gap-1.5">
                  {provider && <Badge variant="outline" className="border-border/60 text-muted-foreground">{provider.key}</Badge>}
                  <Badge variant="outline" className="border-border/60 text-muted-foreground">{m.tier}</Badge>
                  {m.active ? (
                    <Badge variant="success" className="gap-1 text-[10px] font-semibold uppercase tracking-wider">active</Badge>
                  ) : (
                    <Badge variant="secondary" className="text-[10px] font-semibold uppercase tracking-wider">inactive</Badge>
                  )}
                </div>
                <div className="mt-4 pt-3 border-t border-border/40 font-mono text-[11px] text-muted-foreground/90 space-y-1">
                  <div className="flex justify-between">
                    <span>context window:</span>
                    <span className="text-foreground font-semibold">{m.context_window.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>input cost / 1k:</span>
                    <span className="text-foreground font-semibold">${m.input_cost_per_1k}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>output cost / 1k:</span>
                    <span className="text-foreground font-semibold">${m.output_cost_per_1k}</span>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        <EmptyState
          icon={Cpu}
          title="No models yet"
          description="Register one under a provider."
          action={
            <Button className="gap-2 active-tactile transition-transform" onClick={() => setOpen(true)}>
              <Plus className="h-4 w-4" /> New Model
            </Button>
          }
        />
      )}
    </div>
  );
}
