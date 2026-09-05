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
  Scaling,
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
  COMPANION_SCALE_PRESETS,
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
import { useTranslation, statusLabel } from "@/lib/i18n";
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

// Each value is a [vi, en] pair; resolve with tx() at render time.
const TOOL_GROUPS: Record<string, [string, string]> = {
  customer: ["Thông tin khách hàng", "Customer intelligence"],
  memory: ["Bộ nhớ", "Memory"],
  workspace: ["Không gian làm việc & tệp", "Workspace & files"],
  execution: ["Thực thi", "Execution"],
  research: ["Web & nghiên cứu", "Web & research"],
  agents: ["Agent & ủy quyền", "Agents & delegation"],
  knowledge: ["Kiến thức & MCP", "Knowledge & MCP"],
  other: ["Tool khác", "Other tools"],
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

export default function AgentsPage() {
  const { t, dict, locale, tx } = useTranslation();
  const toolGroupLabel = (group: string) => {
    const pair = TOOL_GROUPS[group];
    return pair ? tx(pair[0], pair[1]) : group;
  };
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
      toast.success(tx("Đã lưu cấu hình Trợ lý 3D & Operator", "3D Companion & Operator settings saved successfully"));
    } catch (err: any) {
      toast.error(err.message || (tx("Lưu cài đặt đồng hành thất bại", "Failed to save companion settings")));
    } finally {
      setIsSavingCompanion(false);
    }
  };

  const ORCHESTRATOR_ALLOWED_TOOLS = React.useMemo(
    () =>
      new Set([
        "call_agent",
        "workflow_list",
        "get_current_time",
        "save_memory",
        "call_memory",
        "memory_store",
        "memory_recall",
        "call_external_agent",
      ]),
    []
  );

  const groupedTools = React.useMemo(() => {
    const map: Record<string, AgentToolInfo[]> = {};
    for (const tool of tools.data ?? []) {
      if (search && !tool.name.toLowerCase().includes(search.toLowerCase())) continue;
      if (form.kind === "orchestrator") {
        const isAllowed = tool.allowed_for_orchestrator ?? ORCHESTRATOR_ALLOWED_TOOLS.has(tool.name);
        if (!isAllowed) continue;
      } else if (form.kind === "worker") {
        const isProhibited = tool.allowed_for_worker === false || tool.name === "call_agent";
        if (isProhibited) continue;
      }
      const group = toolGroup(tool.name);
      (map[group] ??= []).push(tool);
    }
    return map;
  }, [tools.data, search, form.kind, ORCHESTRATOR_ALLOWED_TOOLS]);

  const handleKindChange = (newKind: "worker" | "orchestrator") => {
    setForm((prev) => ({ ...prev, kind: newKind }));
    if (newKind === "orchestrator") {
      setSelectedTools((prev) => {
        const valid = prev.filter((t) => ORCHESTRATOR_ALLOWED_TOOLS.has(t));
        return valid.length > 0 ? valid : ["call_agent", "workflow_list", "get_current_time", "save_memory", "call_memory"];
      });
    } else {
      setSelectedTools((prev) => prev.filter((t) => t !== "call_agent"));
    }
  };

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
      toast.success((tx("Bản nháp phát hành đã được tạo", "Draft release created")));
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  const handlePublish = async (version: number) => {
    if (!releaseAgent) return;
    try {
      await publishRelease.mutateAsync({ agentId: releaseAgent.id, version });
      toast.success(tx(`Đã phát hành phiên bản ${version}`, `Version ${version} published`));
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
      toast.success(tx(`Đã khôi phục về phiên bản ${release.version}`, `Rolled back as version ${release.version}`));
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  const toggleTool = (t: string) =>
    setSelectedTools((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));

  const handleSubmit = async () => {
    try {
      if (editingAgent) {
        await update.mutateAsync({ id: editingAgent.id, ...form, tools: selectedTools });
        toast.success((tx("Agent đã được cập nhật", "Agent updated")));
      } else {
        await create.mutateAsync({ ...form, tools: selectedTools });
        toast.success((tx("Agent đã được tạo", "Agent created")));
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
        description={tx("Cấu hình AI agent, prompt hệ thống, mô hình và quyền truy cập công cụ.", "Configure AI agents, system prompts, models, and tool access control.")}
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
              {tx("Làm mới", "Refresh")}
            </Button>
            {activeTab === "catalog" && (
              <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) setEditingAgent(null); }}>
                <DialogTrigger asChild>
                  <Button size="sm" className="gap-1.5 font-semibold" onClick={openCreate}>
                    <Plus className="h-4 w-4" /> {tx("Agent mới", "New Agent")}
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                  <DialogHeader>
                    <DialogTitle>{editingAgent ? (tx("Chỉnh sửa Agent", "Edit Agent")) : (tx("Tạo Agent", "Create Agent"))}</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 pt-2">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{tx("Tên", "Name")}</Label>
                        <Input
                          value={form.name}
                          onChange={(e) => setForm({ ...form, name: e.target.value })}
                          placeholder={tx("vd: Code Reviewer", "e.g. Code Reviewer")}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{tx("Loại", "Kind")}</Label>
                        <Select
                          value={form.kind}
                          onChange={(e) => handleKindChange(e.target.value as "worker" | "orchestrator")}
                        >
                          <option value="worker">{tx("Công nhân", "Worker")}</option>
                          <option value="orchestrator">{tx("Điều phối viên", "Orchestrator")}</option>
                        </Select>
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{tx("Mô tả", "Description")}</Label>
                      <Input
                        value={form.description}
                        onChange={(e) => setForm({ ...form, description: e.target.value })}
                        placeholder={tx("Tóm tắt ngắn gọn các khả năng...", "Brief summary of capabilities...")}
                      />
                    </div>

                    <div className="grid gap-3 sm:grid-cols-3">
                      <div className="space-y-1.5">
                        <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{tx("Công cụ Mô hình", "Model Engine")}</Label>
                        <Select
                          value={form.model_id}
                          onChange={(e) => setForm({ ...form, model_id: e.target.value })}
                        >
                          <option value="">{tx("Mô hình mặc định", "Default Model")}</option>
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
                            <Thermometer className="h-3.5 w-3.5" /> {tx("Nhiệt độ", "Temp")}
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
                          <Sparkles className="h-3.5 w-3.5" /> {tx("Suy luận", "Thinking")}
                        </Label>
                        <Select
                          value={form.enable_thinking === null ? "default" : String(form.enable_thinking)}
                          onChange={(e) => setForm({ ...form, enable_thinking: e.target.value === "default" ? null : e.target.value === "true" })}
                        >
                          <option value="default">{tx("Mặc định model", "Model default")}</option>
                          <option value="true">{tx("Bật", "Enabled")}</option>
                          <option value="false">{tx("Tắt", "Disabled")}</option>
                        </Select>
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{tx("Lời nhắc hệ thống", "System Prompt")}</Label>
                      <Textarea
                        value={form.system_prompt}
                        onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
                        rows={5}
                        placeholder={tx("Bạn là một trợ lý hữu ích...", "You are a helpful assistant...")}
                        className="font-mono text-xs"
                      />
                    </div>

                    <div className="space-y-2">
                      {form.kind === "orchestrator" && (
                        <div className="rounded-lg border border-primary/30 bg-primary/5 p-2.5 text-xs text-foreground/90 flex items-start gap-2">
                          <Sparkles className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                          <div className="space-y-0.5">
                            <p className="font-semibold text-primary">
                              {tx("Mô hình Điều phối viên (Orchestrator)", "Orchestrator Architecture")}
                            </p>
                            <p className="text-[11px] text-muted-foreground leading-relaxed">
                              {tx(
                                "Orchestrator tự động sinh các công cụ ủy quyền (delegate_to_*) tới toàn bộ Worker chuyên trách trong tổ chức và tổng hợp kết quả. Không gán trực tiếp công cụ domain cho Orchestrator.",
                                "Orchestrators automatically dynamically generate delegation tools (delegate_to_*) for all active worker agents in the organization and synthesize results. Domain-specific tools are prohibited."
                              )}
                            </p>
                          </div>
                        </div>
                      )}

                      <div className="flex items-center justify-between">
                        <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                          <Wrench className="h-3.5 w-3.5 text-primary" /> {tx(`Công cụ (${selectedTools.length} đã chọn)`, `Tools (${selectedTools.length} selected)`)}
                        </Label>
                        <div className="relative w-48">
                          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                          <Input
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder={tx("Lọc công cụ...", "Filter tools...")}
                            className="h-7 pl-8 text-[11px]"
                          />
                        </div>
                      </div>

                      <div className="max-h-[240px] space-y-3 overflow-y-auto rounded-xl border border-border/40 bg-muted/10 p-3">
                        {Object.entries(groupedTools).map(([group, items]) => (
                          <section key={group} className="space-y-2">
                            <div className="flex items-center gap-2 border-b border-border/40 pb-1.5">
                              <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{toolGroupLabel(group)}</span>
                              <span className="text-[10px] text-muted-foreground/60">{items.length}</span>
                            </div>
                            <div className="grid gap-2 sm:grid-cols-2">
                              {items.map((tool) => {
                                const selected = selectedTools.includes(tool.name);
                                const disabled = !tool.available && !selected;
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
                                          {tx("Không khả dụng", "Unavailable")}
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
                        {tx("Hủy", "Cancel")}
                      </Button>
                      <Button
                        size="sm"
                        onClick={handleSubmit}
                        disabled={create.isPending || update.isPending || !form.name.trim()}
                        className="font-semibold"
                      >
                        {editingAgent ? (tx("Lưu thay đổi", "Save Changes")) : (tx("Tạo Agent", "Create Agent"))}
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
          {tx("Danh mục Agent", "Agent Catalog")}
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
          {tx("Đồng hành 3D", "3D Companion")}
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
                <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Agent đã cấu hình", "Configured Agents")}</p>
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
                <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Điều phối viên", "Orchestrators")}</p>
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
                <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Chuyên gia Công nhân", "Worker Specialists")}</p>
              </div>
            </Card>

            <Card className="flex items-center gap-3.5 p-4 shadow-card">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-500/10 text-amber-500">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{models.data?.length ?? 0}</p>
                <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Công cụ LLM đang hoạt động", "Active LLM Engines")}</p>
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
                {tx(`Tất cả (${data?.length ?? 0})`, `All (${data?.length ?? 0})`)}
              </Button>
              <Button
                size="sm"
                variant={kindFilter === "orchestrator" ? "secondary" : "ghost"}
                className="h-7 text-xs font-medium"
                onClick={() => setKindFilter("orchestrator")}
              >
                {tx(`Điều phối viên (${data?.filter((a) => a.kind === "orchestrator").length ?? 0})`, `Orchestrators (${data?.filter((a) => a.kind === "orchestrator").length ?? 0})`)}
              </Button>
              <Button
                size="sm"
                variant={kindFilter === "worker" ? "secondary" : "ghost"}
                className="h-7 text-xs font-medium"
                onClick={() => setKindFilter("worker")}
              >
                {tx(`Công nhân (${data?.filter((a) => a.kind === "worker").length ?? 0})`, `Workers (${data?.filter((a) => a.kind === "worker").length ?? 0})`)}
              </Button>
            </div>
          </div>

          <Dialog open={Boolean(releaseAgent)} onOpenChange={(v) => { if (!v) setReleaseAgent(null); }}>
            <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{tx("Bản phát hành —", "Releases —")}{releaseAgent?.name}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-2">
                <div className="space-y-2 rounded-xl border border-border/60 bg-muted/20 p-4">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{tx("Bản nháp phát hành mới", "New Release Draft")}</Label>
                  <Textarea
                    value={draftPrompt}
                    onChange={(e) => setDraftPrompt(e.target.value)}
                    rows={4}
                    className="font-mono text-xs"
                    placeholder={tx("Lời nhắc hệ thống cho bản phát hành này...", "System prompt for this release...")}
                  />
                  <Input
                    value={changeNote}
                    onChange={(e) => setChangeNote(e.target.value)}
                    placeholder={tx("Ghi chú thay đổi (vd: Đã thêm suy luận nhiều bước)", "Change note (e.g. Added multi-step reasoning)")}
                    className="text-xs"
                  />
                  <Button size="sm" onClick={handleCreateDraft} disabled={createRelease.isPending || !draftPrompt}>
                    {tx("Tạo Phiên bản Nháp", "Create Draft Version")}
                  </Button>
                </div>

                <div className="space-y-2">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{tx("Lịch sử phiên bản", "Version History")}</Label>
                  {releases.data?.map((release) => (
                    <div key={release.id} className="flex items-center justify-between gap-3 rounded-lg border border-border/70 p-3 text-xs">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground font-mono">v{release.version}</span>
                          <Badge variant={release.status === "published" ? "default" : "outline"} className="text-[9.5px]">
                            {statusLabel(release.status, t)}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted-foreground mt-0.5">{release.change_note || (tx("Không có ghi chú", "No note"))}</p>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {release.status === "draft" && (
                          <Button size="sm" onClick={() => handlePublish(release.version)} disabled={publishRelease.isPending} className="text-xs h-7">
                            <Upload className="h-3 w-3 mr-1" /> {tx("Xuất bản", "Publish")}
                          </Button>
                        )}
                        {release.status === "archived" && (
                          <Button size="sm" variant="outline" onClick={() => handleRollback(release.version)} disabled={rollbackRelease.isPending} className="text-xs h-7">
                            <RotateCcw className="h-3 w-3 mr-1" /> {tx("Khôi phục", "Rollback")}
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
              title={tx("Không thể tải agent", "Unable to load agents")}
              description={tx("Không thể truy xuất dữ liệu danh mục agent.", "Agent catalog data could not be retrieved.")}
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
              title={tx("Không có agent nào khớp với tiêu chí của bạn", "No agents match your criteria")}
              description={tx("Hãy thử điều chỉnh truy vấn tìm kiếm hoặc bộ lọc vai trò của bạn.", "Try adjusting your search query or role filter.")}
              action={
                <Button className="gap-2" onClick={openCreate}>
                  <Plus className="h-4 w-4" /> {tx("Agent mới", "New Agent")}
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
                <Box className="h-4 w-4 text-primary" /> {tx("Xem trước Avatar 3D trực tiếp", "Live 3D Avatar Preview")}
              </CardTitle>
              <CardDescription className="text-xs">
                {tx("Kết xuất hình ảnh trực tiếp của avatar đồng hành cho người dùng cuối.", "Real-time visual rendering of the companion avatar for end-users.")}
              </CardDescription>
            </CardHeader>

            <CardContent className="p-0 flex-1 flex flex-col items-center justify-center pt-2">
              {/* Simulated 3D Avatar Container with HUD Ring */}
              <div className="relative h-64 w-full flex items-center justify-center">
                {/* Simulated Floating Thought Bubble */}
                {companionConfig.showThoughtBubbles && (
                  <div className="animate-bounce-subtle absolute top-2 z-10 flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-card/95 px-3 py-1 text-[10px] font-medium text-amber-500 shadow-md">
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                    <span>{tx("⚡ 2 hành động cần bạn xem lại →", "⚡ 2 actions need your review →")}</span>
                  </div>
                )}

                {/* Simulated 3D Model HUD */}
                <div
                  className="relative transition-all duration-300 flex items-center justify-center"
                  style={{
                    width: `${Math.round(224 * ((companionConfig.avatarScale || 85) / 100))}px`,
                    height: `${Math.round(224 * ((companionConfig.avatarScale || 85) / 100))}px`,
                  }}
                >
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
                      alt={tx("Xem trước Companion 3D", "3D Companion Preview")}
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
                  <span className="font-semibold text-foreground">{companionConfig.name || (tx("Người điều hành Cá nhân", "Personal Operator"))}</span>
                  <span className="font-mono text-[10.5px] text-primary font-medium">{tx("sẵn sàng", "ready")}</span>
                </div>
              </div>

              <div className="w-full mt-4 border-t border-border/60 pt-3 text-center text-xs text-muted-foreground">
                <p className="font-medium text-foreground">{companionConfig.name}</p>
                <p className="text-[11px] text-muted-foreground">{companionConfig.tagline}</p>
                <div className="mt-2 inline-flex items-center gap-1.5 rounded-md border border-border/70 bg-muted/40 px-2.5 py-1 text-[11px] font-mono text-foreground">
                  <Scaling className="h-3 w-3 text-primary" />
                  <span>
                    {tx("Kích thước:", "Scale:")} {companionConfig.avatarScale || 85}% ({Math.round(190 * ((companionConfig.avatarScale || 85) / 100))} × {Math.round(185 * ((companionConfig.avatarScale || 85) / 100))} px)
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Right Column: Companion Configuration Form */}
          <Card className="shadow-card border-border/80 lg:col-span-2 p-6 space-y-6">
            <div className="flex items-center justify-between border-b border-border/60 pb-4">
              <div>
                <h2 className="text-base font-semibold text-foreground flex items-center gap-2">
                  <SlidersHorizontal className="h-5 w-5 text-primary" /> {tx("Cấu hình 3D Companion & Operator điều hành", "3D Companion & Executive Operator Config")}</h2>
                <p className="mt-1 text-xs text-muted-foreground">
                  {tx("Operator và Quản trị tổ chức cấu hình nhân vật này để bảo trì, phát triển và tùy biến trợ lý trực tiếp cho người dùng.", "Operators and Org Admins configure this persona to maintain, develop, and customize the live assistant for users.")}</p>
              </div>
              <Button
                className="gap-2 font-semibold"
                onClick={handleSaveCompanion}
                loading={isSavingCompanion}
              >
                <Save className="h-4 w-4" /> {tx("Lưu cấu hình", "Save Configuration")}</Button>
            </div>

            <div className="space-y-5">
              {/* Section A: Identity & Brain Binding */}
              <div className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-primary">
                  {tx("1. Danh tính & liên kết nhân vật Brain", "1. Identity & Brain Persona Binding")}</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs font-medium">{tx("Tên hiển thị Companion", "Companion Display Name")}</Label>
                    <Input
                      value={companionConfig.name}
                      onChange={(e) => setCompanionConfig({ ...companionConfig, name: e.target.value })}
                      placeholder={tx("VD: Personal Operator, Executive Chief of Staff", "e.g. Personal Operator, Executive Chief of Staff")}
                      className="text-xs"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-medium">{tx("Khẩu hiệu / Mô tả vai trò", "Tagline / Role Description")}</Label>
                    <Input
                      value={companionConfig.tagline}
                      onChange={(e) => setCompanionConfig({ ...companionConfig, tagline: e.target.value })}
                      placeholder={tx("VD: Chánh văn phòng điều hành cá nhân", "e.g. Personal Executive Chief of Staff")}
                      className="text-xs"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">{tx("Brain Agent nền (nhân vật Studio Agent)", "Underlying Brain Agent (Studio Agent Persona)")}</Label>
                  <Select
                    value={companionConfig.brainAgentId || ""}
                    onChange={(e) => setCompanionConfig({ ...companionConfig, brainAgentId: e.target.value || null })}
                    className="text-xs"
                  >
                    <option value="">{tx("Orchestrator tổ chức mặc định", "Default Organization Orchestrator")}</option>
                    {data?.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} — {a.description || tx("Persona Agent đang hoạt động", "Active Agent Persona")}
                      </option>
                    ))}
                  </Select>
                  <p className="text-[11px] text-muted-foreground">
                    {tx("Khi người dùng gửi prompt hoặc điều phối hành động tới 3D Companion, nhân vật agent này cùng system prompt sẽ xử lý yêu cầu.", "When users send prompts or dispatch actions to the 3D Companion, this agent persona and its system prompts will process the request.")}</p>
                </div>
              </div>

              {/* Section B: 3D Avatar Asset Model */}
              <div className="space-y-3 border-t border-border/60 pt-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-primary">
                  {tx("2. Asset mô hình 3D & avatar trực quan", "2. 3D Model Asset & Visual Avatar")}</h3>

                <div className="grid gap-3 sm:grid-cols-3">
                  {AVATAR_3D_PRESETS.map((preset) => {
                    const presetText: Record<string, { name: string; description: string }> = {
                      "service-robot": {
                        name: tx("Robot dịch vụ tự chủ", "Autonomous Service Robot"),
                        description: tx("Robot droid titan điều hành kinh điển với vòng HUD telemetry lơ lửng", "Classic titanium executive droid with floating telemetric HUD ring"),
                      },
                      "cyber-orb": {
                        name: tx("Cầu hologram lượng tử", "Quantum Hologram Sphere"),
                        description: tx("Quả cầu neural toàn ảnh phù hợp cho phân tích dữ liệu cường độ cao", "Holographic neural orb suitable for high-density analytics"),
                      },
                      custom: {
                        name: tx("Mô hình 3D tùy chỉnh (.glb / .gltf)", "Custom 3D Model (.glb / .gltf)"),
                        description: tx("Kết nối URL tài sản 3D thương hiệu doanh nghiệp của bạn", "Connect your enterprise brand 3D asset URL"),
                      },
                    };
                    const text = presetText[preset.id] ?? { name: preset.id, description: "" };
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
                        <p className="text-xs font-semibold text-foreground">{text.name}</p>
                        <p className="mt-1 text-[10.5px] text-muted-foreground leading-relaxed">
                          {text.description}
                        </p>
                      </button>
                    );
                  })}
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs font-medium">{tx("URL asset mô hình 3D tùy chỉnh (.glb / .gltf)", "Custom 3D Model Asset URL (.glb / .gltf)")}</Label>
                  <Input
                    value={companionConfig.modelUrl}
                    onChange={(e) => setCompanionConfig({ ...companionConfig, modelUrl: e.target.value })}
                    placeholder={tx("/agent-service-robot.glb hoặc https://your-cdn.com/avatar.glb", "/agent-service-robot.glb or https://your-cdn.com/avatar.glb")}
                    className="text-xs font-mono"
                  />
                </div>
              </div>

              {/* Section 3: Avatar Display Scale & Dimensions */}
              <div className="space-y-3 border-t border-border/60 pt-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-primary flex items-center gap-1.5">
                      <Scaling className="h-3.5 w-3.5" />
                      {tx("3. Kích thước hiển thị & tỷ lệ mô hình", "3. Display Size & Model Scale")}
                    </h3>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      {tx(
                        "Tùy chỉnh độ lớn của robot companion để góc làm việc thoáng và tránh che khuất nội dung quan trọng.",
                        "Customize the 3D avatar scale to keep workspace clear and unobstructed."
                      )}
                    </p>
                  </div>
                  <Badge variant="secondary" className="font-mono text-xs font-semibold">
                    {companionConfig.avatarScale || 85}% ({Math.round(190 * ((companionConfig.avatarScale || 85) / 100))} × {Math.round(185 * ((companionConfig.avatarScale || 85) / 100))} px)
                  </Badge>
                </div>

                {/* Preset Scale Buttons */}
                <div className="grid gap-2.5 sm:grid-cols-4">
                  {COMPANION_SCALE_PRESETS.map((preset) => {
                    const presetLabels: Record<string, { label: string; desc: string }> = {
                      compact: {
                        label: tx("Nhỏ gọn (70%)", "Compact (70%)"),
                        desc: tx("133 × 130 px · Gọn nhẹ", "133 × 130 px · Minimal"),
                      },
                      standard: {
                        label: tx("Tiêu chuẩn (85%)", "Standard (85%)"),
                        desc: tx("162 × 157 px · Cân đối nhất", "162 × 157 px · Recommended"),
                      },
                      default: {
                        label: tx("Nguyên bản (100%)", "Default (100%)"),
                        desc: tx("190 × 185 px · Kích thước gốc", "190 × 185 px · Original"),
                      },
                      large: {
                        label: tx("Lớn (115%)", "Large (115%)"),
                        desc: tx("219 × 213 px · Màn hình lớn", "219 × 213 px · Hi-DPI"),
                      },
                    };
                    const isSelected = (companionConfig.avatarScale || 85) === preset.scale;
                    const meta = presetLabels[preset.id] || { label: `${preset.scale}%`, desc: "" };
                    return (
                      <button
                        key={preset.id}
                        type="button"
                        onClick={() => setCompanionConfig({ ...companionConfig, avatarScale: preset.scale })}
                        className={`rounded-lg border p-2.5 text-left transition-all ${
                          isSelected
                            ? "border-primary bg-primary/10 shadow-sm ring-1 ring-primary/30"
                            : "border-border/80 bg-card hover:border-border hover:bg-muted/30"
                        }`}
                      >
                        <p className={`text-xs font-semibold ${isSelected ? "text-primary" : "text-foreground"}`}>
                          {meta.label}
                        </p>
                        <p className="mt-0.5 text-[10px] text-muted-foreground">{meta.desc}</p>
                      </button>
                    );
                  })}
                </div>

                {/* Slider for smooth continuous adjustment */}
                <div className="space-y-2 rounded-lg border border-border/70 bg-card/50 p-3.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground font-medium flex items-center gap-1.5">
                      <SlidersHorizontal className="h-3.5 w-3.5 text-primary" />
                      {tx("Thanh trượt tinh chỉnh tỷ lệ tự do:", "Fine-tune Scale Range:")}
                    </span>
                    <span className="font-mono font-bold text-primary">
                      {companionConfig.avatarScale || 85}%
                    </span>
                  </div>
                  <div className="flex items-center gap-3 pt-1">
                    <span className="text-[11px] font-mono text-muted-foreground">60%</span>
                    <Slider
                      value={[companionConfig.avatarScale || 85]}
                      min={60}
                      max={130}
                      step={5}
                      onValueChange={(val) => setCompanionConfig({ ...companionConfig, avatarScale: val[0] })}
                      className="flex-1"
                    />
                    <span className="text-[11px] font-mono text-muted-foreground">130%</span>
                  </div>
                  <div className="flex items-center justify-between pt-1 text-[11px] text-muted-foreground">
                    <span>{tx("Mặc định đề xuất: 85% (Tiêu chuẩn tối ưu trải nghiệm)", "Recommended default: 85% (Optimal UX)")}</span>
                    {companionConfig.avatarScale !== 85 && (
                      <button
                        type="button"
                        onClick={() => setCompanionConfig({ ...companionConfig, avatarScale: 85 })}
                        className="text-primary hover:underline font-medium"
                      >
                        {tx("Đặt lại về 85%", "Reset to 85%")}
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* Section 4: Docking Position & Screen Placement */}
              <div className="space-y-3 border-t border-border/60 pt-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-primary">
                  {tx("4. Vị trí mặc định trên màn hình & neo đậu", "4. Default Screen Placement & Docking")}</h3>
                <div className="grid gap-3 sm:grid-cols-4">
                  {[
                    { id: "bottom-right", label: tx("Dưới-phải (Mặc định)", "Bottom-Right (Default)") },
                    { id: "middle-right", label: tx("Giữa-phải", "Middle-Right") },
                    { id: "top-right", label: tx("Trên-phải", "Top-Right") },
                    { id: "bottom-left", label: tx("Dưới-trái", "Bottom-Left") },
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

              {/* Section 5: Feature Toggles & Capabilities */}
              <div className="space-y-3 border-t border-border/60 pt-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-primary">
                  {tx("5. Khả năng tương tác & điều khiển bề mặt", "5. Interactive Capabilities & Surface Controls")}</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="flex items-center gap-2.5 rounded-lg border border-border/70 p-3 text-xs text-foreground cursor-pointer hover:bg-muted/30">
                    <input
                      type="checkbox"
                      checked={companionConfig.showThoughtBubbles}
                      onChange={(e) => setCompanionConfig({ ...companionConfig, showThoughtBubbles: e.target.checked })}
                      className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
                    />
                    <div>
                      <p className="font-semibold">{tx("Cảnh báo bong bóng suy nghĩ trực tiếp", "Live Thought Bubble Alerts")}</p>
                      <p className="text-[10px] text-muted-foreground">{tx("Hiện thông báo hành động khẩn phía trên đầu avatar", "Show urgent action notifications above avatar head")}</p>
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
                      <p className="font-semibold">{tx("Phê duyệt kỹ thuật 1-chạm", "1-Click Technical Approvals")}</p>
                      <p className="text-[10px] text-muted-foreground">{tx("Cho phép phê duyệt tức thì từ bảng operator nổi", "Allow instant approving from floating operator surface")}</p>
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
                      <p className="font-semibold">{tx("Luồng phân loại email", "Email Triage Feed")}</p>
                      <p className="text-[10px] text-muted-foreground">{tx("Hiển thị email đầu vào đã phân loại trong bảng operator", "Expose incoming classified emails in operator surface")}</p>
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
                      <p className="font-semibold">{tx("Điều phối operator trực tiếp", "Direct Operator Dispatch")}</p>
                      <p className="text-[10px] text-muted-foreground">{tx("Bật thanh điều phối lệnh bằng ngôn ngữ tự nhiên", "Enable natural language command dispatch bar")}</p>
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
