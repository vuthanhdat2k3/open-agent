"use client";

import * as React from "react";
import { toast } from "sonner";
import { Plus, Server, CheckCircle2, Trash2, Pencil } from "lucide-react";
import { useProviders, useCreateProvider, useDeleteProvider, useTestProvider, useUpdateProvider } from "@/hooks";
import type { Provider } from "@/types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ProviderForm } from "@/components/providers/provider-form";

export default function ProvidersPage() {
  const { data, isLoading } = useProviders();
  const create = useCreateProvider();
  const del = useDeleteProvider();
  const test = useTestProvider();
  const update = useUpdateProvider();
  const [open, setOpen] = React.useState(false);
  const [editOpen, setEditOpen] = React.useState(false);
  const [editTarget, setEditTarget] = React.useState<Provider | null>(null);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Server}
        title="Providers"
        description="OpenAI-compatible endpoints that supply models"
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="gap-2 active-tactile transition-transform">
                <Plus className="h-4 w-4" /> New Provider
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>New Provider</DialogTitle>
              </DialogHeader>
              <ProviderForm
                onSubmit={async (values) => {
                  try {
                    await create.mutateAsync(values);
                    toast.success("Provider created");
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
            <DialogTitle>Edit Provider</DialogTitle>
          </DialogHeader>
          {editTarget && (
            <ProviderForm
              initial={editTarget}
              onSubmit={async (values) => {
                try {
                  await update.mutateAsync({ id: editTarget.id, ...values });
                  toast.success("Provider updated");
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
          {data.map((p) => (
            <Card key={p.id} glass className="card-lift flex flex-col p-5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary/25 via-primary/10 to-transparent text-primary shadow-3d-card border border-primary/20">
                    <Server className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-sm tracking-tight text-foreground">{p.name}</p>
                    <p className="truncate font-mono text-[10px] text-muted-foreground/70">{p.key}</p>
                    {p.is_default && (
                      <Badge variant="success" className="mt-1 text-[10px] py-0 px-1.5 uppercase font-semibold tracking-wider">
                        default
                      </Badge>
                    )}
                  </div>
                </div>
              </div>
              
              <div className="mt-4 flex-1 space-y-2 font-mono text-xs text-muted-foreground">
                <div className="truncate rounded-lg border border-border/40 bg-muted/30 px-2.5 py-1.5 select-all shadow-inner-edge">{p.base_url}</div>
                <div className="flex items-center gap-1 text-[11px]">
                  {p.api_key ? (
                    <>
                      <span className="text-muted-foreground/60">key:</span>
                      <span className="rounded bg-muted px-1.5 py-0.5 text-foreground font-medium">
                        •••• {p.api_key.slice(-4)}
                      </span>
                    </>
                  ) : (
                    <>
                      <span className="text-muted-foreground/60">env:</span>
                      <span className="rounded bg-muted px-1.5 py-0.5 text-foreground font-medium">
                        {p.env_var || "—"}
                      </span>
                    </>
                  )}
                </div>
              </div>

              <div className="mt-5 flex gap-2 border-t border-border/60 pt-4">
                <Button
                  size="icon"
                  variant="ghost"
                  className="h-8 w-8 text-muted-foreground hover:text-foreground active-tactile transition-transform"
                  aria-label={`Edit ${p.name}`}
                  onClick={() => {
                    setEditTarget(p);
                    setEditOpen(true);
                  }}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5 active-tactile transition-transform ml-auto"
                  loading={test.isPending}
                  onClick={async () => {
                    const r = await test.mutateAsync(p.id);
                    toast[r.ok ? "success" : "error"](`latency ${r.latency_ms}ms · ${r.model_count} models`);
                  }}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" /> Test
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  className="gap-1.5 active-tactile transition-transform"
                  onClick={() => del.mutate(p.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" /> Delete
                </Button>
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState
          icon={Server}
          title="No providers yet"
          description="Add a provider to start connecting models."
          action={
            <Button className="gap-2 active-tactile transition-transform" onClick={() => setOpen(true)}>
              <Plus className="h-4 w-4" /> New Provider
            </Button>
          }
        />
      )}
    </div>
  );
}
