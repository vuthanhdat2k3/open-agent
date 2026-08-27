"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Bot,
  Plus,
  Wrench,
  Cpu,
  Thermometer,
  RotateCcw,
  History,
  Search,
  Upload,
  Sparkles,
  Save,
  CheckCircle2,
  SlidersHorizontal,
  Box,
  Layers,
  ShieldCheck,
  RefreshCw,
} from "lucide-react";
import {
  useAgents,
  useAgentTools,
  useModels,
  useCreateAgent,
  useDeleteAgent,
  useUpdateAgent,
  useAgentReleases,
  useCreateAgentRelease,
  usePublishAgentRelease,
  useRollbackAgentRelease,
  useUrlSearchParam,
} from "@/hooks";
import {
  getCompanionConfig,
  saveCompanionConfig,
  AVATAR_3D_PRESETS,
  type CompanionConfig,
} from "@/lib/operator/companion-config";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { useTranslation } from "@/lib/i18n";
import { EmptyState, ErrorState, LoadingSkeleton, DataPagination } from "@/components/shared";
import { AgentCard } from "@/components/agents/agent-card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import type { Agent, AgentToolInfo } from "@/types";

type AgentForm = {
  name: string;
  description: string;
  system_prompt: string;
  model_id: string;
  kind: "worker" | "orchestrator";
  max_iterations: number;
  temperature: number;
  enable_thinking: boolean | null;
  allowed_risk_tiers: string[];
};

const DEFAULT_FORM: AgentForm = {
  name: "",
  description: "",
  system_prompt: "",
  model_id: "",
  kind: "worker",
  max_iterations: 12,
  temperature: 0.7,
  enable_thinking: null,
  allowed_risk_tiers: ["safe", "read"],
};

const TOOL_GROUPS: Record<string, string> = {
  customer: "Customer intelligence",
  memory: "Memory",
  workspace: "Workspace & files",
  execution: "Execution",
  research: "Web & research",
  agents: "Agents & delegation",
  knowledge: "Knowledge & MCP",
  other: "Other tools",
};

function toolGroup(name: string): string {
  if (/^(email_|calendar_|drive_|company_|news_)/.test(name)) return "customer";
  if (/memory|save_memory|call_memory/.test(name)) return "memory";
  if (/^(write_file|list_dir|search_files|read_attachment|workspace_)/.test(name)) return "workspace";
  if (/^(run_shell|run_code|sandbox_)/.test(name)) return "execution";
  if (/^(web_|rag_)/.test(name)) return name.startsWith("rag_") ? "knowledge" : "research";
  if (/^(call_agent|call_external_agent)/.test(name)) return "agents";
  if (name.startsWith("mcp:")) return "knowledge";
  return "other";
}

const RISK_TIERS = [
  { key: "safe", label: "Safe", description: "No side effects" },
  { key: "read", label: "Read", description: "Read data and files" },
  { key: "write", label: "Write", description: "Create or change data" },
  { key: "network", label: "Network", description: "Outbound network calls" },
  { key: "execute", label: "Execute", description: "Run sandboxed code" },
  { key: "dangerous", label: "Dangerous", description: "High-impact operations" },
] as const;

