"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Activity,
  ArrowLeft,
  Check,
  CheckCircle2,
  Cpu,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Server,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import {
  useProviders,
  useProviderTemplates,
  useCreateProvider,
  useCreateProviderFromTemplate,
  useDeleteProvider,
  useTestProvider,
  useUpdateProvider,
  useHealth,
  useModels,
  useCreateModel,
  useDeleteModel,
  useUpdateModel,
  useTestModel,
  useUrlSearchParam,
} from "@/hooks";
import type { Model, Provider, ProviderTemplate } from "@/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, Label } from "@/components/ui/input";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { useTranslation } from "@/lib/i18n";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ProviderForm } from "@/components/providers/provider-form";
import { ModelForm } from "@/components/models/model-form";
import { ConfirmDialog, ErrorState, LoadingSkeleton, DataPagination } from "@/components/shared";

export default function ProvidersPage() {
  const { t, dict, locale } = useTranslation();
  const [tabParam, setTabParam] = useUrlSearchParam("tab");
  const activeTab = (tabParam as "providers" | "models") || "providers";

  // --- Providers State & Queries ---
  const providers = useProviders(true);
  const templates = useProviderTemplates();
  const health = useHealth();
  const createProvider = useCreateProvider();
  const createProviderTemplate = useCreateProviderFromTemplate();
  const deleteProvider = useDeleteProvider();
  const testProvider = useTestProvider();
  const updateProvider = useUpdateProvider();

  const [providerModalOpen, setProviderModalOpen] = React.useState(false);
  const [editProviderOpen, setEditProviderOpen] = React.useState(false);
  const [editProviderTarget, setEditProviderTarget] = React.useState<Provider | null>(null);
  const [selectedTemplate, setSelectedTemplate] = React.useState<ProviderTemplate | null>(null);
  const [templateApiKey, setTemplateApiKey] = React.useState("");
  const [templateBaseUrl, setTemplateBaseUrl] = React.useState("");
  const [advancedTemplate, setAdvancedTemplate] = React.useState(false);

  // --- Models State & Queries ---
  const [modelModalOpen, setModelModalOpen] = React.useState(false);
  const [editModelOpen, setEditModelOpen] = React.useState(false);
  const [editModelTarget, setEditModelTarget] = React.useState<Model | null>(null);
  const [modelQuery, setModelQuery] = React.useState("");
  const [modelStatusFilter, setModelStatusFilter] = React.useState<string>("all");
  const [modelProviderFilter, setModelProviderFilter] = React.useState<string>("all");
  const [testingModelId, setTestingModelId] = React.useState<string | null>(null);

  const activeOption = modelStatusFilter === "all" ? undefined : modelStatusFilter === "active";
  const providerOption = modelProviderFilter === "all" ? undefined : modelProviderFilter;

  const models = useModels(true, {
    withInactive: true,
    active: activeOption,
    provider: providerOption,
    q: modelQuery,
  });

  const createModel = useCreateModel();
  const deleteModel = useDeleteModel();
  const updateModel = useUpdateModel();
  const testModel = useTestModel();

  // Reset template dialog
  const resetTemplate = () => {
    setSelectedTemplate(null);
    setTemplateApiKey("");
    setTemplateBaseUrl("");
    setAdvancedTemplate(false);
  };

  const submitTemplate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedTemplate) return;
    try {
      await createProviderTemplate.mutateAsync({
        template_key: selectedTemplate.key,
        api_key: templateApiKey,
        ...(templateBaseUrl.trim() ? { base_url: templateBaseUrl.trim() } : {}),
      });
      toast.success(`${selectedTemplate.display_name} connected and models discovered`);
      resetTemplate();
      setProviderModalOpen(false);
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  const handleTestModel = async (model: Model) => {
    setTestingModelId(model.id);
    try {
      const res = await testModel.mutateAsync(model.id);
      if (res.ok) {
        toast.success(`${model.display_name} is active & chat ready!`, {
          description: `Response: "${res.sample_response || "OK"}" (${res.latency_ms}ms)`,
        });
      } else {
        toast.error(`Test failed for ${model.display_name}`, {
          description: res.message || "No response received",
        });
      }
    } catch (err: any) {
      toast.error(`Failed to test ${model.display_name}`, {
        description: err.message || "Connection error",
      });
    } finally {
      setTestingModelId(null);
    }
  };

  const toggleModelEnabled = async (model: Model) => {
    try {
      await updateModel.mutateAsync({ id: model.id, enabled: !model.enabled });
      toast.success(`${model.display_name} ${model.enabled ? "disabled" : "enabled"}`);
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  const totalProviders = providers.data?.length ?? 0;
  const totalModels = models.data?.length ?? 0;
  const activeModels = models.data?.filter((m) => m.enabled).length ?? 0;

  // Lookup provider name by ID
  const getProviderName = (providerId: string) => {
    return providers.data?.find((p) => p.id === providerId)?.name || "Provider";
  };

  const [providerPage, setProviderPage] = React.useState(1);
  const [providerPageSize, setProviderPageSize] = React.useState(9);

  const paginatedProviders = React.useMemo(() => {
    const start = (providerPage - 1) * providerPageSize;
    return (providers.data || []).slice(start, start + providerPageSize);
  }, [providers.data, providerPage, providerPageSize]);

  const [modelPage, setModelPage] = React.useState(1);
  const [modelPageSize, setModelPageSize] = React.useState(12);

  const filteredModels = React.useMemo(() => {
    return (models.data || []).filter((m) => {
      if (modelStatusFilter === "active" && !m.enabled) return false;
      if (modelStatusFilter === "inactive" && m.enabled) return false;
      if (modelProviderFilter !== "all" && m.provider_id !== modelProviderFilter) return false;
      if (modelQuery.trim()) {
        const q = modelQuery.toLowerCase();
        const matchName = m.name.toLowerCase().includes(q);
        const matchDisplay = (m.display_name || "").toLowerCase().includes(q);
        const matchProv = getProviderName(m.provider_id).toLowerCase().includes(q);
        return matchName || matchDisplay || matchProv;
      }
      return true;
    });
  }, [models.data, modelStatusFilter, modelProviderFilter, modelQuery, providers.data]);

  React.useEffect(() => {
    setModelPage(1);
  }, [modelQuery, modelStatusFilter, modelProviderFilter]);

  const paginatedModels = React.useMemo(() => {
    const start = (modelPage - 1) * modelPageSize;
    return filteredModels.slice(start, start + modelPageSize);
  }, [filteredModels, modelPage, modelPageSize]);

  return (
    <div className="space-y-6">
      {/* 1. Unified Page Header */}
      <PageHeader
        icon={Server}
        title={dict.pages.providers.title}
        description="Manage AI model providers, API credentials, and benchmark endpoints."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void providers.refetch();
                void models.refetch();
              }}
              disabled={providers.isFetching || models.isFetching}
              className="gap-1.5"
            >
              <RefreshCw className={providers.isFetching || models.isFetching ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
              Refresh
            </Button>

            {activeTab === "providers" ? (
              <Dialog open={providerModalOpen} onOpenChange={(v) => { setProviderModalOpen(v); if (!v) resetTemplate(); }}>
                <DialogTrigger asChild>
                  <Button size="sm" className="gap-1.5 font-semibold">
                    <Plus className="h-4 w-4" /> New Provider
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-2xl">
                  <DialogHeader>
                    <DialogTitle>
                      {selectedTemplate && selectedTemplate.key !== "custom"
                        ? `Connect ${selectedTemplate.display_name}`
                        : "Choose AI Provider Template"}
                    </DialogTitle>
                  </DialogHeader>
                  {selectedTemplate && selectedTemplate.key !== "custom" ? (
                    <form className="space-y-4" onSubmit={submitTemplate}>
                      <Button type="button" variant="ghost" className="-ml-2 gap-2" onClick={resetTemplate}>
                        <ArrowLeft className="h-4 w-4" /> Back to templates
                      </Button>
                      <div className="rounded-xl border border-primary/25 bg-primary/5 p-4">
                        <p className="font-semibold text-foreground">{selectedTemplate.display_name}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{selectedTemplate.description}</p>
                        <p className="mt-3 font-mono text-xs text-muted-foreground">{selectedTemplate.default_base_url}</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="template-api-key">API Key{selectedTemplate.api_key_required ? "" : " (optional)"}</Label>
                        <Input
                          id="template-api-key"
                          type="password"
                          autoComplete="off"
                          value={templateApiKey}
                          onChange={(event) => setTemplateApiKey(event.target.value)}
                          placeholder={selectedTemplate.api_key_required ? "Paste API key" : "Leave empty for local Ollama"}
                          required={selectedTemplate.api_key_required}
                        />
                      </div>
                      <div className="space-y-3 rounded-xl border border-border/60 p-3">
                        <Button type="button" variant="ghost" className="h-auto p-0 text-sm" onClick={() => setAdvancedTemplate((v) => !v)}>
                          {advancedTemplate ? "Hide advanced settings" : "Show advanced settings"}
                        </Button>
                        {advancedTemplate && (
                          <div className="space-y-2">
                            <Label htmlFor="template-base-url">Base URL override</Label>
                            <Input
                              id="template-base-url"
                              value={templateBaseUrl}
                              onChange={(event) => setTemplateBaseUrl(event.target.value)}
                              placeholder={selectedTemplate.default_base_url}
                              className="font-mono text-xs"
                            />
                            {selectedTemplate.key === "ollama" && health.data?.runtime === "docker" && (
                              <p className="text-xs text-muted-foreground">When OpenAgent runs in Docker, use http://host.docker.internal:11434/v1 or your Ollama service hostname.</p>
                            )}
                          </div>
                        )}
                      </div>
                      <Button type="submit" className="w-full font-semibold" loading={createProviderTemplate.isPending}>
                        Test & Connect Provider
                      </Button>
                    </form>
                  ) : (
                    <div className="space-y-4">
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {(templates.data ?? []).map((template) => (
                          <button
                            key={template.key}
                            type="button"
                            className="rounded-xl border border-border/70 p-4 text-left transition-colors hover:border-primary/60 hover:bg-primary/5"
                            onClick={() => setSelectedTemplate(template)}
                          >
                            <p className="font-semibold text-foreground">{template.display_name}</p>
                            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{template.description}</p>
                            <p className="mt-3 font-mono text-[10px] uppercase tracking-wider text-primary">{template.driver}</p>
                          </button>
                        ))}
                      </div>
                      <div className="border-t border-border/60 pt-4">
                        <Button
                          type="button"
                          variant="outline"
                          className="w-full"
                          onClick={() =>
                            setSelectedTemplate({
                              key: "custom",
                              display_name: "Custom provider",
                              description: "OpenAI-compatible custom endpoint",
                              driver: "openai_compatible",
                              default_base_url: "",
                              api_key_required: false,
                              supports_tools: true,
                              supports_reasoning: false,
                              supports_vision: false,
                              catalog_source: "manual",
                              catalog_version: "1",
                            })
                          }
                        >
                          Use Custom Provider Endpoint
                        </Button>
                      </div>
                      {selectedTemplate?.key === "custom" && (
                        <ProviderForm
                          onSubmit={async (values) => {
                            try {
                              await createProvider.mutateAsync(values);
                              toast.success("Provider created");
                              setProviderModalOpen(false);
                              resetTemplate();
                            } catch (error: any) {
                              toast.error(error.message);
                            }
                          }}
                        />
                      )}
                    </div>
                  )}
                </DialogContent>
              </Dialog>
            ) : (
              <Dialog open={modelModalOpen} onOpenChange={setModelModalOpen}>
                <DialogTrigger asChild>
                  <Button size="sm" className="gap-1.5 font-semibold">
                    <Plus className="h-4 w-4" /> New Model
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Add Custom Model</DialogTitle>
                  </DialogHeader>
                  <ModelForm
                    providers={providers.data ?? []}
                    onSubmit={async (values) => {
                      try {
                        await createModel.mutateAsync(values);
                        toast.success("Model created");
                        setModelModalOpen(false);
                      } catch (error: any) {
                        toast.error(error.message);
                      }
                    }}
                  />
                </DialogContent>
              </Dialog>
            )}
          </div>
        }
      />

      {/* 2. Executive Metrics Ribbon */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <Server className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{totalProviders}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">Connected Providers</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sky-500/10 text-sky-500">
            <Cpu className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{totalModels}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">Discovered Models</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-500/10 text-emerald-500">
            <CheckCircle2 className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{activeModels}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">Active & Chat-Ready</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-500/10 text-amber-500">
            <Activity className="h-5 w-5" />
          </div>
          <div>
            <p className="text-lg font-bold leading-none capitalize text-foreground">{health.data?.runtime || "Docker"}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">Runtime Environment</p>
          </div>
        </Card>
      </div>

      {/* 3. Navigation Segmented Tabs */}
      <div className="flex gap-2 border-b border-border/70 pb-2">
        <Button
          type="button"
          variant={activeTab === "providers" ? "secondary" : "ghost"}
          onClick={() => setTabParam("providers")}
          className="gap-2 font-medium"
        >
          <Server className="h-4 w-4" />
          Providers
          <Badge variant="outline" className="ml-1 text-[10px] font-mono">
            {totalProviders}
          </Badge>
        </Button>

        <Button
          type="button"
          variant={activeTab === "models" ? "secondary" : "ghost"}
          onClick={() => setTabParam("models")}
          className="gap-2 font-medium"
        >
          <Cpu className="h-4 w-4" />
          Models
          <Badge variant="outline" className="ml-1 text-[10px] font-mono">
            {totalModels}
          </Badge>
        </Button>
      </div>

      {/* 4. Tab 1: Connected Providers View */}
      {activeTab === "providers" && (
        <div className="space-y-4">
          <Dialog open={editProviderOpen} onOpenChange={setEditProviderOpen}>
            <DialogContent>
              <DialogHeader><DialogTitle>Edit Provider</DialogTitle></DialogHeader>
              {editProviderTarget && (
                <ProviderForm
                  initial={editProviderTarget}
                  onSubmit={async (values) => {
                    try {
                      await updateProvider.mutateAsync({ id: editProviderTarget.id, ...values });
                      toast.success("Provider updated");
                      setEditProviderOpen(false);
                      setEditProviderTarget(null);
                    } catch (error: any) {
                      toast.error(error.message);
                    }
                  }}
                />
              )}
            </DialogContent>
          </Dialog>

          {providers.isLoading ? (
            <LoadingSkeleton variant="grid" />
          ) : providers.isError ? (
            <ErrorState
              title="Unable to load providers"
              description="Provider data could not be loaded."
              onRetry={() => void providers.refetch()}
            />
          ) : providers.data && providers.data.length > 0 ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {paginatedProviders.map((provider) => (
                  <Card key={provider.id} className="shadow-card flex flex-col p-5 border-border/80 transition-colors hover:border-primary/40">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-3">
                        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-primary/25 bg-primary/10 text-primary">
                          <Server className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold tracking-tight text-foreground">{provider.name}</p>
                          <p className="truncate font-mono text-[10px] text-muted-foreground">{provider.key}</p>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {provider.is_default && <Badge variant="default" className="text-[9.5px]">Default</Badge>}
                            {provider.template_key && <Badge variant="outline" className="text-[9.5px]">{provider.template_key}</Badge>}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 flex-1 space-y-2 font-mono text-xs text-muted-foreground">
                      <div className="truncate rounded-lg border border-border/50 bg-muted/30 px-2.5 py-1.5 select-all">
                        {provider.base_url}
                      </div>
                      <div className="flex items-center justify-between text-[11px]">
                        <span className={provider.api_key_configured ? "text-emerald-500 font-medium" : "text-amber-500 font-medium"}>
                          {provider.api_key_configured ? `API Key: •••• ${provider.api_key_last4 ?? "active"}` : "No API key"}
                        </span>
                        <Badge variant={provider.discovery_status === "complete" ? "default" : "outline"} className="text-[9.5px]">
                          {provider.discovery_status}
                        </Badge>
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        Discovered: <span className="font-semibold text-foreground">{provider.models_discovered} models</span>
                      </p>
                      {provider.discovery_error && (
                        <p className="line-clamp-2 text-[10px] text-destructive">{provider.discovery_error}</p>
                      )}
                    </div>

                    <div className="mt-5 flex items-center justify-between gap-2 border-t border-border/60 pt-4">
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8 text-muted-foreground hover:text-foreground"
                        aria-label={`Edit ${provider.name}`}
                        onClick={() => {
                          setEditProviderTarget(provider);
                          setEditProviderOpen(true);
                        }}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <div className="flex items-center gap-1.5">
                        <Button
                          size="sm"
                          variant="outline"
                          className="gap-1.5"
                          loading={testProvider.isPending}
                          onClick={async () => {
                            try {
                              const result = await testProvider.mutateAsync(provider.id);
                              toast[result.ok ? "success" : "error"](`${result.message} · ${result.model_count} models`);
                            } catch (error: any) {
                              toast.error(error.message);
                            }
                          }}
                        >
                          <Zap className="h-3.5 w-3.5 text-amber-500" /> Test Connection
                        </Button>
                        <ConfirmDialog
                          trigger={
                            <Button size="sm" variant="ghost" className="text-destructive hover:bg-destructive/10">
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          }
                          title={`Delete ${provider.name}?`}
                          description="All models associated with this provider will also be removed."
                          confirmLabel="Delete"
                          destructive
                          onConfirm={() => deleteProvider.mutate(provider.id)}
                        />
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
              <DataPagination
                page={providerPage}
                pageSize={providerPageSize}
                totalItems={providers.data.length}
                onPageChange={setProviderPage}
                onPageSizeChange={setProviderPageSize}
                pageSizeOptions={[6, 9, 18, 36]}
              />
            </div>
          ) : (
            <EmptyState
              icon={Server}
              title="No providers connected yet"
              description="Connect an LLM provider to start discovering models and running agents."
              action={
                <Button className="gap-2" onClick={() => setProviderModalOpen(true)}>
                  <Plus className="h-4 w-4" /> Connect First Provider
                </Button>
              }
            />
          )}
        </div>
      )}

      {/* 5. Tab 2: Models Catalog & Testing View */}
      {activeTab === "models" && (
        <div className="space-y-4">
          <Dialog open={editModelOpen} onOpenChange={setEditModelOpen}>
            <DialogContent>
              <DialogHeader><DialogTitle>Edit Model</DialogTitle></DialogHeader>
              {editModelTarget && (
                <ModelForm
                  initial={editModelTarget}
                  providers={providers.data ?? []}
                  onSubmit={async (values) => {
                    try {
                      await updateModel.mutateAsync({ id: editModelTarget.id, ...values });
                      toast.success("Model updated");
                      setEditModelOpen(false);
                      setEditModelTarget(null);
                    } catch (error: any) {
                      toast.error(error.message);
                    }
                  }}
                />
              )}
            </DialogContent>
          </Dialog>

          {/* Model Filters Bar */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative flex-1 max-w-md">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={modelQuery}
                onChange={(event) => setModelQuery(event.target.value)}
                placeholder="Search model name or provider..."
                className="pl-9 text-xs"
                aria-label="Search models"
              />
            </div>

            <div className="flex items-center gap-2.5">
              <select
                value={modelStatusFilter}
                onChange={(e) => setModelStatusFilter(e.target.value)}
                className="flex h-9 cursor-pointer rounded-lg border border-border bg-background px-3 py-1 text-xs text-foreground shadow-sm hover:border-primary/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                aria-label="Filter by active status"
              >
                <option value="all">All Status</option>
                <option value="active">Active Only</option>
                <option value="inactive">Inactive Only</option>
              </select>

              <select
                value={modelProviderFilter}
                onChange={(e) => setModelProviderFilter(e.target.value)}
                className="flex h-9 cursor-pointer rounded-lg border border-border bg-background px-3 py-1 text-xs text-foreground shadow-sm hover:border-primary/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                aria-label="Filter by provider"
              >
                <option value="all">All Providers</option>
                {(providers.data ?? []).map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Models Grid */}
          {models.isLoading ? (
            <LoadingSkeleton variant="grid" />
          ) : models.isError ? (
            <ErrorState
              title="Unable to load models"
              description="Model data could not be loaded."
              onRetry={() => void models.refetch()}
            />
          ) : filteredModels.length > 0 ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {paginatedModels.map((model) => (
                  <Card key={model.id} className="shadow-card flex flex-col p-5 border-border/80 transition-colors hover:border-primary/40">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex min-w-0 items-start gap-3">
                        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-sky-500/25 bg-sky-500/10 text-sky-500">
                          <Cpu className="h-5 w-5" />
                        </div>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold tracking-tight text-foreground">{model.display_name}</p>
                          <p className="truncate font-mono text-[10.5px] text-muted-foreground">{model.name}</p>
                          <div className="mt-1 flex flex-wrap gap-1">
                            <Badge variant={model.enabled ? "default" : "outline"} className="text-[9.5px]">
                              {model.enabled ? "Enabled" : "Disabled"}
                            </Badge>
                            <Badge variant="outline" className="text-[9.5px] font-mono">
                              {getProviderName(model.provider_id)}
                            </Badge>
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 flex-1 space-y-2 text-xs text-muted-foreground font-mono">
                      <div className="flex items-center justify-between rounded-lg border border-border/50 bg-muted/20 px-2.5 py-1.5 text-[11px]">
                        <span>Context Window:</span>
                        <span className="font-semibold text-foreground">{model.context_window ? `${(model.context_window / 1000).toFixed(0)}k` : "Standard"}</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5 pt-1 font-sans">
                        {model.supports_tools && <Badge variant="outline" className="text-[9.5px]">Tools</Badge>}
                        {model.supports_vision && <Badge variant="outline" className="text-[9.5px]">Vision</Badge>}
                        {model.supports_reasoning && <Badge variant="outline" className="text-[9.5px]">Reasoning</Badge>}
                      </div>
                    </div>

                    <div className="mt-5 flex items-center justify-between gap-2 border-t border-border/60 pt-4">
                      <div className="flex items-center gap-1">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8 text-muted-foreground hover:text-foreground"
                          aria-label={`Edit ${model.display_name}`}
                          onClick={() => {
                            setEditModelTarget(model);
                            setEditModelOpen(true);
                          }}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="text-xs text-muted-foreground hover:text-foreground"
                          onClick={() => toggleModelEnabled(model)}
                        >
                          {model.enabled ? "Disable" : "Enable"}
                        </Button>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <Button
                          size="sm"
                          variant="outline"
                          className="gap-1.5"
                          loading={testingModelId === model.id}
                          onClick={() => handleTestModel(model)}
                        >
                          <Zap className="h-3.5 w-3.5 text-amber-500" /> Test Chat
                        </Button>
                        <ConfirmDialog
                          trigger={
                            <Button size="sm" variant="ghost" className="text-destructive hover:bg-destructive/10">
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          }
                          title={`Delete ${model.display_name}?`}
                          description="This model will be removed from your catalog."
                          confirmLabel="Delete"
                          destructive
                          onConfirm={() => deleteModel.mutate(model.id)}
                        />
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
              <DataPagination
                page={modelPage}
                pageSize={modelPageSize}
                totalItems={filteredModels.length}
                onPageChange={setModelPage}
                onPageSizeChange={setModelPageSize}
                pageSizeOptions={[6, 12, 24, 48]}
              />
            </div>
          ) : (
            <EmptyState
              icon={Cpu}
              title="No models discovered"
              description="Connect an AI Provider or add a custom model to populate your catalog."
              action={
                <Button className="gap-2" onClick={() => setModelModalOpen(true)}>
                  <Plus className="h-4 w-4" /> Add Custom Model
                </Button>
              }
            />
          )}
        </div>
      )}
    </div>
  );
}
