"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Workflow as WorkflowIcon,
  Play,
  Save,
  FolderOpen,
  FilePlus,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { streamSSE } from "@/lib/api";
import { useWorkflows, useCreateWorkflow, useAgents, useModels, useGenerateWorkflow, useUrlSearchParam, useWorkflowRun } from "@/hooks";
import { useWorkflowStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingSkeleton } from "@/components/shared";
import { WorkflowNodePalette } from "@/components/workflows/workflow-node-palette";
import { WorkflowCanvas } from "@/components/workflows/workflow-canvas";
import { WorkflowNodeConfig } from "@/components/workflows/workflow-node-config";
import { WorkflowConsole, type WorkflowLogItem } from "@/components/workflows/workflow-console";
import type { GraphEdge, GraphNode } from "@/types";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

function layout(nodes: GraphNode[], edges: GraphEdge[]) {
  const adj: Record<string, string[]> = {};
  edges.forEach((e) => (adj[e.from_] = adj[e.from_] || []).push(e.to));
  const layer: Record<string, number> = {};
  const input = nodes.find((n) => n.kind === "input");
  if (!input) return {};
  const q: [string, number][] = [[input.id, 0]];
  layer[input.id] = 0;
  while (q.length) {
    const [id, d] = q.shift()!;
    (adj[id] || []).forEach((t) => {
      if (layer[t] === undefined || layer[t] < d + 1) {
        layer[t] = d + 1;
        q.push([t, d + 1]);
      }
    });
  }
  const perLayer: Record<number, GraphNode[]> = {};
  nodes.forEach((n) => {
    const l = layer[n.id] ?? 0;
    (perLayer[l] = perLayer[l] || []).push(n);
  });
  // Vertical flow: BFS depth -> row (y), index within a row -> column (x).
  const pos: Record<string, { x: number; y: number }> = {};
  Object.entries(perLayer).forEach(([l, ns]) => {
    ns.forEach((n, i) => (pos[n.id] = { x: 40 + i * 240, y: 40 + +l * 160 }));
  });
  return pos;
}

