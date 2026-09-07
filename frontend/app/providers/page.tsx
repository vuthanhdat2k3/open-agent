"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Activity,
  ArrowLeft,
  Check,
  CheckCircle2,
  Cpu,
  Eye,
  Layers,
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
  useModelTierMatrix,
  useUpdateModelTierMatrix,
  useUrlSearchParam,
} from "@/hooks";
import type { Model, ModelTier, Provider, ProviderTemplate } from "@/types";
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
  const { t, dict, locale, tx } = useTranslation();
  const [tabParam, setTabParam] = useUrlSearchParam("tab");
  const activeTab = (tabParam as "providers" | "models" | "tier-matrix") || "providers";

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
  const [modelVisionFilter, setModelVisionFilter] = React.useState<string>("all");
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
  const tierMatrix = useModelTierMatrix(true);
  const updateTierMatrix = useUpdateModelTierMatrix();

  const [savingTier, setSavingTier] = React.useState<string | null>(null);

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
      toast.success(tx(`${selectedTemplate.display_name} đã kết nối và phát hiện mô hình`, `${selectedTemplate.display_name} connected and models discovered`));
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
        toast.success(tx(`${model.display_name} đã kích hoạt & sẵn sàng chat!`, `${model.display_name} is active & chat ready!`), {
          description: tx(`Phản hồi: "${res.sample_response || "OK"}" (${res.latency_ms}ms)`, `Response: "${res.sample_response || "OK"}" (${res.latency_ms}ms)`),
        });
      } else {
        toast.error(tx(`Kiểm thử thất bại với ${model.display_name}`, `Test failed for ${model.display_name}`), {
          description: res.message || tx("Không nhận được phản hồi", "No response received"),
        });
      }
    } catch (err: any) {
      toast.error(tx(`Không thể kiểm thử ${model.display_name}`, `Failed to test ${model.display_name}`), {
        description: err.message || tx("Lỗi kết nối", "Connection error"),
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
      if (modelVisionFilter === "vision" && !m.supports_vision) return false;
      if (modelVisionFilter === "non-vision" && m.supports_vision) return false;
      if (modelQuery.trim()) {
        const q = modelQuery.toLowerCase();
        const matchName = m.name.toLowerCase().includes(q);
        const matchDisplay = (m.display_name || "").toLowerCase().includes(q);
        const matchProv = getProviderName(m.provider_id).toLowerCase().includes(q);
        return matchName || matchDisplay || matchProv;
      }
      return true;
    });
  }, [models.data, modelStatusFilter, modelProviderFilter, modelVisionFilter, modelQuery, providers.data]);

  React.useEffect(() => {
    setModelPage(1);
  }, [modelQuery, modelStatusFilter, modelProviderFilter, modelVisionFilter]);

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
        description={tx("Quản lý provider mô hình AI, thông tin xác thực API và endpoint benchmark.", "Manage AI model providers, API credentials, and benchmark endpoints.")}
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
              <RefreshCw className={providers.isFetching || models.isFetching ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />{tx("Làm mới", "Refresh")}</Button>

            {activeTab === "providers" ? (
              <Dialog open={providerModalOpen} onOpenChange={(v) => { setProviderModalOpen(v); if (!v) resetTemplate(); }}>
                <DialogTrigger asChild>
                  <Button size="sm" className="gap-1.5 font-semibold">
                    <Plus className="h-4 w-4" />{tx("Provider mới", "New Provider")}</Button>
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
                        <ArrowLeft className="h-4 w-4" />{tx("Quay lại danh sách mẫu", "Back to templates")}</Button>
                      <div className="rounded-xl border border-primary/25 bg-primary/5 p-4">
                        <p className="font-semibold text-foreground">{selectedTemplate.display_name}</p>
                        <p className="mt-1 text-sm text-muted-foreground">{selectedTemplate.description}</p>
                        <p className="mt-3 font-mono text-xs text-muted-foreground">{selectedTemplate.default_base_url}</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="template-api-key">{tx("API Key", "API Key")}{selectedTemplate.api_key_required ? "" : " (optional)"}</Label>
                        <Input
                          id="template-api-key"
                          type="password"
                          autoComplete="off"
                          value={templateApiKey}
                          onChange={(event) => setTemplateApiKey(event.target.value)}
                          placeholder={selectedTemplate.api_key_required ? tx("Dán API key", "Paste API key") : tx("Bỏ trống cho Ollama cục bộ", "Leave empty for local Ollama")}
                          required={selectedTemplate.api_key_required}
                        />
                      </div>
                      <div className="space-y-3 rounded-xl border border-border/60 p-3">
                        <Button type="button" variant="ghost" className="h-auto p-0 text-sm" onClick={() => setAdvancedTemplate((v) => !v)}>
                          {advancedTemplate ? "Hide advanced settings" : "Show advanced settings"}
                        </Button>
                        {advancedTemplate && (
                          <div className="space-y-2">
                            <Label htmlFor="template-base-url">{tx("Ghi đè Base URL", "Base URL override")}</Label>
                            <Input
                              id="template-base-url"
                              value={templateBaseUrl}
                              onChange={(event) => setTemplateBaseUrl(event.target.value)}
                              placeholder={selectedTemplate.default_base_url}
                              className="font-mono text-xs"
                            />
                            {selectedTemplate.key === "ollama" && health.data?.runtime === "docker" && (
                              <p className="text-xs text-muted-foreground">{tx("Khi OpenAgent chạy trong Docker, sử dụng http://host.docker.internal:11434/v1 hoặc hostname dịch vụ Ollama của bạn.", "When OpenAgent runs in Docker, use http://host.docker.internal:11434/v1 or your Ollama service hostname.")}</p>
                            )}
                          </div>
                        )}
                      </div>
                      <Button type="submit" className="w-full font-semibold" loading={createProviderTemplate.isPending}>{tx("Kiểm tra & Kết nối Provider", "Test & Connect Provider")}</Button>
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
                              display_name: tx("Provider tùy chỉnh", "Custom provider"),
                              description: tx("Endpoint tùy chỉnh tương thích OpenAI", "OpenAI-compatible custom endpoint"),
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
                        >{tx("Sử dụng Custom Provider Endpoint", "Use Custom Provider Endpoint")}</Button>
                      </div>
                      {selectedTemplate?.key === "custom" && (
                        <ProviderForm
                          onSubmit={async (values) => {
                            try {
                              await createProvider.mutateAsync(values);
                              toast.success(tx("Đã tạo Provider", "Provider created"));
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
                    <Plus className="h-4 w-4" />{tx("Model mới", "New Model")}</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>{tx("Thêm Custom Model", "Add Custom Model")}</DialogTitle>
                  </DialogHeader>
                  <ModelForm
                    providers={providers.data ?? []}
                    onSubmit={async (values) => {
                      try {
                        await createModel.mutateAsync(values);
                        toast.success(tx("Đã tạo Model", "Model created"));
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
            <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Provider đã kết nối", "Connected Providers")}</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sky-500/10 text-sky-500">
            <Cpu className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{totalModels}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Model đã khám phá", "Discovered Models")}</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-500/10 text-emerald-500">
            <CheckCircle2 className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{activeModels}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Hoạt động & Sẵn sàng Chat", "Active & Chat-Ready")}</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-500/10 text-amber-500">
            <Activity className="h-5 w-5" />
          </div>
          <div>
            <p className="text-lg font-bold leading-none capitalize text-foreground">{health.data?.runtime || "Docker"}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Môi trường Runtime", "Runtime Environment")}</p>
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
          <Server className="h-4 w-4" />{tx("Providers", "Providers")}<Badge variant="outline" className="ml-1 text-[10px] font-mono">
            {totalProviders}
          </Badge>
        </Button>

        <Button
          type="button"
          variant={activeTab === "models" ? "secondary" : "ghost"}
          onClick={() => setTabParam("models")}
          className="gap-2 font-medium"
        >
          <Cpu className="h-4 w-4" />{tx("Mô hình", "Models")}<Badge variant="outline" className="ml-1 text-[10px] font-mono">
            {totalModels}
          </Badge>
        </Button>

        <Button
          type="button"
          variant={activeTab === "tier-matrix" ? "secondary" : "ghost"}
          onClick={() => setTabParam("tier-matrix")}
          className="gap-2 font-medium"
        >
          <Layers className="h-4 w-4 text-primary" />{dict.pages.providers.tabTierMatrix}
        </Button>
      </div>

      {/* 4. Tab 1: Connected Providers View */}
      {activeTab === "providers" && (
        <div className="space-y-4">
          <Dialog open={editProviderOpen} onOpenChange={setEditProviderOpen}>
            <DialogContent>
              <DialogHeader><DialogTitle>{tx("Sửa đổi Provider", "Edit Provider")}</DialogTitle></DialogHeader>
              {editProviderTarget && (
                <ProviderForm
                  initial={editProviderTarget}
                  onSubmit={async (values) => {
                    try {
                      await updateProvider.mutateAsync({ id: editProviderTarget.id, ...values });
                      toast.success(tx("Đã cập nhật Provider", "Provider updated"));
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
              title={tx("Không thể tải providers", "Unable to load providers")}
              description={tx("Dữ liệu Provider không thể tải được.", "Provider data could not be loaded.")}
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
                            {provider.is_default && <Badge variant="default" className="text-[9.5px]">{tx("Mặc định", "Default")}</Badge>}
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
                      <p className="text-[11px] text-muted-foreground">{tx("Đã khám phá: ", "Discovered: ")}<span className="font-semibold text-foreground">{provider.models_discovered} {tx("mô hình", "models")}</span>
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
                        aria-label={tx(`Sửa ${provider.name}`, `Edit ${provider.name}`)}
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
                              toast[result.ok ? "success" : "error"](tx(`${result.message} · ${result.model_count} mô hình`, `${result.message} · ${result.model_count} models`));
                            } catch (error: any) {
                              toast.error(error.message);
                            }
                          }}
                        >
                          <Zap className="h-3.5 w-3.5 text-amber-500" />{tx("Kiểm tra kết nối", "Test Connection")}</Button>
                        <ConfirmDialog
                          trigger={
                            <Button size="sm" variant="ghost" className="text-destructive hover:bg-destructive/10">
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          }
                          title={tx(`Xóa ${provider.name}?`, `Delete ${provider.name}?`)}
                          description={tx("Tất cả models liên kết với provider này cũng sẽ bị xóa.", "All models associated with this provider will also be removed.")}
                          confirmLabel={tx("Xóa", "Delete")}
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
              title={tx("Chưa kết nối provider nào", "No providers connected yet")}
              description={tx("Kết nối một LLM provider để bắt đầu khám phá models và chạy agents.", "Connect an LLM provider to start discovering models and running agents.")}
              action={
                <Button className="gap-2" onClick={() => setProviderModalOpen(true)}>
                  <Plus className="h-4 w-4" />{tx("Kết nối Provider đầu tiên", "Connect First Provider")}</Button>
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
              <DialogHeader><DialogTitle>{tx("Sửa đổi Model", "Edit Model")}</DialogTitle></DialogHeader>
              {editModelTarget && (
                <ModelForm
                  initial={editModelTarget}
                  providers={providers.data ?? []}
                  onSubmit={async (values) => {
                    try {
                      await updateModel.mutateAsync({ id: editModelTarget.id, ...values });
                      toast.success(tx("Đã cập nhật Model", "Model updated"));
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
                placeholder={tx("Tìm kiếm tên model hoặc provider...", "Search model name or provider...")}
                className="pl-9 text-xs"
                aria-label={tx("Tìm kiếm mô hình", "Search models")}
              />
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              <select
                value={modelStatusFilter}
                onChange={(e) => setModelStatusFilter(e.target.value)}
                className="flex h-9 cursor-pointer rounded-lg border border-border bg-background px-3 py-1 text-xs text-foreground shadow-sm hover:border-primary/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                aria-label={tx("Lọc theo trạng thái hoạt động", "Filter by active status")}
              >
                <option value="all">{tx("Tất cả Trạng thái", "All Status")}</option>
                <option value="active">{tx("Chỉ Hoạt động", "Active Only")}</option>
                <option value="inactive">{tx("Chỉ Không hoạt động", "Inactive Only")}</option>
              </select>

              <select
                value={modelProviderFilter}
                onChange={(e) => setModelProviderFilter(e.target.value)}
                className="flex h-9 cursor-pointer rounded-lg border border-border bg-background px-3 py-1 text-xs text-foreground shadow-sm hover:border-primary/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                aria-label={tx("Lọc theo provider", "Filter by provider")}
              >
                <option value="all">{tx("Tất cả Providers", "All Providers")}</option>
                {(providers.data ?? []).map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>

              <select
                value={modelVisionFilter}
                onChange={(e) => setModelVisionFilter(e.target.value)}
                className="flex h-9 cursor-pointer rounded-lg border border-border bg-background px-3 py-1 text-xs text-foreground shadow-sm hover:border-primary/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                aria-label={tx("Lọc theo khả năng thị giác (Vision)", "Filter by vision capability")}
              >
                <option value="all">{tx("Tất cả Khả năng", "All Capabilities")}</option>
                <option value="vision">{tx("Hỗ trợ Vision (Đọc ảnh)", "Vision Supported")}</option>
                <option value="non-vision">{tx("Chỉ Văn bản (No Vision)", "Text Only (No Vision)")}</option>
              </select>
            </div>
          </div>

          {/* Models Grid */}
          {models.isLoading ? (
            <LoadingSkeleton variant="grid" />
          ) : models.isError ? (
            <ErrorState
              title={tx("Không thể tải models", "Unable to load models")}
              description={tx("Dữ liệu model không thể tải được.", "Model data could not be loaded.")}
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
                        <span>{tx("Cửa sổ ngữ cảnh:", "Context Window:")}</span>
                        <span className="font-semibold text-foreground">{model.context_window ? `${(model.context_window / 1000).toFixed(0)}k` : "Standard"}</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5 pt-1 font-sans">
                        {model.supports_tools && <Badge variant="outline" className="text-[9.5px]">{tx("Công cụ", "Tools")}</Badge>}
                        {model.supports_vision && (
                          <Badge variant="outline" className="gap-1 border-primary/30 bg-primary/10 text-[9.5px] text-primary font-medium">
                            <Eye className="h-2.5 w-2.5" />
                            {tx("Thị giác", "Vision")}
                          </Badge>
                        )}
                        {model.supports_reasoning && <Badge variant="outline" className="text-[9.5px]">{tx("Suy luận", "Reasoning")}</Badge>}
                      </div>
                    </div>

                    <div className="mt-5 flex items-center justify-between gap-2 border-t border-border/60 pt-4">
                      <div className="flex items-center gap-1">
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8 text-muted-foreground hover:text-foreground"
                          aria-label={tx(`Sửa ${model.display_name}`, `Edit ${model.display_name}`)}
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
                          <Zap className="h-3.5 w-3.5 text-amber-500" />{tx("Kiểm tra Chat", "Test Chat")}</Button>
                        <ConfirmDialog
                          trigger={
                            <Button size="sm" variant="ghost" className="text-destructive hover:bg-destructive/10">
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          }
                          title={tx(`Xóa ${model.display_name}?`, `Delete ${model.display_name}?`)}
                          description={tx("Model này sẽ bị xóa khỏi danh mục của bạn.", "This model will be removed from your catalog.")}
                          confirmLabel={tx("Xóa", "Delete")}
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
          ) : (models.data || []).length > 0 ? (
            <EmptyState
              icon={Cpu}
              title={tx("Không tìm thấy mô hình phù hợp", "No matching models found")}
              description={tx("Thử thay đổi bộ lọc trạng thái, provider, hoặc khả năng thị giác (Vision).", "Try adjusting your status, provider, or Vision capability filters.")}
              action={
                <Button
                  variant="outline"
                  className="gap-2"
                  onClick={() => {
                    setModelQuery("");
                    setModelStatusFilter("all");
                    setModelProviderFilter("all");
                    setModelVisionFilter("all");
                  }}
                >
                  <RefreshCw className="h-4 w-4" />
                  {tx("Đặt lại bộ lọc", "Reset Filters")}
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={Cpu}
              title={tx("Không có models nào được khám phá", "No models discovered")}
              description={tx("Kết nối AI Provider hoặc thêm model tùy chỉnh để điền vào danh mục của bạn.", "Connect an AI Provider or add a custom model to populate your catalog.")}
              action={
                <Button className="gap-2" onClick={() => setModelModalOpen(true)}>
                  <Plus className="h-4 w-4" />{tx("Thêm Custom Model", "Add Custom Model")}</Button>
              }
            />
          )}
        </div>
      )}

      {/* 6. Tab 3: Model Tier Matrix Routing View */}
      {activeTab === "tier-matrix" && (
        <div className="space-y-6">
          <Card className="p-6 border-primary/20 bg-primary/[0.02]">
            <div className="flex items-start gap-4">
              <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-primary/10 text-primary">
                <Layers className="h-6 w-6" />
              </div>
              <div className="space-y-1">
                <h3 className="text-lg font-semibold text-foreground">
                  {dict.pages.providers.tierMatrixTitle}
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {dict.pages.providers.tierMatrixDesc}
                </p>
              </div>
            </div>
          </Card>

          {tierMatrix.isLoading ? (
            <LoadingSkeleton />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* Tier 1: Economy */}
              <Card className="flex flex-col justify-between p-5 border-border/80 hover:border-border transition-colors">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20 font-medium">
                      Economy / Fast
                    </Badge>
                    <span className="text-xs text-muted-foreground font-mono">Tier 1</span>
                  </div>
                  <div>
                    <h4 className="font-semibold text-foreground">{dict.pages.providers.tierEconomy}</h4>
                    <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                      {dict.pages.providers.tierEconomyDesc}
                    </p>
                  </div>
                  <div className="space-y-2 pt-2 border-t border-border/60">
                    <Label className="text-xs font-medium text-muted-foreground">{tx("Model đang sử dụng:", "Current Model:")}</Label>
                    <select
                      className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-xs shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      value={tierMatrix.data?.tiers?.economy?.id || ""}
                      disabled={updateTierMatrix.isPending}
                      onChange={async (e) => {
                        const newModelId = e.target.value || null;
                        setSavingTier("economy");
                        try {
                          await updateTierMatrix.mutateAsync({
                            tier_mappings: {
                              economy: newModelId,
                              balanced: tierMatrix.data?.tiers?.balanced?.id || null,
                              frontier: tierMatrix.data?.tiers?.frontier?.id || null,
                            },
                          });
                          toast.success(dict.pages.providers.tierSaveSuccess);
                        } catch (err: any) {
                          toast.error(err.message || tx("Không thể lưu cấu hình", "Failed to save config"));
                        } finally {
                          setSavingTier(null);
                        }
                      }}
                    >
                      <option value="">{dict.pages.providers.tierSelectPlaceholder}</option>
                      {(models.data ?? []).filter((m) => m.active).map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.display_name} ({m.name}) {m.tier ? `· ${m.tier}` : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="mt-6 pt-3 border-t border-border/40 text-[11px] text-muted-foreground flex items-center justify-between">
                  <span>{tx("Áp dụng cho:", "Applies to:")}</span>
                  <span className="font-medium text-foreground">General, Email, Calendar, Drive, Summarizer</span>
                </div>
              </Card>

              {/* Tier 2: Balanced */}
              <Card className="flex flex-col justify-between p-5 border-border/80 hover:border-border transition-colors">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20 font-medium">
                      Balanced / Standard
                    </Badge>
                    <span className="text-xs text-muted-foreground font-mono">Tier 2</span>
                  </div>
                  <div>
                    <h4 className="font-semibold text-foreground">{dict.pages.providers.tierBalanced}</h4>
                    <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                      {dict.pages.providers.tierBalancedDesc}
                    </p>
                  </div>
                  <div className="space-y-2 pt-2 border-t border-border/60">
                    <Label className="text-xs font-medium text-muted-foreground">{tx("Model đang sử dụng:", "Current Model:")}</Label>
                    <select
                      className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-xs shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      value={tierMatrix.data?.tiers?.balanced?.id || ""}
                      disabled={updateTierMatrix.isPending}
                      onChange={async (e) => {
                        const newModelId = e.target.value || null;
                        setSavingTier("balanced");
                        try {
                          await updateTierMatrix.mutateAsync({
                            tier_mappings: {
                              economy: tierMatrix.data?.tiers?.economy?.id || null,
                              balanced: newModelId,
                              frontier: tierMatrix.data?.tiers?.frontier?.id || null,
                            },
                          });
                          toast.success(dict.pages.providers.tierSaveSuccess);
                        } catch (err: any) {
                          toast.error(err.message || tx("Không thể lưu cấu hình", "Failed to save config"));
                        } finally {
                          setSavingTier(null);
                        }
                      }}
                    >
                      <option value="">{dict.pages.providers.tierSelectPlaceholder}</option>
                      {(models.data ?? []).filter((m) => m.active).map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.display_name} ({m.name}) {m.tier ? `· ${m.tier}` : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="mt-6 pt-3 border-t border-border/40 text-[11px] text-muted-foreground flex items-center justify-between">
                  <span>{tx("Áp dụng cho:", "Applies to:")}</span>
                  <span className="font-medium text-foreground">Document Analyst, RAG Researcher, Content Writer</span>
                </div>
              </Card>

              {/* Tier 3: Frontier */}
              <Card className="flex flex-col justify-between p-5 border-border/80 hover:border-border transition-colors">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20 font-medium">
                      Frontier / Reasoning
                    </Badge>
                    <span className="text-xs text-muted-foreground font-mono">Tier 3</span>
                  </div>
                  <div>
                    <h4 className="font-semibold text-foreground">{dict.pages.providers.tierFrontier}</h4>
                    <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                      {dict.pages.providers.tierFrontierDesc}
                    </p>
                  </div>
                  <div className="space-y-2 pt-2 border-t border-border/60">
                    <Label className="text-xs font-medium text-muted-foreground">{tx("Model đang sử dụng:", "Current Model:")}</Label>
                    <select
                      className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-xs shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      value={tierMatrix.data?.tiers?.frontier?.id || ""}
                      disabled={updateTierMatrix.isPending}
                      onChange={async (e) => {
                        const newModelId = e.target.value || null;
                        setSavingTier("frontier");
                        try {
                          await updateTierMatrix.mutateAsync({
                            tier_mappings: {
                              economy: tierMatrix.data?.tiers?.economy?.id || null,
                              balanced: tierMatrix.data?.tiers?.balanced?.id || null,
                              frontier: newModelId,
                            },
                          });
                          toast.success(dict.pages.providers.tierSaveSuccess);
                        } catch (err: any) {
                          toast.error(err.message || tx("Không thể lưu cấu hình", "Failed to save config"));
                        } finally {
                          setSavingTier(null);
                        }
                      }}
                    >
                      <option value="">{dict.pages.providers.tierSelectPlaceholder}</option>
                      {(models.data ?? []).filter((m) => m.active).map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.display_name} ({m.name}) {m.tier ? `· ${m.tier}` : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="mt-6 pt-3 border-t border-border/40 text-[11px] text-muted-foreground flex items-center justify-between">
                  <span>{tx("Áp dụng cho:", "Applies to:")}</span>
                  <span className="font-medium text-foreground">Software Engineer (Coder), Deep Web Researcher, Workflow Manager</span>
                </div>
              </Card>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
