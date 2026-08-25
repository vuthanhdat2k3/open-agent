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
} from "@/hooks";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared";
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
  const [open, setOpen] = React.useState(false);
  const [editingAgent, setEditingAgent] = React.useState<Agent | null>(null);
  const [releaseAgent, setReleaseAgent] = React.useState<Agent | null>(null);
  const [draftPrompt, setDraftPrompt] = React.useState("");
  const [changeNote, setChangeNote] = React.useState("");
  const { data, isLoading, isError, refetch } = useAgents();
  const models = useModels(open);
  const tools = useAgentTools(open);
  const create = useCreateAgent();
  const update = useUpdateAgent();
  const del = useDeleteAgent();
  const releases = useAgentReleases(releaseAgent?.id ?? null);
  const createRelease = useCreateAgentRelease();
  const publishRelease = usePublishAgentRelease();
  const rollbackRelease = useRollbackAgentRelease();

  const [selectedTools, setSelectedTools] = React.useState<string[]>([]);
  const [toolSearch, setToolSearch] = React.useState("");
  const [form, setForm] = React.useState<AgentForm>(DEFAULT_FORM);

  const groupedTools = React.useMemo(() => {
    const query = toolSearch.trim().toLowerCase();
    const groups: Record<string, AgentToolInfo[]> = {};
    for (const tool of tools.data ?? []) {
      if (query && !`${tool.name} ${tool.description}`.toLowerCase().includes(query)) continue;
      const group = toolGroup(tool.name);
      (groups[group] ??= []).push(tool);
    }
    return groups;
  }, [tools.data, toolSearch]);

  React.useEffect(() => {
    if (!models.data?.length || editingAgent) return;
    setForm((current) =>
      current.model_id ? current : { ...current, model_id: models.data![0].id }
    );
  }, [models.data, editingAgent]);

  const openEdit = (agent: Agent) => {
    setEditingAgent(agent);
    setForm({
      name: agent.name,
      description: agent.description,
      system_prompt: agent.system_prompt,
      model_id: agent.model_id,
      kind: agent.kind,
      max_iterations: agent.max_iterations,
      temperature: agent.temperature,
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
      toast.success("Draft release created");
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  const handlePublish = async (version: number) => {
    if (!releaseAgent) return;
    try {
      await publishRelease.mutateAsync({ agentId: releaseAgent.id, version });
      toast.success(`Version ${version} published`);
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
      toast.success(`Rolled back as version ${release.version}`);
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
        toast.success("Agent updated");
      } else {
        await create.mutateAsync({ ...form, tools: selectedTools });
        toast.success("Agent created");
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
      <PageHeader
        icon={Bot}
        title="Agents"
        description="System prompt, model, and granted tool set"
        actions={
          <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) setEditingAgent(null); }}>
            <DialogTrigger asChild>
              <Button className="gap-2 active-tactile transition-transform" onClick={openCreate}>
                <Plus className="h-4 w-4" /> New Agent
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>{editingAgent ? `Edit â€” ${editingAgent.name}` : "New Agent"}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-1">
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Name</Label>
                    <Input
                      value={form.name}
                      onChange={(e) => setForm({ ...form, name: e.target.value })}
                      placeholder="researcher"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Description</Label>
                    <Input
                      value={form.description}
                      onChange={(e) => setForm({ ...form, description: e.target.value })}
                      placeholder="Brief description"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Kind</Label>
                  <Select
                    value={form.kind}
                    onChange={(e) => setForm({ ...form, kind: e.target.value as "worker" | "orchestrator" })}
                    className="w-full"
                  >
                    <option value="worker">Worker (called by other agents, not directly by users)</option>
                    <option value="orchestrator">Orchestrator (chats with users, delegates to workers via call_agent)</option>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80 flex items-center gap-1.5">
                    <Cpu className="h-3.5 w-3.5 text-primary" /> Model
                  </Label>
                  <Select
                    value={form.model_id}
                    onChange={(e) => setForm({ ...form, model_id: e.target.value })}
                    className="w-full"
                  >
                    {models.data?.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.display_name || m.name} ({m.tier})
                      </option>
                    ))}
                  </Select>
                  {form.model_id && (() => {
                    const m = models.data?.find((x) => x.id === form.model_id);
                    if (!m) return null;
                    return (
                      <div className="flex items-center gap-3 px-3 py-1.5 rounded-lg bg-muted/30 border border-border/30 text-[11px] font-mono text-muted-foreground">
                        <span>ctx: <strong className="text-foreground">{m.context_window.toLocaleString()}</strong></span>
                        <span>in: <strong className="text-foreground">${m.input_cost_per_1k}/1k</strong></span>
                        <span>out: <strong className="text-foreground">${m.output_cost_per_1k}/1k</strong></span>
                      </div>
                    );
                  })()}
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">System Prompt</Label>
                  <Textarea
                    className="min-h-[120px] font-mono text-xs resize-y"
                    value={form.system_prompt}
                    onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
                    placeholder="You are a helpful assistantâ€¦"
                  />
                </div>

                <div className="space-y-2 rounded-xl border border-border/50 bg-muted/10 p-3">
                  <div className="flex items-start gap-2">
                    <div>
                      <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Execution permissions</Label>
                      <p className="mt-1 text-[11px] text-muted-foreground">Allow risk tiers before selecting tools that require them.</p>
                    </div>
                    <Badge variant="outline" className="ml-auto text-[10px]">{form.allowed_risk_tiers.length} / {RISK_TIERS.length} enabled</Badge>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                    {RISK_TIERS.map((tier) => {
                      const enabled = form.allowed_risk_tiers.includes(tier.key);
                      return (
                        <button
                          key={tier.key}
                          type="button"
                          aria-pressed={enabled}
                          onClick={() => toggleRiskTier(tier.key)}
                          className={`rounded-lg border p-2 text-left transition-colors ${enabled ? "border-primary/50 bg-primary/10" : "border-border/50 bg-background/30 hover:border-primary/30"}`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className={`text-xs font-semibold ${enabled ? "text-foreground" : "text-muted-foreground"}`}>{tier.label}</span>
                            <span className="text-[9px] uppercase tracking-wider text-muted-foreground">{enabled ? "Allowed" : "Blocked"}</span>
                          </div>
                          <span className="mt-1 block text-[10px] text-muted-foreground">{tier.description}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Label className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                      <Wrench className="h-3.5 w-3.5 text-primary" /> Tools
                    </Label>
                    <Badge variant="outline" className="ml-auto text-[10px]">
                      {selectedTools.length} selected Â· {tools.data?.length ?? 0} total
                    </Badge>
                  </div>
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      value={toolSearch}
                      onChange={(event) => setToolSearch(event.target.value)}
                      placeholder="Search tools by name or description"
                      aria-label="Search tools"
                      className="h-9 pl-9 text-xs"
                    />
                  </div>
                  <div className="max-h-[320px] space-y-3 overflow-y-auto rounded-xl border border-border/40 bg-muted/10 p-3">
                    {Object.entries(groupedTools).length === 0 ? (
                      <p className="py-8 text-center text-xs text-muted-foreground">No tools match your search.</p>
                    ) : (
                      Object.entries(groupedTools).map(([group, items]) => (
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
                                  aria-pressed={selected}
                                  onClick={() => toggleTool(tool.name)}
                                  title={tool.available && tierAllowed ? tool.description : !tool.available ? "Connection unavailable. Connect the integration before using this tool." : `Enable the ${tool.risk_tier} permission above before selecting this tool.`}
                                  className={`flex min-w-0 items-start justify-between gap-2 rounded-lg border p-2 text-left transition-colors ${
                                    selected ? "border-primary/50 bg-primary/10" : "border-border/50 bg-background/30 hover:border-primary/30"
                                  } ${disabled ? "cursor-not-allowed opacity-45" : "active-tactile"}`}
                                >
                                  <span className="min-w-0">
                                    <span className="block truncate font-mono text-[11px] font-medium">{tool.name}</span>
                                    <span className="mt-0.5 block line-clamp-1 text-[10px] text-muted-foreground">{tool.description}</span>
                                  </span>
                                  <span className="flex shrink-0 flex-col items-end gap-1">
                                    {tool.risk_tier && <span className={`rounded-full border px-1.5 py-0.5 text-[9px] ${riskColor[tool.risk_tier]}`}>{tool.risk_tier}</span>}
                                    {!tool.available && <span className="text-[9px] text-warning">Unavailable</span>}
                                    {tool.available && !tierAllowed && <span className="text-[9px] text-warning">Permission required</span>}
                                  </span>
                                </button>
                              );
                            })}
                          </div>
                        </section>
                      ))
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80 flex items-center gap-1.5">
                      <RotateCcw className="h-3.5 w-3.5 text-primary" /> Max Iterations
                    </Label>
                    <Input
                      type="number"
                      min={1}
                      max={50}
                      value={form.max_iterations}
                      onChange={(e) => setForm({ ...form, max_iterations: +e.target.value })}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80 flex items-center gap-1.5">
                      <Thermometer className="h-3.5 w-3.5 text-primary" /> Temperature
                      <span className="ml-auto font-mono text-foreground">{form.temperature.toFixed(2)}</span>
                    </Label>
                    <Slider value={[form.temperature]} min={0} max={2} step={0.1} onValueChange={([value]) => setForm({ ...form, temperature: value })} aria-label="Temperature" />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="agent-thinking" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Thinking</Label>
                    <Select id="agent-thinking" value={form.enable_thinking === null ? "" : String(form.enable_thinking)} onChange={(event) => setForm({ ...form, enable_thinking: event.target.value === "" ? null : event.target.value === "true" })} aria-label="Enable thinking">
                      <option value="">Model default</option>
                      <option value="true">Enabled</option>
                      <option value="false">Disabled (concise replies)</option>
                    </Select>
                    <p className="text-[10px] text-muted-foreground">Disable for routing/orchestration agents to skip verbose reasoning.</p>
                  </div>
                </div>

                <Button
                  className="w-full gap-2 active-tactile transition-transform"
                  onClick={handleSubmit}
                  disabled={create.isPending || update.isPending || !form.name}
                >
                  {(create.isPending || update.isPending) ? "Savingâ€¦" : editingAgent ? "Update Agent" : "Create Agent"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        }
      />

      <Dialog
        open={!!releaseAgent}
        onOpenChange={(value) => {
          if (!value) setReleaseAgent(null);
        }}
      >
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Release history: {releaseAgent?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-5 pt-1">
            <div className="space-y-3 border-b border-border/50 pb-5">
              <div className="space-y-1.5">
                <Label>Draft system prompt</Label>
                <Textarea
                  className="min-h-[120px] font-mono text-xs"
                  value={draftPrompt}
                  onChange={(event) => setDraftPrompt(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Change note</Label>
                <Input
                  value={changeNote}
                  maxLength={512}
                  onChange={(event) => setChangeNote(event.target.value)}
                  placeholder="Why this release is needed"
                />
              </div>
              <Button
                className="gap-2"
                onClick={handleCreateDraft}
                disabled={createRelease.isPending || !changeNote.trim()}
              >
                <Plus className="h-4 w-4" />
                {createRelease.isPending ? "Creating..." : "Create draft"}
              </Button>
            </div>

            <div className="space-y-2">
              {releases.isLoading && <Skeleton className="h-24 w-full" />}
              {releases.data?.map((release) => (
                <div
                  key={release.id}
                  className="flex items-start justify-between gap-4 rounded-md border border-border/50 p-3"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-semibold">
                        v{release.version}
                      </span>
                      <Badge
                        variant={release.status === "published" ? "default" : "outline"}
                      >
                        {release.status}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {release.change_note || "No change note"}
                    </p>
                    <p className="text-[10px] text-muted-foreground/70">
                      {new Date(release.created_at).toLocaleString()}
                      {" Â· "}
                      {release.config_hash.slice(0, 10)}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    {release.status === "draft" && (
                      <Button
                        size="sm"
                        className="gap-1.5"
                        onClick={() => handlePublish(release.version)}
                        disabled={publishRelease.isPending}
                      >
                        <Upload className="h-3.5 w-3.5" /> Publish
                      </Button>
                    )}
                    {release.status === "archived" && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="gap-1.5"
                        onClick={() => handleRollback(release.version)}
                        disabled={rollbackRelease.isPending}
                      >
                        <RotateCcw className="h-3.5 w-3.5" /> Rollback
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {isLoading ? <LoadingSkeleton variant="grid" /> : isError ? <ErrorState title="Unable to load agents" description="Agent data could not be loaded." onRetry={() => void refetch()} /> : data && data.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 stagger">
          {data.map((a) => (
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
      ) : (
        <EmptyState
          icon={Bot}
          title="No agents yet"
          description="Create one with a model, system prompt, and a tool set."
          action={
            <Button className="gap-2 active-tactile transition-transform" onClick={openCreate}>
              <Plus className="h-4 w-4" /> New Agent
            </Button>
          }
        />
      )}
    </div>
  );
}
