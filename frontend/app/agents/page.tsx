"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Bot,
  Plus,
  Trash2,
  Wrench,
  Cpu,
  Pencil,
  Thermometer,
  RotateCcw,
  History,
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
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, Slider } from "@/components/ui/select";
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
import type { Agent } from "@/types";

type AgentForm = {
  name: string;
  description: string;
  system_prompt: string;
  model_id: string;
  max_iterations: number;
  temperature: number;
};

const DEFAULT_FORM: AgentForm = {
  name: "",
  description: "",
  system_prompt: "",
  model_id: "",
  max_iterations: 12,
  temperature: 0.7,
};

export default function AgentsPage() {
  const [open, setOpen] = React.useState(false);
  const [editingAgent, setEditingAgent] = React.useState<Agent | null>(null);
  const [releaseAgent, setReleaseAgent] = React.useState<Agent | null>(null);
  const [draftPrompt, setDraftPrompt] = React.useState("");
  const [changeNote, setChangeNote] = React.useState("");
  const { data, isLoading } = useAgents();
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
  const [form, setForm] = React.useState<AgentForm>(DEFAULT_FORM);

  // Auto-populate model when models load (for new agent)
  React.useEffect(() => {
    if (!models.data?.length || editingAgent) return;
    setForm((current) =>
      current.model_id ? current : { ...current, model_id: models.data![0].id }
    );
  }, [models.data, editingAgent]);

  // Populate form when editing an existing agent
  const openEdit = (agent: Agent) => {
    setEditingAgent(agent);
    setForm({
      name: agent.name,
      description: agent.description,
      system_prompt: agent.system_prompt,
      model_id: agent.model_id,
      max_iterations: agent.max_iterations,
      temperature: agent.temperature,
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

  const tierColor: Record<string, string> = {
    frontier: "border-primary/60 text-primary bg-primary/10",
    balanced: "border-info/60 text-info bg-info/10",
    economy: "border-muted-foreground/40 text-muted-foreground bg-muted/20",
  };
  const riskColor: Record<string, string> = {
    safe: "border-muted-foreground/40 bg-muted/30 text-muted-foreground",
    read: "border-info/50 bg-info/10 text-info",
    write: "border-warning/50 bg-warning/10 text-warning",
    execute: "border-orange-500/50 bg-orange-500/10 text-orange-400",
    network: "border-violet-500/50 bg-violet-500/10 text-violet-400",
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
                <DialogTitle>{editingAgent ? `Edit — ${editingAgent.name}` : "New Agent"}</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-1">
                {/* Name + Description */}
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

                {/* Model */}
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

                {/* System Prompt */}
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">System Prompt</Label>
                  <Textarea
                    className="min-h-[120px] font-mono text-xs resize-y"
                    value={form.system_prompt}
                    onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
                    placeholder="You are a helpful assistant…"
                  />
                </div>

                {/* Tools */}
                <div className="space-y-1.5">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80 flex items-center gap-1.5">
                    <Wrench className="h-3.5 w-3.5 text-primary" /> Tools
                    {selectedTools.length > 0 && (
                      <span className="ml-auto text-[10px] text-muted-foreground font-normal">{selectedTools.length} selected</span>
                    )}
                  </Label>
                  <div className="flex flex-wrap gap-2 p-3 rounded-xl border border-border/40 bg-muted/10 min-h-[56px]">
                    {tools.data?.map((t) => {
                      const on = selectedTools.includes(t.name);
                      return (
                        <button
                          key={t.name}
                          type="button"
                          onClick={() => toggleTool(t.name)}
                          className="transition-transform active:scale-[0.96]"
                          title={t.description}
                        >
                          <Badge
                            variant={on ? "default" : "outline"}
                            className={`cursor-pointer gap-1 text-[11px] transition-colors ${
                              on ? "shadow-sm" : "opacity-60 hover:opacity-100"
                            }`}
                          >
                            <Wrench className="h-2.5 w-2.5" /> {t.name}
                            {t.risk_tier && (
                              <span className={`ml-1 rounded-full border px-1.5 py-0.5 ${riskColor[t.risk_tier]}`}>
                                {t.risk_tier}
                              </span>
                            )}
                          </Badge>
                        </button>
                      );
                    })}
                    {!tools.data?.length && (
                      <span className="text-xs text-muted-foreground/60 m-auto">Loading tools…</span>
                    )}
                  </div>
                </div>

                {/* Max Iterations + Temperature */}
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
                    <Slider value={form.temperature} onChange={(v) => setForm({ ...form, temperature: v })} />
                  </div>
                </div>

                <Button
                  className="w-full gap-2 active-tactile transition-transform"
                  onClick={handleSubmit}
                  disabled={create.isPending || update.isPending || !form.name}
                >
                  {(create.isPending || update.isPending) ? "Saving…" : editingAgent ? "Update Agent" : "Create Agent"}
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
                      {" · "}
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

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-48 w-full" />
          ))}
        </div>
      ) : data && data.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 stagger">
          {data.map((a) => {
            const agentModel = models.data?.find((m) => m.id === a.model_id);
            return (
              <Card key={a.id} glass className="card-lift flex flex-col p-5 group">
                {/* Header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 text-primary shadow-inner-edge">
                      <Bot className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-sm tracking-tight">{a.name}</p>
                      {agentModel && (
                        <p className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground/70">
                          <Cpu className="h-2.5 w-2.5 text-primary/60" />
                          <span className="truncate font-mono">{agentModel.display_name || agentModel.name}</span>
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 text-muted-foreground hover:text-foreground active-tactile transition-transform"
                      onClick={() => openReleases(a)}
                      aria-label={`Release history for ${a.name}`}
                    >
                      <History className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 text-muted-foreground hover:text-foreground active-tactile transition-transform"
                      onClick={() => openEdit(a)}
                      aria-label={`Edit ${a.name}`}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-7 w-7 text-muted-foreground hover:text-destructive active-tactile transition-transform"
                      onClick={() => del.mutate(a.id)}
                      aria-label={`Delete ${a.name}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>

                {/* Description */}
                {a.description && (
                  <p className="mt-3 line-clamp-2 text-xs text-muted-foreground leading-relaxed">{a.description}</p>
                )}

                <div className="mt-3 flex items-center gap-2 text-[10px] text-muted-foreground">
                  <History className="h-3 w-3" />
                  Active release v{a.latest_release_number}
                </div>

                {/* Model badge row */}
                {agentModel && (
                  <div className="mt-3 flex items-center gap-1.5 flex-wrap">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider border ${tierColor[agentModel.tier] ?? tierColor.economy}`}>
                      {agentModel.tier}
                    </span>
                    <span className="text-[10px] font-mono text-muted-foreground/60 bg-muted/30 border border-border/30 px-2 py-0.5 rounded-full">
                      ctx {agentModel.context_window.toLocaleString()}
                    </span>
                    <span className="text-[10px] font-mono text-muted-foreground/60 bg-muted/30 border border-border/30 px-2 py-0.5 rounded-full">
                      T={a.temperature.toFixed(1)}
                    </span>
                    <span className="text-[10px] font-mono text-muted-foreground/60 bg-muted/30 border border-border/30 px-2 py-0.5 rounded-full">
                      ×{a.max_iterations}
                    </span>
                  </div>
                )}

                {/* Tools */}
                {a.tools.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-border/40 space-y-1.5">
                    <div className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground/80">
                      Granted tools ({a.tools.length})
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {a.tools.map((t) => (
                        <Badge key={t} variant="outline" className="gap-1 font-mono text-[10px] bg-muted/30 border-border/50">
                          <Wrench className="h-2.5 w-2.5" /> {t}
                          {tools.data?.find((tool) => tool.name === t)?.risk_tier && (
                            <span className="text-muted-foreground">
                              {tools.data.find((tool) => tool.name === t)?.risk_tier}
                            </span>
                          )}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            );
          })}
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