export default function WorkflowsPage() {
  const workflows = useWorkflows();
  const { data } = workflows;
  const create = useCreateWorkflow();
  const agents = useAgents();
  const models = useModels();
  const generate = useGenerateWorkflow();
  const {
    nodes,
    edges,
    selectedNodeId,
    activeRunId,
    setGraph,
    setSelectedNode,
    setActiveRun,
  } = useWorkflowStore();
  const workflowRun = useWorkflowRun(activeRunId);
  const [runParam, setRunParam] = useUrlSearchParam("run");
  React.useEffect(() => {
    if (runParam && runParam !== activeRunId) setActiveRun(runParam);
  }, [activeRunId, runParam, setActiveRun]);
  React.useEffect(() => {
    if (activeRunId !== runParam) setRunParam(activeRunId);
  }, [activeRunId, runParam, setRunParam]);

  const [wfName, setWfName] = React.useState("");
  const [aiPrompt, setAiPrompt] = React.useState("");
  const [aiModelId, setAiModelId] = React.useState("");
  const [aiResult, setAiResult] = React.useState<{
    name: string;
    description: string;
    graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  } | null>(null);
  const [input, setInput] = React.useState("");
  const [running, setRunning] = React.useState(false);
  const [nodeStatus, setNodeStatus] = React.useState<Record<string, string>>({});
  const [output, setOutput] = React.useState("");
  const [logs, setLogs] = React.useState<WorkflowLogItem[]>([]);
  const [editId, setEditId] = React.useState<string | null>(null);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) || null;

  // Fade a node/edge's "done" status back to idle a few seconds after it
  // finishes, so the running-state highlight reads as transient feedback
  // rather than a permanent marker. Only applies while a run is actively
  // streaming â€” restoring a past completed run's status (see the
  // workflowRun.data effect below) should stay visible, not fade away.
  const fadedNodeIdsRef = React.useRef<Set<string>>(new Set());
  React.useEffect(() => {
    if (!running) return;
    const timers: number[] = [];
    for (const [nodeId, status] of Object.entries(nodeStatus)) {
      if (status !== "done" || fadedNodeIdsRef.current.has(nodeId)) continue;
      fadedNodeIdsRef.current.add(nodeId);
      const timer = window.setTimeout(() => {
        setNodeStatus((s) => {
          if (s[nodeId] !== "done") return s;
          const next = { ...s };
          delete next[nodeId];
          return next;
        });
      }, 4000);
      timers.push(timer);
    }
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [nodeStatus, running]);

  React.useEffect(() => {
    if (nodes.length > 0 && !nodes.every((n) => n.position?.x != null)) {
      const calculatedPos = layout(nodes, edges);
      const updatedNodes = nodes.map((n) => ({
        ...n,
        position: n.position || calculatedPos[n.id] || { x: 40, y: 40 },
      }));
      setGraph(updatedNodes, edges);
    }
  }, [nodes, edges, setGraph]);

  const addNode = (kind: GraphNode["kind"], position: { x: number; y: number }) => {
    const id = `${kind}-${Math.random().toString(36).slice(2, 7)}`;
    const node: GraphNode = {
      id,
      kind,
      label: kind,
      config: kind === "tool" ? { tool: "" } : {},
      merge_mode: kind === "merge" ? "all" : undefined,
      agent_id:
        kind === "agent" && agents.data?.length ? agents.data[0].id : undefined,
      position,
    };
    setGraph([...nodes, node], edges);
    setSelectedNode(id);
  };

  const updateNode = (patch: Partial<GraphNode>) => {
    setGraph(
      nodes.map((n) => (n.id === selectedNodeId ? { ...n, ...patch } : n)),
      edges,
    );
  };

  const newWorkflow = () => {
    setWfName("");
    setEditId(null);
    setInput("");
    setOutput("");
    setLogs([]);
    setNodeStatus({});
    setActiveRun(null);
    setGraph([], []);
    setSelectedNode(null);
    toast.success("New workflow â€” canvas cleared");
  };

  const loadWorkflow = (wf: any) => {
    setWfName(wf.name);
    setEditId(wf.id);
    setGraph(wf.graph.nodes, wf.graph.edges);
    setSelectedNode(null);
    setLogs([]);
    setOutput("");
  };

  const save = async () => {
    try {
      await create.mutateAsync({
        name: wfName || "workflow",
        description: "",
        graph: { nodes, edges },
      });
      toast.success("Workflow saved");
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  React.useEffect(() => {
    if (!aiModelId && models.data?.length) setAiModelId(models.data[0].id);
  }, [models.data, aiModelId]);

  React.useEffect(() => {
    const run = workflowRun.data;
    if (!run) return;
    setActiveRun(run.id, run.status);
    const statuses: Record<string, string> = {};
    const restoredLogs: WorkflowLogItem[] = [];
    for (const node of run.nodes || []) {
      statuses[node.node_id] = node.status === "succeeded" ? "done" : node.status;
      restoredLogs.push({
        id: node.id,
        ts: node.started_at ? new Date(node.started_at).getTime() : Date.now(),
        event: node.status === "succeeded" ? "node_done" : node.status === "failed" ? "node_error" : "node_start",
        node_id: node.node_id,
        message: `Node "${node.node_id}" ${node.status}`,
        output: typeof node.output?.text === "string" ? node.output.text : undefined,
      });
    }
    setNodeStatus(statuses);
    if (run.output?.text) setOutput(String(run.output.text));
    setRunning(!["succeeded", "failed", "diverged", "cancelled", "waiting_approval"].includes(run.status));
    setLogs((previous) => (previous.length === 0 ? restoredLogs : previous));
  }, [workflowRun.data, setActiveRun]);

  const handleGenerate = async () => {
    if (!aiPrompt.trim() || !aiModelId) return;
    try {
      const result = await generate.mutateAsync({ prompt: aiPrompt, model_id: aiModelId });
      setAiResult(result);
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const applyGenerated = () => {
    if (!aiResult) return;
    setWfName(aiResult.name);
    setEditId(null);
    setGraph(
      aiResult.graph.nodes.map((n) => ({ ...n, position: undefined })),
      aiResult.graph.edges,
    );
    setSelectedNode(null);
    setAiResult(null);
    setAiPrompt("");
    toast.success("Applied to canvas â€” review and Save");
  };

  const handleAutoLayout = () => {
    const calculatedPos = layout(nodes, edges);
    const updatedNodes = nodes.map((n) => ({
      ...n,
      position: calculatedPos[n.id] || { x: 40, y: 40 },
    }));
    setGraph(updatedNodes, edges);
    toast.success("Graph auto-layout applied");
  };

  const run = async () => {
    if (!editId) {
      toast.error("Save the workflow first to run it");
      return;
    }
    setRunning(true);
    setOutput("");
    setNodeStatus({});
    fadedNodeIdsRef.current.clear();
    setLogs([]);
    try {
      await streamSSE(
        `/api/workflows/${editId}/run`,
        { input, stream: true, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone },
        (ev) => {
          const d = ev.data;
          const ts = Date.now();
          const logId = Math.random().toString(36).slice(2, 9);

          if (ev.event === "workflow_start") {
            setActiveRun(d.workflow_run_id, d.status);
          } else if (ev.event === "node_start") {
            setNodeStatus((s) => ({ ...s, [d.node_id]: "running" }));
            setLogs((prev) => [
              ...prev,
              {
                id: logId,
                ts,
                event: "node_start",
                node_id: d.node_id,
                message: `Node "${d.node_id}" started (${d.kind || "execution"})`,
              },
            ]);
          } else if (ev.event === "node_done") {
            setNodeStatus((s) => ({ ...s, [d.node_id]: "done" }));
            const outSnippet = d.output ? ` (output: ${typeof d.output === "string" ? d.output.slice(0, 100) : JSON.stringify(d.output).slice(0, 100)})` : "";
            setLogs((prev) => [
              ...prev,
              {
                id: logId,
                ts,
                event: "node_done",
                node_id: d.node_id,
                message: `Node "${d.node_id}" completed${outSnippet}`,
                output: typeof d.output === "string" ? d.output : JSON.stringify(d.output, null, 2),
              },
            ]);
          } else if (ev.event === "node_error") {
            setNodeStatus((s) => ({ ...s, [d.node_id]: "error" }));
            setLogs((prev) => [
              ...prev,
              {
                id: logId,
                ts,
                event: "node_error",
                node_id: d.node_id,
                message: d.message || `Node "${d.node_id}" failed`,
              },
            ]);
          } else if (ev.event === "edge") {
            setLogs((prev) => [
              ...prev,
              {
                id: logId,
                ts,
                event: "edge",
                message: `Edge ${d.from} â†’ ${d.to} taken`,
              },
            ]);
          } else if (ev.event === "approval_required") {
            setLogs((prev) => [
              ...prev,
              {
                id: logId,
                ts,
                event: "approval_required",
                node_id: d.node_id,
                message: `Node "${d.node_id}" waiting for approval (approval_id: ${d.approval_id})`,
              },
            ]);
          } else if (ev.event === "error") {
            setLogs((prev) => [
              ...prev,
              {
                id: logId,
                ts,
                event: "error",
                message: d.message || "Workflow execution error",
              },
            ]);
          } else if (ev.event === "done") {
            setOutput(d.output || "");
            setLogs((prev) => [
              ...prev,
              {
                id: logId,
                ts,
                event: "done",
                message: "Workflow finished successfully",
                output: typeof d.output === "string" ? d.output : JSON.stringify(d.output, null, 2),
              },
            ]);
          }
        },
      );
    } catch (e: any) {
      toast.error(e.message);
      setLogs((prev) => [
        ...prev,
        {
          id: Math.random().toString(36).slice(2, 9),
          ts: Date.now(),
          event: "error",
          message: e.message || "Execution error occurred",
        },
      ]);
    } finally {
      // The durable run owns the lifecycle; polling will update the UI.
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        icon={WorkflowIcon}
        title="Workflows"
        description="Connect agents into a parallel graph"
        actions={
          <>
            <Button variant="outline" className="gap-2 active-tactile transition-transform" onClick={newWorkflow}>
              <FilePlus className="h-4 w-4" /> New
            </Button>
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="outline" className="gap-2 active-tactile transition-transform">
                  <FolderOpen className="h-4 w-4" /> Load
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Load workflow</DialogTitle>
                </DialogHeader>
                <div className="space-y-2">
                  {workflows.isLoading ? <LoadingSkeleton variant="table" /> : workflows.isError ? <ErrorState title="Unable to load workflows" description="Saved workflows could not be loaded." onRetry={() => void workflows.refetch()} /> : data?.map((wf) => (
                    <DialogClose asChild key={wf.id}>
                      <Button
                        variant="outline"
                        className="w-full justify-start"
                        onClick={() => loadWorkflow(wf)}
                      >
                        {wf.name}
                      </Button>
                    </DialogClose>
                  ))}
                </div>
              </DialogContent>
            </Dialog>
            <Button variant="outline" className="gap-2 active-tactile transition-transform" onClick={handleAutoLayout}>
              <RefreshCw className="h-4 w-4" /> Auto-Layout
            </Button>
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="outline" className="gap-2 active-tactile transition-transform">
                  <Sparkles className="h-4 w-4 text-primary" /> AI Generate
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Generate workflow with AI</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                      Describe what the workflow should do
                    </Label>
                    <Textarea
                      className="min-h-[100px] text-xs"
                      value={aiPrompt}
                      onChange={(e) => setAiPrompt(e.target.value)}
                      placeholder="e.g. Research a topic, then draft a report, then review it before output."
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Model</Label>
                    <Select className="text-xs w-full" value={aiModelId} onChange={(e) => setAiModelId(e.target.value)}>
                      {models.data?.map((m) => (
                        <option key={m.id} value={m.id}>{m.display_name || m.name}</option>
                      ))}
                    </Select>
                  </div>
                  <Button
                    className="w-full gap-2 active-tactile transition-transform"
                    disabled={!aiPrompt.trim() || !aiModelId || generate.isPending}
                    onClick={handleGenerate}
                  >
                    <Sparkles className="h-4 w-4" /> {generate.isPending ? "Generatingâ€¦" : "Generate"}
                  </Button>

                  {aiResult && (
                    <div className="space-y-2 rounded-lg border border-primary/30 bg-primary/5 p-3">
                      <div className="text-sm font-semibold text-foreground">{aiResult.name}</div>
                      {aiResult.description && (
                        <p className="text-xs text-muted-foreground">{aiResult.description}</p>
                      )}
                      <p className="text-[11px] text-muted-foreground">
                        {aiResult.graph.nodes.length} nodes Â· {aiResult.graph.edges.length} connections
                      </p>
                      <Button size="sm" className="w-full gap-2" onClick={applyGenerated}>
                        Apply to canvas
                      </Button>
                    </div>
                  )}
                </div>
              </DialogContent>
            </Dialog>
            <Button onClick={save} className="gap-2 active-tactile transition-transform">
              <Save className="h-4 w-4" /> Save
            </Button>
          </>
        }
      />

      <div className="space-y-3">
        <div className="flex items-center gap-2 rounded-xl border border-border/80 bg-card/50 p-3 backdrop-blur-xl shadow-3d-card">
          <div className="flex-1 space-y-1">
            <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
              Workflow name
            </Label>
            <Input className="text-xs" value={wfName} onChange={(e) => setWfName(e.target.value)} placeholder="Workflow name" />
          </div>
          <div className="flex-[2] space-y-1">
            <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
              Run input
            </Label>
            <Textarea
              className="min-h-[38px] text-xs resize-none"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="JSON or plain text inputâ€¦"
            />
          </div>
          <Button className="gap-2 active-tactile transition-transform self-end text-xs" disabled={running} onClick={run}>
            <Play className="h-3.5 w-3.5" /> {running ? "Runningâ€¦" : "Run Workflow"}
          </Button>
        </div>

        <div className="flex gap-3">
          <WorkflowNodePalette
            className="sticky top-4 self-start"
            onAddNode={(kind) => addNode(kind, { x: 60 + (nodes.length * 40) % 300, y: 80 + (nodes.length * 30) % 200 })}
          />
          <WorkflowCanvas
            className="h-[calc(100vh-380px)] min-h-[500px] flex-1"
            graphNodes={nodes}
            graphEdges={edges}
            nodeStatus={nodeStatus}
            selectedNodeId={selectedNodeId}
            onGraphChange={setGraph}
            onSelectNode={setSelectedNode}
            onCreateNode={addNode}
          />
        </div>
      </div>

      <WorkflowNodeConfig
        node={selectedNode}
        open={Boolean(selectedNode)}
        onOpenChange={(open) => !open && setSelectedNode(null)}
        agents={agents.data}
        workflows={data}
        currentWorkflowId={editId}
        onUpdate={updateNode}
      />

      <div className="animate-slide-up" style={{ animationDelay: "150ms" }}>
        <WorkflowConsole logs={logs} output={output} running={running} />
      </div>
    </div>
  );
}