export default function AgentsPage() {
  const { t, dict, locale } = useTranslation();
  const [tabParam, setTabParam] = useUrlSearchParam("tab");
  const activeTab = (tabParam as "catalog" | "companion") || "catalog";

  const { data, isLoading, isError, refetch } = useAgents();
  const tools = useAgentTools();
  const models = useModels();
  const create = useCreateAgent();
  const del = useDeleteAgent();
  const update = useUpdateAgent();

  const [open, setOpen] = React.useState(false);
  const [editingAgent, setEditingAgent] = React.useState<Agent | null>(null);
  const [form, setForm] = React.useState<AgentForm>(DEFAULT_FORM);
  const [selectedTools, setSelectedTools] = React.useState<string[]>([]);
  const [search, setSearch] = React.useState("");
  const [catalogSearch, setCatalogSearch] = React.useState("");
  const [kindFilter, setKindFilter] = React.useState<"all" | "orchestrator" | "worker">("all");

  // Release Management state
  const [releaseAgent, setReleaseAgent] = React.useState<Agent | null>(null);
  const [draftPrompt, setDraftPrompt] = React.useState("");
  const [changeNote, setChangeNote] = React.useState("");
  const releases = useAgentReleases(releaseAgent?.id ?? null);
  const createRelease = useCreateAgentRelease();
  const publishRelease = usePublishAgentRelease();
  const rollbackRelease = useRollbackAgentRelease();

  // 3D Companion Configuration state
  const [companionConfig, setCompanionConfig] = React.useState<CompanionConfig>(getCompanionConfig());
  const [isSavingCompanion, setIsSavingCompanion] = React.useState(false);
  const previewViewerRef = React.useRef<any>(null);

  React.useEffect(() => {
    setCompanionConfig(getCompanionConfig());
  }, []);

  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(12);

  const filteredAgents = React.useMemo(() => {
    return (data || []).filter((a) => {
      if (kindFilter !== "all" && a.kind !== kindFilter) return false;
      if (catalogSearch.trim()) {
        const q = catalogSearch.toLowerCase();
        const matchName = a.name.toLowerCase().includes(q);
        const matchDesc = (a.description || "").toLowerCase().includes(q);
        const matchTools = (a.tools || []).some((t) => t.toLowerCase().includes(q));
        return matchName || matchDesc || matchTools;
      }
      return true;
    });
  }, [data, kindFilter, catalogSearch]);

  React.useEffect(() => {
    setPage(1);
  }, [catalogSearch, kindFilter]);

  const paginatedAgents = React.useMemo(() => {
    const start = (page - 1) * pageSize;
    return filteredAgents.slice(start, start + pageSize);
  }, [filteredAgents, page, pageSize]);

  const handleSaveCompanion = () => {
    setIsSavingCompanion(true);
    try {
      saveCompanionConfig(companionConfig);
      toast.success((locale === "vi" ? "Cài đặt Avatar & Operator Đồng hành 3D đã được lưu thành công!" : "3D Companion Avatar & Operator settings saved successfully!"));
    } catch (err: any) {
      toast.error(err.message || (locale === "vi" ? "Lưu cài đặt đồng hành thất bại" : "Failed to save companion settings"));
    } finally {
      setIsSavingCompanion(false);
    }
  };

  const groupedTools = React.useMemo(() => {
    const map: Record<string, AgentToolInfo[]> = {};
    for (const tool of tools.data ?? []) {
      if (search && !tool.name.toLowerCase().includes(search.toLowerCase())) continue;
      const group = toolGroup(tool.name);
      (map[group] ??= []).push(tool);
    }
    return map;
  }, [tools.data, search]);

  const openEdit = (agent: Agent) => {
    setEditingAgent(agent);
    setForm({
      name: agent.name,
      description: agent.description,
      system_prompt: agent.system_prompt,
      model_id: agent.model_id,
      kind: agent.kind ?? "worker",
      max_iterations: agent.max_iterations ?? 12,
      temperature: agent.temperature ?? 0.7,
      enable_thinking: agent.enable_thinking ?? null,
      allowed_risk_tiers: agent.allowed_risk_tiers ?? ["safe", "read"],
    });
    setSelectedTools(agent.tools ?? []);
    setOpen(true);
  };

  const openCreate = () => {
    setEditingAgent(null);
    setForm({ ...DEFAULT_FORM, model_id: models.data?.[0]?.id ?? "" });
    setSelectedTools([]);
    setOpen(true);
  };

  const openReleases = (agent: Agent) => {
    setReleaseAgent(agent);
    setDraftPrompt(agent.system_prompt);
    setChangeNote("");
  };

  const handleCreateDraft = async () => {
    if (!releaseAgent) return;
    try {
      await createRelease.mutateAsync({
        agentId: releaseAgent.id,
        system_prompt: draftPrompt,
        change_note: changeNote,
      });
      setChangeNote("");
      toast.success((locale === "vi" ? "Bản nháp phát hành đã được tạo" : "Draft release created"));
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  const handlePublish = async (version: number) => {
    if (!releaseAgent) return;
    try {
      await publishRelease.mutateAsync({ agentId: releaseAgent.id, version });
      toast.success(locale === "vi" ? `Phiên bản ${version} đã được xuất bản` : `Version ${version} published`);
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  const handleRollback = async (version: number) => {
    if (!releaseAgent) return;
    try {
      const release = await rollbackRelease.mutateAsync({
        agentId: releaseAgent.id,
        version,
      });
      toast.success(locale === "vi" ? `Đã khôi phục về phiên bản ${release.version}` : `Rolled back as version ${release.version}`);
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  const toggleTool = (t: string) =>
    setSelectedTools((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));

  const toggleRiskTier = (tier: string) =>
    setForm((current) => ({
      ...current,
      allowed_risk_tiers: current.allowed_risk_tiers.includes(tier)
        ? current.allowed_risk_tiers.filter((item) => item !== tier)
        : [...current.allowed_risk_tiers, tier],
    }));

  const handleSubmit = async () => {
    try {
      if (editingAgent) {
        await update.mutateAsync({ id: editingAgent.id, ...form, tools: selectedTools });
        toast.success((locale === "vi" ? "Agent đã được cập nhật" : "Agent updated"));
      } else {
        await create.mutateAsync({ ...form, tools: selectedTools });
        toast.success((locale === "vi" ? "Agent đã được tạo" : "Agent created"));
      }
      setOpen(false);
      setEditingAgent(null);
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const riskColor: Record<string, string> = {
    safe: "border-muted-foreground/40 bg-muted/30 text-muted-foreground",
    read: "border-info/50 bg-info/10 text-info",
    write: "border-warning/50 bg-warning/10 text-warning",
    execute: "border-warning/50 bg-warning/10 text-warning",
    network: "border-info/50 bg-info/10 text-info",
    dangerous: "border-destructive/50 bg-destructive/10 text-destructive",
  };

  return (
    <div className="space-y-6">
      {/* 1. Page Header */}
      <PageHeader
        icon={Bot}
        title={dict.pages.agents.title}
        description={locale === "vi" ? "Cấu hình AI agents, lời nhắc suy luận hệ thống, mô hình và kiểm soát truy cập công cụ." : "Configure AI agents, system reasoning prompts, models, and tool access control."}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void refetch()}
              disabled={isLoading}
              className="gap-1.5"
            >
              <RefreshCw className={isLoading ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
              {locale === "vi" ? "Làm mới" : "Refresh"}
            </Button>
            {activeTab === "catalog" && (
              <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) setEditingAgent(null); }}>
                <DialogTrigger asChild>
                  <Button size="sm" className="gap-1.5 font-semibold" onClick={openCreate}>
                    <Plus className="h-4 w-4" /> {locale === "vi" ? "Agent mới" : "New Agent"}
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle>{editingAgent ? (locale === "vi" ? "Chỉnh sửa Agent" : "Edit Agent") : (locale === "vi" ? "Tạo Agent" : "Create Agent")}</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 pt-2">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{locale === "vi" ? "Tên" : "Name"}</Label>
                        <Input
                          value={form.name}
                          onChange={(e) => setForm({ ...form, name: e.target.value })}
                          placeholder={locale === "vi" ? "vd: Code Reviewer" : "e.g. Code Reviewer"}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{locale === "vi" ? "Loại" : "Kind"}</Label>
                        <Select
                          value={form.kind}
                          onChange={(e) => setForm({ ...form, kind: e.target.value as "worker" | "orchestrator" })}
                        >
                          <option value="worker">{locale === "vi" ? "Công nhân" : "Worker"}</option>
                          <option value="orchestrator">{locale === "vi" ? "Điều phối viên" : "Orchestrator"}</option>
                        </Select>
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{locale === "vi" ? "Mô tả" : "Description"}</Label>
                      <Input
                        value={form.description}
                        onChange={(e) => setForm({ ...form, description: e.target.value })}
                        placeholder={locale === "vi" ? "Tóm tắt ngắn gọn các khả năng..." : "Brief summary of capabilities..."}
                      />
                    </div>

                    <div className="grid gap-3 sm:grid-cols-3">
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{locale === "vi" ? "Công cụ Mô hình" : "Model Engine"}</Label>
                        <Select
                          value={form.model_id}
                          onChange={(e) => setForm({ ...form, model_id: e.target.value })}
                        >
                          <option value="">{locale === "vi" ? "Mô hình mặc định" : "Default Model"}</option>
                          {models.data?.map((m) => (
                            <option key={m.id} value={m.id}>
                              {m.display_name || m.name}
                            </option>
                          ))}
                        </Select>
                      </div>

                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                            <Thermometer className="h-3.5 w-3.5" /> {locale === "vi" ? "Nhiệt độ" : "Temp"}
                          </Label>
                          <span className="font-mono text-xs text-foreground font-semibold">{form.temperature}</span>
                        </div>
                        <div className="pt-2">
                          <Slider
                            value={[form.temperature]}
                            min={0}
                            max={2}
                            step={0.1}
                            onValueChange={([v]) => setForm({ ...form, temperature: v })}
                          />
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                          <Sparkles className="h-3.5 w-3.5" /> {locale === "vi" ? "Suy luận" : "Thinking"}
                        </Label>
                        <Select
                          value={form.enable_thinking === null ? "default" : String(form.enable_thinking)}
                          onChange={(e) => setForm({ ...form, enable_thinking: e.target.value === "default" ? null : e.target.value === "true" })}
                        >
                          <option value="default">{locale === "vi" ? "Mặc định model" : "Model default"}</option>
                          <option value="true">{locale === "vi" ? "Bật" : "Enabled"}</option>
                          <option value="false">{locale === "vi" ? "Tắt" : "Disabled"}</option>
                        </Select>
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{locale === "vi" ? "Lời nhắc hệ thống" : "System Prompt"}</Label>
                      <Textarea
                        value={form.system_prompt}
                        onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
                        rows={5}
                        placeholder={locale === "vi" ? "Bạn là một trợ lý hữu ích..." : "You are a helpful assistant..."}
                        className="font-mono text-xs"
                      />
                    </div>

                    <div className="space-y-2">
                      <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{locale === "vi" ? "Mức độ rủi ro cho phép" : "Allowed Risk Tiers"}</Label>
                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                        {RISK_TIERS.map((tier) => {
                          const active = form.allowed_risk_tiers.includes(tier.key);
                          return (
                            <button
                              key={tier.key}
                              type="button"
                              onClick={() => toggleRiskTier(tier.key)}
                              className={`rounded-lg border p-2 text-left text-xs transition-colors ${
                                active ? "border-primary bg-primary/10" : "border-border bg-background/50 hover:border-primary/40"
                              }`}
                            >
                              <p className="font-semibold text-foreground">{tier.label}</p>
                              <p className="text-[10px] text-muted-foreground">{tier.description}</p>
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                          <Wrench className="h-3.5 w-3.5 text-primary" /> {locale === "vi" ? `Công cụ (${selectedTools.length} đã chọn)` : `Tools (${selectedTools.length} selected)`}
                        </Label>
                        <div className="relative w-48">
                          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                          <Input
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder={locale === "vi" ? "Lọc công cụ..." : "Filter tools..."}
                            className="h-7 pl-8 text-[11px]"
                          />
                        </div>
                      </div>

                      <div className="max-h-[240px] space-y-3 overflow-y-auto rounded-xl border border-border/40 bg-muted/10 p-3">
                        {Object.entries(groupedTools).map(([group, items]) => (
                          <section key={group} className="space-y-2">
                            <div className="flex items-center gap-2 border-b border-border/40 pb-1.5">
                              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{TOOL_GROUPS[group] ?? group}</span>
                              <span className="text-[10px] text-muted-foreground/60">{items.length}</span>
                            </div>
                            <div className="grid gap-2 sm:grid-cols-2">
                              {items.map((tool) => {
                                const selected = selectedTools.includes(tool.name);
                                const tierAllowed = !tool.risk_tier || form.allowed_risk_tiers.includes(tool.risk_tier);
                                const disabled = (!tool.available || !tierAllowed) && !selected;
                                return (
                                  <button
                                    key={tool.name}
                                    type="button"
                                    disabled={disabled}
                                    onClick={() => toggleTool(tool.name)}
                                    className={`flex min-w-0 items-start justify-between gap-2 rounded-lg border p-2 text-left transition-colors ${
                                      selected ? "border-primary/50 bg-primary/10" : "border-border/50 bg-background/30 hover:border-primary/30"
                                    } ${disabled ? "cursor-not-allowed opacity-45" : ""}`}
                                  >
                                    <span className="min-w-0">
                                      <span className="block truncate font-mono text-[11px] font-medium">{tool.name}</span>
                                      <span className="mt-0.5 block line-clamp-1 text-[10px] text-muted-foreground">{tool.description}</span>
                                    </span>
                                    <span className="flex shrink-0 flex-col items-end gap-1">
                                      {tool.risk_tier && (
                                        <span className={`rounded px-1 text-[9px] font-mono uppercase ${riskColor[tool.risk_tier] ?? "border-border text-muted-foreground"}`}>
                                          {tool.risk_tier}
                                        </span>
                                      )}
                                      {!tool.available && (
                                        <span className="rounded bg-muted px-1 text-[9px] text-muted-foreground">
                                          {locale === "vi" ? "Không khả dụng" : "Unavailable"}
                                        </span>
                                      )}
                                    </span>
                                  </button>
                                );
                              })}
                            </div>
                          </section>
                        ))}
                      </div>
                    </div>

                    <div className="flex justify-end gap-2 pt-2">
                      <Button variant="outline" size="sm" onClick={() => setOpen(false)}>
                        {locale === "vi" ? "Hủy" : "Cancel"}
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleSubmit}
                        disabled={create.isPending || update.isPending || !form.name.trim()}
                        className="font-semibold"
                      >
                        {editingAgent ? (locale === "vi" ? "Lưu thay đổi" : "Save Changes") : (locale === "vi" ? "Tạo Agent" : "Create Agent")}
                      </Button>
                    </div>
                  </div>
                </DialogContent>
              </Dialog>
            )}
          </div>
        }
      />

      {/* 2. Segmented Navigation Tabs */}
      <div className="flex gap-2 border-b border-border/70 pb-2">
        <Button
          type="button"
          variant={activeTab === "catalog" ? "secondary" : "ghost"}
          onClick={() => setTabParam("catalog")}
          className="gap-2 font-medium"
        >
          <Bot className="h-4 w-4" />
          {locale === "vi" ? "Danh mục Agent" : "Agent Catalog"}
          <Badge variant="outline" className="ml-1 text-[10px] font-mono">
            {data?.length ?? 0}
          </Badge>
        </Button>

        <Button
          type="button"
          variant={activeTab === "companion" ? "secondary" : "ghost"}
          onClick={() => setTabParam("companion")}
          className="gap-2 font-medium"
        >
          <Sparkles className="h-4 w-4 text-amber-500" />
          {locale === "vi" ? "Đồng hành 3D" : "3D Companion"}
        </Button>
      </div>

      {/* 3. Tab 1: Agent Personas & Catalog */}
      {activeTab === "catalog" && (
        <div className="space-y-5">
          {/* KPI Ribbon */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Card className="flex items-center gap-3.5 p-4 shadow-card">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
                <Bot className="h-5 w-5" />
              </div>
              <div>
                <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{data?.length ?? 0}</p>
                <p className="mt-1 text-xs text-muted-foreground font-medium">{locale === "vi" ? "Agent đã cấu hình" : "Configured Agents"}</p>
              </div>
            </Card>

            <Card className="flex items-center gap-3.5 p-4 shadow-card">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sky-500/10 text-sky-500">
                <Layers className="h-5 w-5" />
              </div>
              <div>
                <p className="text-2xl font-bold leading-none tabular-nums text-foreground">
                  {data?.filter((a) => a.kind === "orchestrator").length ?? 0}
                </p>
                <p className="mt-1 text-xs text-muted-foreground font-medium">{locale === "vi" ? "Điều phối viên" : "Orchestrators"}</p>
              </div>
            </Card>

            <Card className="flex items-center gap-3.5 p-4 shadow-card">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-500/10 text-emerald-500">
                <Cpu className="h-5 w-5" />
              </div>
              <div>
                <p className="text-2xl font-bold leading-none tabular-nums text-foreground">
                  {data?.filter((a) => a.kind === "worker").length ?? 0}
                </p>
                <p className="mt-1 text-xs text-muted-foreground font-medium">{locale === "vi" ? "Chuyên gia Công nhân" : "Worker Specialists"}</p>
              </div>
            </Card>

            <Card className="flex items-center gap-3.5 p-4 shadow-card">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-500/10 text-amber-500">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{models.data?.length ?? 0}</p>
                <p className="mt-1 text-xs text-muted-foreground font-medium">{locale === "vi" ? "Công cụ LLM đang hoạt động" : "Active LLM Engines"}</p>
              </div>
            </Card>
          </div>

          {/* Search & Kind Filters */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative flex-1 max-w-md">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={catalogSearch}
                onChange={(e) => setCatalogSearch(e.target.value)}
                placeholder={dict.pages.agents.searchPlaceholder}
                className="pl-9 text-xs"
              />
            </div>

            <div className="flex rounded-lg border border-border bg-muted/30 p-0.5">
              <Button
                size="sm"
                variant={kindFilter === "all" ? "secondary" : "ghost"}
                className="h-7 text-xs font-medium"
                onClick={() => setKindFilter("all")}
              >
                {locale === "vi" ? `Tất cả (${data?.length ?? 0})` : `All (${data?.length ?? 0})`}
              </Button>
              <Button
                size="sm"
                variant={kindFilter === "orchestrator" ? "secondary" : "ghost"}
                className="h-7 text-xs font-medium"
                onClick={() => setKindFilter("orchestrator")}
              >
                {locale === "vi" ? `Điều phối viên (${data?.filter((a) => a.kind === "orchestrator").length ?? 0})` : `Orchestrators (${data?.filter((a) => a.kind === "orchestrator").length ?? 0})`}
              </Button>
              <Button
                size="sm"
                variant={kindFilter === "worker" ? "secondary" : "ghost"}
                className="h-7 text-xs font-medium"
                onClick={() => setKindFilter("worker")}
              >
                {locale === "vi" ? `Công nhân (${data?.filter((a) => a.kind === "worker").length ?? 0})` : `Workers (${data?.filter((a) => a.kind === "worker").length ?? 0})`}
              </Button>
            </div>
          </div>

          <Dialog open={Boolean(releaseAgent)} onOpenChange={(v) => { if (!v) setReleaseAgent(null); }}>
            <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{locale === "vi" ? "Releases —" : "Releases —"}{releaseAgent?.name}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-2">
                <div className="space-y-2 rounded-xl border border-border/60 bg-muted/20 p-4">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{locale === "vi" ? "Bản nháp phát hành mới" : "New Release Draft"}</Label>
                  <Textarea
                    value={draftPrompt}
                    onChange={(e) => setDraftPrompt(e.target.value)}
                    rows={4}
                    className="font-mono text-xs"
                    placeholder={locale === "vi" ? "Lời nhắc hệ thống cho bản phát hành này..." : "System prompt for this release..."}
                  />
                  <Input
                    value={changeNote}
                    onChange={(e) => setChangeNote(e.target.value)}
                    placeholder={locale === "vi" ? "Ghi chú thay đổi (vd: Đã thêm suy luận nhiều bước)" : "Change note (e.g. Added multi-step reasoning)"}
                    className="text-xs"
                  />
                  <Button size="sm" onClick={handleCreateDraft} disabled={createRelease.isPending || !draftPrompt}>
                    {locale === "vi" ? "Tạo Phiên bản Nháp" : "Create Draft Version"}
                  </Button>
                </div>

                <div className="space-y-2">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{locale === "vi" ? "Lịch sử phiên bản" : "Version History"}</Label>
                  {releases.data?.map((release) => (
                    <div key={release.id} className="flex items-center justify-between gap-3 rounded-lg border border-border/70 p-3 text-xs">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground font-mono">v{release.version}</span>
                          <Badge variant={release.status === "published" ? "default" : "outline"} className="text-[9.5px]">
                            {release.status}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">{release.change_note || (locale === "vi" ? "Không có ghi chú" : "No note")}</p>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {release.status === "draft" && (
                          <Button size="sm" onClick={() => handlePublish(release.version)} disabled={publishRelease.isPending} className="text-xs h-7">
                            <Upload className="h-3 w-3 mr-1" /> {locale === "vi" ? "Xuất bản" : "Publish"}
                          </Button>
                        )}
                        {release.status === "archived" && (
                          <Button size="sm" variant="outline" onClick={() => handleRollback(release.version)} disabled={rollbackRelease.isPending} className="text-xs h-7">
                            <RotateCcw className="h-3 w-3 mr-1" /> {locale === "vi" ? "Khôi phục" : "Rollback"}
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </DialogContent>
          </Dialog>

          {isLoading ? (
            <LoadingSkeleton variant="grid" />
          ) : isError ? (
            <ErrorState
              title={locale === "vi" ? "Không thể tải agent" : "Unable to load agents"}
              description={locale === "vi" ? "Không thể truy xuất dữ liệu danh mục agent." : "Agent catalog data could not be retrieved."}
              onRetry={() => void refetch()}
            />
          ) : filteredAgents.length > 0 ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {paginatedAgents.map((a) => (
                  <AgentCard
                    key={a.id}
                    agent={a}
                    models={models.data}
                    tools={tools.data}
                    onEdit={openEdit}
                    onReleases={openReleases}
                    onDelete={(id) => del.mutate(id)}
                  />
                ))}
              </div>
              <DataPagination
                page={page}
                pageSize={pageSize}
                totalItems={filteredAgents.length}
                onPageChange={setPage}
                onPageSizeChange={setPageSize}
                pageSizeOptions={[6, 12, 24, 48]}
              />
            </div>
          ) : (
            <EmptyState
              icon={Bot}
              title={locale === "vi" ? "Không có agent nào khớp với tiêu chí của bạn" : "No agents match your criteria"}
              description={locale === "vi" ? "Hãy thử điều chỉnh truy vấn tìm kiếm hoặc bộ lọc vai trò của bạn." : "Try adjusting your search query or role filter."}
              action={
                <Button className="gap-2" onClick={openCreate}>
                  <Plus className="h-4 w-4" /> {locale === "vi" ? "Agent mới" : "New Agent"}
                </Button>
              }
            />
          )}
        </div>
      )}

      {/* 4. Tab 2: 3D Companion Avatar & Operator Settings */}
      {activeTab === "companion" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Left Column: Live 3D Avatar Preview Box */}
          <Card className="shadow-card border-border/80 lg:col-span-1 flex flex-col p-5 bg-gradient-to-b from-card via-card to-primary/[0.04]">
            <CardHeader className="p-0 pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <Box className="h-4 w-4 text-primary" /> {locale === "vi" ? "Xem trước Avatar 3D trực tiếp" : "Live 3D Avatar Preview"}
              </CardTitle>
              <CardDescription className="text-xs">
                {locale === "vi" ? "Kết xuất hình ảnh trực tiếp của avatar đồng hành cho người dùng cuối." : "Real-time visual rendering of the companion avatar for end-users."}
              </CardDescription>
            </CardHeader>

            <CardContent className="p-0 flex-1 flex flex-col items-center justify-center pt-2">
              {/* Simulated 3D Avatar Container with HUD Ring */}
              <div className="relative h-64 w-full flex items-center justify-center">
                {/* Simulated Floating Thought Bubble */}
                {companionConfig.showThoughtBubbles && (
                  <div className="animate-bounce-subtle absolute top-2 z-10 flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-card/95 px-3 py-1 text-[10px] font-medium text-amber-500 shadow-md">
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                    <span>{locale === "vi" ? "⚡ 2 actions need your review →" : "⚡ 2 actions need your review →"}</span>
                  </div>
                )}

                {/* Simulated 3D Model HUD */}
                <div className="relative h-56 w-56">
                  <svg className="pointer-events-none absolute inset-0 animate-spin-slow opacity-65" viewBox="0 0 200 200" fill="none" stroke="currentColor">
                    <circle cx="100" cy="100" r="94" stroke="currentColor" className="text-primary" strokeWidth="1" strokeDasharray="4 8" opacity="0.6" />
                    <circle cx="100" cy="100" r="86" stroke="currentColor" className="text-primary" strokeWidth="1.5" strokeDasharray="24 16 8 16" opacity="0.8" />
                    <circle cx="100" cy="100" r="76" stroke="currentColor" className="text-sky-400" strokeWidth="0.8" strokeDasharray="6 12" opacity="0.5" />
                  </svg>

                  <div className="h-full w-full">
                    {/* @ts-ignore */}
                    <model-viewer
                      ref={previewViewerRef}
                      src={companionConfig.modelUrl || "/agent-service-robot.glb"}
                      alt="3D Companion Preview"
                      camera-orbit="0deg 75deg 2.2m"
                      field-of-view="24deg"
                      auto-rotate
                      rotation-per-second="15deg"
                      style={{ width: "100%", height: "100%", background: "transparent" }}
                    />
                  </div>
                </div>

                {/* Status Pill Preview */}
                <div className="absolute bottom-2 flex items-center gap-2 rounded-full border border-border/90 bg-card/95 px-3 py-1 text-xs text-muted-foreground shadow-sm backdrop-blur-md">
                  <span className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_#10b981]" />
                  <span className="font-semibold text-foreground">{companionConfig.name || (locale === "vi" ? "Người điều hành Cá nhân" : "Personal Operator")}</span>
                  <span className="font-mono text-[10.5px] text-primary font-medium">{locale === "vi" ? "ready" : "ready"}</span>
                </div>
              </div>

              <div className="w-full mt-4 border-t border-border/60 pt-3 text-center text-xs text-muted-foreground">
                <p className="font-medium text-foreground">{companionConfig.name}</p>
                <p className="text-[11px] text-muted-foreground">{companionConfig.tagline}</p>
              </div>
            </CardContent>
          </Card>

          {/* Right Column: Companion Configuration Form */}
          <Card className="shadow-card border-border/80 lg:col-span-2 p-6 space-y-6">
            <div className="flex items-center justify-between border-b border-border/60 pb-4">
              <div>
                <h2 className="text-base font-semibold text-foreground flex items-center gap-2">
                  <SlidersHorizontal className="h-5 w-5 text-primary" /> {locale === "vi" ? "3D Companion & Executive Operator Config" : "3D Companion & Executive Operator Config"}</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  {locale === "vi" ? "Operators and Org Admins configure this persona to maintain, develop, and customize the live assistant for users." : "Operators and Org Admins configure this persona to maintain, develop, and customize the live assistant for users."}</p>
              </div>
              <Button
                className="gap-2 font-semibold"
                onClick={handleSaveCompanion}
                loading={isSavingCompanion}
              >
                <Save className="h-4 w-4" /> {locale === "vi" ? "Save Configuration" : "Save Configuration"}</Button>
            </div>

            <div className="space-y-5">
              {/* Section A: Identity & Brain Binding */}
              <div className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-primary">
                  {locale === "vi" ? "1. Identity & Brain Persona Binding" : "1. Identity & Brain Persona Binding"}</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs font-medium">{locale === "vi" ? "Companion Display Name" : "Companion Display Name"}</Label>
                    <Input
                      value={companionConfig.name}
                      onChange={(e) => setCompanionConfig({ ...companionConfig, name: e.target.value })}
                      placeholder={locale === "vi" ? "e.g. Personal Operator, Executive Chief of Staff" : "e.g. Personal Operator, Executive Chief of Staff"}
                      className="text-xs"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-medium">{locale === "vi" ? "Tagline / Role Description" : "Tagline / Role Description"}</Label>
                    <Input
                      value={companionConfig.tagline}
                      onChange={(e) => setCompanionConfig({ ...companionConfig, tagline: e.target.value })}
                      placeholder={locale === "vi" ? "e.g. Personal Executive Chief of Staff" : "e.g. Personal Executive Chief of Staff"}
                      className="text-xs"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">{locale === "vi" ? "Underlying Brain Agent (Studio Agent Persona)" : "Underlying Brain Agent (Studio Agent Persona)"}</Label>
                  <Select
                    value={companionConfig.brainAgentId || ""}
                    onChange={(e) => setCompanionConfig({ ...companionConfig, brainAgentId: e.target.value || null })}
                    className="text-xs"
                  >
                    <option value="">{locale === "vi" ? "Default Organization Orchestrator" : "Default Organization Orchestrator"}</option>
                    {data?.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} — {a.description || "Active Agent Persona"}
                      </option>
                    ))}
                  </Select>
                  <p className="text-[11px] text-muted-foreground">
                    {locale === "vi" ? "When users send prompts or dispatch actions to the 3D Companion, this agent persona and its system prompts will process the request." : "When users send prompts or dispatch actions to the 3D Companion, this agent persona and its system prompts will process the request."}</p>
                </div>
              </div>

              {/* Section B: 3D Avatar Asset Model */}
              <div className="space-y-3 border-t border-border/60 pt-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-primary">
                  {locale === "vi" ? "2. 3D Model Asset & Visual Avatar" : "2. 3D Model Asset & Visual Avatar"}</h3>

                <div className="grid gap-3 sm:grid-cols-3">
                  {AVATAR_3D_PRESETS.map((preset) => {
                    const isSelected =
                      preset.id === "custom"
                        ? companionConfig.modelUrl !== "/agent-service-robot.glb" &&
                          companionConfig.modelUrl !== "https://modelviewer.dev/shared-assets/models/Astronaut.glb"
                        : companionConfig.modelUrl === preset.url;
                    return (
                      <button
                        key={preset.id}
                        type="button"
                        onClick={() => {
                          if (preset.url) {
                            setCompanionConfig({ ...companionConfig, modelUrl: preset.url });
                          }
                        }}
                        className={`rounded-xl border p-3.5 text-left transition-all ${
                          isSelected
                            ? "border-primary bg-primary/10 shadow-sm ring-1 ring-primary/30"
                            : "border-border/80 bg-card hover:border-border hover:bg-muted/30"
                        }`}
                      >
                        <p className="text-xs font-semibold text-foreground">{preset.name}</p>
                        <p className="mt-1 text-[10.5px] text-muted-foreground leading-relaxed">
                          {preset.description}
                        </p>
                      </button>
                    );
                  })}
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">{locale === "vi" ? "Custom 3D Model Asset URL (.glb / .gltf)" : "Custom 3D Model Asset URL (.glb / .gltf)"}</Label>
                  <Input
                    value={companionConfig.modelUrl}
                    onChange={(e) => setCompanionConfig({ ...companionConfig, modelUrl: e.target.value })}
                    placeholder={locale === "vi" ? "/agent-service-robot.glb or https://your-cdn.com/avatar.glb" : "/agent-service-robot.glb or https://your-cdn.com/avatar.glb"}
                    className="text-xs font-mono"
                  />
                </div>
              </div>

              {/* Section C: Docking Position & Screen Placement */}
              <div className="space-y-3 border-t border-border/60 pt-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-primary">
                  {locale === "vi" ? "3. Default Screen Placement & Docking" : "3. Default Screen Placement & Docking"}</h3>
                <div className="grid gap-3 sm:grid-cols-4">
                  {[
                    { id: "bottom-right", label: "Bottom-Right (Default)" },
                    { id: "middle-right", label: "Middle-Right" },
                    { id: "top-right", label: "Top-Right" },
                    { id: "bottom-left", label: "Bottom-Left" },
                  ].map((pos) => {
                    const isSelected = companionConfig.defaultPosition === pos.id;
                    return (
                      <button
                        key={pos.id}
                        type="button"
                        onClick={() =>
                          setCompanionConfig({
                            ...companionConfig,
                            defaultPosition: pos.id as any,
                          })
                        }
                        className={`rounded-lg border p-2.5 text-center text-xs font-medium transition-all ${
                          isSelected
                            ? "border-primary bg-primary/10 text-foreground font-semibold"
                            : "border-border/70 bg-card hover:bg-muted/40 text-muted-foreground"
                        }`}
                      >
                        {pos.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Section D: Feature Toggles & Capabilities */}
              <div className="space-y-3 border-t border-border/60 pt-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-primary">
                  {locale === "vi" ? "4. Interactive Capabilities & Surface Controls" : "4. Interactive Capabilities & Surface Controls"}</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="flex items-center gap-2.5 rounded-lg border border-border/70 p-3 text-xs text-foreground cursor-pointer hover:bg-muted/30">
                    <input
                      type="checkbox"
                      checked={companionConfig.showThoughtBubbles}
                      onChange={(e) => setCompanionConfig({ ...companionConfig, showThoughtBubbles: e.target.checked })}
                      className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                    />
                    <div>
                      <p className="font-semibold">{locale === "vi" ? "Live Thought Bubble Alerts" : "Live Thought Bubble Alerts"}</p>
                      <p className="text-[10px] text-muted-foreground">{locale === "vi" ? "Show urgent action notifications above avatar head" : "Show urgent action notifications above avatar head"}</p>
                    </div>
                  </label>

                  <label className="flex items-center gap-2.5 rounded-lg border border-border/70 p-3 text-xs text-foreground cursor-pointer hover:bg-muted/30">
                    <input
                      type="checkbox"
                      checked={companionConfig.enableApprovals}
                      onChange={(e) => setCompanionConfig({ ...companionConfig, enableApprovals: e.target.checked })}
                      className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                    />
                    <div>
                      <p className="font-semibold">{locale === "vi" ? "1-Click Technical Approvals" : "1-Click Technical Approvals"}</p>
                      <p className="text-[10px] text-muted-foreground">{locale === "vi" ? "Allow instant approving from floating operator surface" : "Allow instant approving from floating operator surface"}</p>
                    </div>
                  </label>

                  <label className="flex items-center gap-2.5 rounded-lg border border-border/70 p-3 text-xs text-foreground cursor-pointer hover:bg-muted/30">
                    <input
                      type="checkbox"
                      checked={companionConfig.enableEmailTriage}
                      onChange={(e) => setCompanionConfig({ ...companionConfig, enableEmailTriage: e.target.checked })}
                      className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                    />
                    <div>
                      <p className="font-semibold">{locale === "vi" ? "Email Triage Feed" : "Email Triage Feed"}</p>
                      <p className="text-[10px] text-muted-foreground">{locale === "vi" ? "Expose incoming classified emails in operator surface" : "Expose incoming classified emails in operator surface"}</p>
                    </div>
                  </label>

                  <label className="flex items-center gap-2.5 rounded-lg border border-border/70 p-3 text-xs text-foreground cursor-pointer hover:bg-muted/30">
                    <input
                      type="checkbox"
                      checked={companionConfig.enableDirectPrompt}
                      onChange={(e) => setCompanionConfig({ ...companionConfig, enableDirectPrompt: e.target.checked })}
                      className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                    />
                    <div>
                      <p className="font-semibold">{locale === "vi" ? "Direct Operator Dispatch" : "Direct Operator Dispatch"}</p>
                      <p className="text-[10px] text-muted-foreground">{locale === "vi" ? "Enable natural language command dispatch bar" : "Enable natural language command dispatch bar"}</p>
                    </div>
                  </label>
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
