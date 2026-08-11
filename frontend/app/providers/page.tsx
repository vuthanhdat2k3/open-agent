"use client";

import * as React from "react";
import { toast } from "sonner";
import { Plus, Server, CheckCircle2, Trash2, Pencil, ArrowLeft } from "lucide-react";
import {
  useProviders,
  useProviderTemplates,
  useCreateProvider,
  useCreateProviderFromTemplate,
  useDeleteProvider,
  useTestProvider,
  useUpdateProvider,
  useHealth,
} from "@/hooks";
import type { Provider, ProviderTemplate } from "@/types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Input, Label } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ProviderForm } from "@/components/providers/provider-form";
import { ConfirmDialog, ErrorState, LoadingSkeleton } from "@/components/shared";

export default function ProvidersPage() {
  const { data, isLoading, isError, refetch } = useProviders();
  const templates = useProviderTemplates();
  const health = useHealth();
  const create = useCreateProvider();
  const createTemplate = useCreateProviderFromTemplate();
  const del = useDeleteProvider();
  const test = useTestProvider();
  const update = useUpdateProvider();
  const [open, setOpen] = React.useState(false);
  const [editOpen, setEditOpen] = React.useState(false);
  const [editTarget, setEditTarget] = React.useState<Provider | null>(null);
  const [selectedTemplate, setSelectedTemplate] = React.useState<ProviderTemplate | null>(null);
  const [templateApiKey, setTemplateApiKey] = React.useState("");
  const [templateBaseUrl, setTemplateBaseUrl] = React.useState("");
  const [advanced, setAdvanced] = React.useState(false);

  const resetTemplate = () => {
    setSelectedTemplate(null);
    setTemplateApiKey("");
    setTemplateBaseUrl("");
    setAdvanced(false);
  };

  const submitTemplate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedTemplate) return;
    try {
      await createTemplate.mutateAsync({
        template_key: selectedTemplate.key,
        api_key: templateApiKey,
        ...(templateBaseUrl.trim() ? { base_url: templateBaseUrl.trim() } : {}),
      });
      toast.success(`${selectedTemplate.display_name} connected and models discovered`);
      resetTemplate();
      setOpen(false);
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Server}
        title="Providers"
        description="Connect model providers using a tested template or custom endpoint"
        actions={
          <Dialog open={open} onOpenChange={(value) => { setOpen(value); if (!value) resetTemplate(); }}>
            <DialogTrigger asChild>
              <Button className="gap-2 active-tactile transition-transform">
                <Plus className="h-4 w-4" /> New Provider
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>{selectedTemplate && selectedTemplate.key !== "custom" ? `Connect ${selectedTemplate.display_name}` : "Choose provider"}</DialogTitle>
              </DialogHeader>
              {selectedTemplate && selectedTemplate.key !== "custom" ? (
                <form className="space-y-4" onSubmit={submitTemplate}>
                  <Button type="button" variant="ghost" className="-ml-2 gap-2" onClick={resetTemplate}>
                    <ArrowLeft className="h-4 w-4" /> Back to templates
                  </Button>
                  <div className="rounded-xl border border-primary/25 bg-primary/5 p-4">
                    <p className="font-semibold">{selectedTemplate.display_name}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{selectedTemplate.description}</p>
                    <p className="mt-3 font-mono text-xs text-muted-foreground">{selectedTemplate.default_base_url}</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="template-api-key">API Key{selectedTemplate.api_key_required ? "" : " (optional)"}</Label>
                    <Input id="template-api-key" type="password" autoComplete="off" value={templateApiKey} onChange={(event) => setTemplateApiKey(event.target.value)} placeholder={selectedTemplate.api_key_required ? "Paste API key" : "Leave empty for local Ollama"} required={selectedTemplate.api_key_required} />
                  </div>
                  <div className="space-y-3 rounded-xl border border-border/60 p-3">
                    <Button type="button" variant="ghost" className="h-auto p-0 text-sm" onClick={() => setAdvanced((value) => !value)}>
                      {advanced ? "Hide advanced settings" : "Show advanced settings"}
                    </Button>
                    {advanced && (
                      <div className="space-y-2">
                        <Label htmlFor="template-base-url">Base URL override</Label>
                        <Input id="template-base-url" value={templateBaseUrl} onChange={(event) => setTemplateBaseUrl(event.target.value)} placeholder={selectedTemplate.default_base_url} className="font-mono text-xs" />
                        {selectedTemplate.key === "ollama" && health.data?.runtime === "docker" && <p className="text-xs text-muted-foreground">When OpenAgent runs in Docker, use http://host.docker.internal:11434/v1 or your Ollama service hostname.</p>}
                      </div>
                    )}
                  </div>
                  <Button type="submit" className="w-full" loading={createTemplate.isPending}>Test & Add Provider</Button>
                </form>
              ) : (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {(templates.data ?? []).map((template) => (
                      <button key={template.key} type="button" className="rounded-xl border border-border/70 p-4 text-left transition-colors hover:border-primary/60 hover:bg-primary/5" onClick={() => setSelectedTemplate(template)}>
                        <p className="font-semibold">{template.display_name}</p>
                        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{template.description}</p>
                        <p className="mt-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground/70">{template.driver}</p>
                      </button>
                    ))}
                  </div>
                  <div className="border-t border-border/60 pt-4">
                    <Button type="button" variant="outline" className="w-full" onClick={() => setSelectedTemplate({ key: "custom", display_name: "Custom provider", description: "OpenAI-compatible custom endpoint", driver: "openai_compatible", default_base_url: "", api_key_required: false, supports_tools: true, supports_reasoning: false, supports_vision: false, catalog_source: "manual", catalog_version: "1" })}>Use custom provider</Button>
                  </div>
                  {selectedTemplate?.key === "custom" && <ProviderForm onSubmit={async (values) => { try { await create.mutateAsync(values); toast.success("Provider created"); setOpen(false); resetTemplate(); } catch (error: any) { toast.error(error.message); } }} />}
                </div>
              )}
            </DialogContent>
          </Dialog>
        }
      />

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit Provider</DialogTitle></DialogHeader>
          {editTarget && <ProviderForm initial={editTarget} onSubmit={async (values) => { try { await update.mutateAsync({ id: editTarget.id, ...values }); toast.success("Provider updated"); setEditOpen(false); setEditTarget(null); } catch (error: any) { toast.error(error.message); } }} />}
        </DialogContent>
      </Dialog>

      {isLoading ? <LoadingSkeleton variant="grid" /> : isError ? <ErrorState title="Unable to load providers" description="Provider data could not be loaded." onRetry={() => void refetch()} /> : data && data.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 stagger">
          {data.map((provider) => (
            <Card key={provider.id} glass className="card-lift flex flex-col p-5">
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-primary/25 bg-primary/10 text-primary shadow-inner-edge"><Server className="h-5 w-5" /></div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold tracking-tight text-foreground">{provider.name}</p>
                    <p className="truncate font-mono text-[10px] text-muted-foreground/70">{provider.key}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {provider.is_default && <Badge variant="success" className="text-[10px]">default</Badge>}
                      {provider.template_key && <Badge variant="outline" className="text-[10px]">{provider.template_key}</Badge>}
                    </div>
                  </div>
                </div>
              </div>
              <div className="mt-4 flex-1 space-y-2 font-mono text-xs text-muted-foreground">
                <div className="truncate rounded-lg border border-border/40 bg-muted/30 px-2.5 py-1.5 select-all shadow-inner-edge">{provider.base_url}</div>
                <div className="flex items-center gap-2 text-[11px]">
                  <span className={provider.api_key_configured ? "text-success" : "text-warning"}>{provider.api_key_configured ? `key: •••• ${provider.api_key_last4 ?? "configured"}` : "key: not configured"}</span>
                </div>
                <div className="flex items-center gap-2 text-[11px]">
                  <Badge variant={provider.discovery_status === "complete" ? "success" : "secondary"} className="text-[10px]">{provider.discovery_status}</Badge>
                  <span>{provider.models_discovered} discovered</span>
                </div>
                {provider.discovery_error && <p className="line-clamp-2 text-[10px] text-warning">{provider.discovery_error}</p>}
              </div>
              <div className="mt-5 flex gap-2 border-t border-border/60 pt-4">
                <Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-foreground active-tactile transition-transform" aria-label={`Edit ${provider.name}`} onClick={() => { setEditTarget(provider); setEditOpen(true); }}><Pencil className="h-4 w-4" /></Button>
                <Button size="sm" variant="outline" className="ml-auto gap-1.5 active-tactile transition-transform" loading={test.isPending} onClick={async () => { try { const result = await test.mutateAsync(provider.id); toast[result.ok ? "success" : "error"](`${result.message} · ${result.model_count} models`); } catch (error: any) { toast.error(error.message); } }}><CheckCircle2 className="h-3.5 w-3.5" /> Test</Button>
                <ConfirmDialog trigger={<Button size="sm" variant="destructive" className="gap-1.5"><Trash2 className="h-3.5 w-3.5" /> Delete</Button>} title={`Delete ${provider.name}?`} description="This provider and its connection settings will be permanently removed." confirmLabel="Delete provider" destructive onConfirm={() => del.mutateAsync(provider.id).then(() => undefined)} />
              </div>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState icon={Server} title="No providers yet" description="Add a provider to start connecting models." action={<Button className="gap-2 active-tactile transition-transform" onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> New Provider</Button>} />
      )}
    </div>
  );
}
