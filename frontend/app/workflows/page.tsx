"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Workflow as WorkflowIcon,
  Play,
  Save,
  FolderOpen,
  FilePlus,
  Box,
  Bot,
  Wrench,
  GitMerge,
  LogOut,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { streamSSE } from "@/lib/api";
import { useWorkflows, useCreateWorkflow, useAgents, useModels, useGenerateWorkflow, useWorkflowRun } from "@/hooks";
import { useWorkflowStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { PageHeader } from "@/components/page-header";
import { WorkflowNodeCard, type GNode } from "@/components/workflows/workflow-node-card";
import { WorkflowConsole, type WorkflowLogItem } from "@/components/workflows/workflow-console";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

type GEdge = { from_: string; to: string; condition?: string };

function layout(nodes: GNode[], edges: GEdge[]) {
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
  const perLayer: Record<number, GNode[]> = {};
  nodes.forEach((n) => {
    const l = layer[n.id] ?? 0;
    (perLayer[l] = perLayer[l] || []).push(n);
  });
  // Vertical flow: BFS depth -> row (y), index within a row -> column (x).
  const pos: Record<string, { x: number; y: number }> = {};
  Object.entries(perLayer).forEach(([l, ns]) => {
    ns.forEach((n, i) => (pos[n.id] = { x: 40 + i * 200, y: 40 + +l * 140 }));
  });
  return pos;
}

export default function WorkflowsPage() {
  const { data } = useWorkflows();
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

  const [wfName, setWfName] = React.useState("");
  const [aiPrompt, setAiPrompt] = React.useState("");
  const [aiModelId, setAiModelId] = React.useState("");
  const [aiResult, setAiResult] = React.useState<{
    name: string;
    description: string;
    graph: { nodes: GNode[]; edges: GEdge[] };
  } | null>(null);
  const [input, setInput] = React.useState("");
  const [newEdge, setNewEdge] = React.useState<GEdge>({ from_: "", to: "" });
  const [running, setRunning] = React.useState(false);
  const [nodeStatus, setNodeStatus] = React.useState<Record<string, string>>({});
  const [output, setOutput] = React.useState("");
  const [logs, setLogs] = React.useState<WorkflowLogItem[]>([]);
  const [editId, setEditId] = React.useState<string | null>(null);

  const canvasRef = React.useRef<HTMLDivElement>(null);
  const [draggingNode, setDraggingNode] = React.useState<{
    id: string;
    offsetX: number;
    offsetY: number;
  } | null>(null);

  const [connectingFromId, setConnectingFromId] = React.useState<string | null>(null);
  const [mousePosition, setMousePosition] = React.useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const pos = React.useMemo(() => {
    const layoutPos = layout(nodes, edges);
    const p: Record<string, { x: number; y: number }> = {};
    nodes.forEach((n) => {
      p[n.id] = n.position || layoutPos[n.id] || { x: 40, y: 40 };
    });
    return p;
  }, [nodes, edges]);

  React.useEffect(() => {
    if (!draggingNode && !connectingFromId) return;

    const handleGlobalMouseMove = (e: MouseEvent) => {
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect) return;

      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      if (draggingNode) {
        setGraph(
          nodes.map((n) => {
            if (n.id === draggingNode.id) {
              return {
                ...n,
                position: {
                  x: Math.max(0, mouseX - draggingNode.offsetX),
                  y: Math.max(0, mouseY - draggingNode.offsetY),
                },
              };
            }
            return n;
          }),
          edges
        );
      }

      if (connectingFromId) {
        setMousePosition({ x: mouseX, y: mouseY });
      }
    };

    const handleGlobalMouseUp = () => {
      setDraggingNode(null);
      setConnectingFromId(null);
    };

    window.addEventListener("mousemove", handleGlobalMouseMove);
    window.addEventListener("mouseup", handleGlobalMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleGlobalMouseMove);
      window.removeEventListener("mouseup", handleGlobalMouseUp);
    };
  }, [draggingNode, connectingFromId, nodes, edges, setGraph]);

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

  const addNode = (kind: GNode["kind"]) => {
    const id = `${kind}-${Math.random().toString(36).slice(2, 7)}`;
    const count = nodes.length;
    const node: GNode = {
      id,
      kind,
      label: kind,
      config: kind === "tool" ? { tool: "" } : {},
      merge_mode: kind === "merge" ? "all" : undefined,
      agent_id:
        kind === "agent" && agents.data?.length ? agents.data[0].id : undefined,
      position: {
        x: 60 + (count * 60) % 300,
        y: 80 + (count * 40) % 200,
      },
    };
    setGraph([...nodes, node], edges);
    setSelectedNode(id);
  };

  const updateNode = (patch: Partial<GNode>) => {
    setGraph(
      nodes.map((n) => (n.id === selectedNodeId ? { ...n, ...patch } : n)),
      edges,
    );
  };

  const addEdge = () => {
    if (!newEdge.from_ || !newEdge.to) return;
    setGraph(nodes, [...edges, { ...newEdge }]);
    setNewEdge({ from_: "", to: "" });
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
    toast.success("New workflow — canvas cleared");
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
    toast.success("Applied to canvas — review and Save");
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
    setLogs([]);
    try {
      await streamSSE(
        `/api/workflows/${editId}/run`,
        { input, stream: true },
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
                message: `Edge ${d.from} → ${d.to} taken`,
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

  const onNodeMouseDown = (e: React.MouseEvent, id: string) => {
    const target = e.target as HTMLElement;
    if (target.closest(".no-drag")) return;

    e.preventDefault();
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const node = nodes.find((n) => n.id === id);
    if (!node) return;

    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const nodeX = node.position?.x ?? pos[id]?.x ?? 0;
    const nodeY = node.position?.y ?? pos[id]?.y ?? 0;

    setDraggingNode({
      id,
      offsetX: mouseX - nodeX,
      offsetY: mouseY - nodeY,
    });
    setSelectedNode(id);
  };

  const onOutputPortMouseDown = (e: React.MouseEvent, sourceId: string) => {
    e.stopPropagation();
    e.preventDefault();
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const node = nodes.find((n) => n.id === sourceId);
    if (!node) return;

    const nodeX = node.position?.x ?? pos[sourceId]?.x ?? 0;
    const nodeY = node.position?.y ?? pos[sourceId]?.y ?? 0;

    const portX = nodeX + 80;
    const portY = nodeY + 70;

    setConnectingFromId(sourceId);
    setMousePosition({ x: portX, y: portY });
  };

  const onInputPortMouseUp = (e: React.MouseEvent, targetId: string) => {
    e.stopPropagation();
    if (connectingFromId && connectingFromId !== targetId) {
      const exists = edges.some((edge) => edge.from_ === connectingFromId && edge.to === targetId);
      if (!exists) {
        setGraph(nodes, [...edges, { from_: connectingFromId, to: targetId }]);
        toast.success("Connection added");
      }
    }
    setConnectingFromId(null);
  };

  const deleteNode = (id: string) => {
    const target = nodes.find((n) => n.id === id);
    const name = target?.label || id;
    if (!window.confirm(`Xóa node "${name}"? Hành động này sẽ làm mất cấu hình của node trên canvas.`)) return;
    setGraph(
      nodes.filter((x) => x.id !== id),
      edges.filter((edge) => edge.from_ !== id && edge.to !== id)
    );
    if (selectedNodeId === id) setSelectedNode(null);
    toast.success("Node deleted");
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
                  {data?.map((wf) => (
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
                    <Sparkles className="h-4 w-4" /> {generate.isPending ? "Generating…" : "Generate"}
                  </Button>

                  {aiResult && (
                    <div className="space-y-2 rounded-lg border border-primary/30 bg-primary/5 p-3">
                      <div className="text-sm font-semibold text-foreground">{aiResult.name}</div>
                      {aiResult.description && (
                        <p className="text-xs text-muted-foreground">{aiResult.description}</p>
                      )}
                      <p className="text-[11px] text-muted-foreground">
                        {aiResult.graph.nodes.length} nodes · {aiResult.graph.edges.length} connections
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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4 stagger">
        <div className="rounded-xl border border-border/80 bg-card/50 p-4 space-y-4 backdrop-blur-xl shadow-3d-card">
          <div className="space-y-2">
            <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Add node to canvas</Label>
            <div className="space-y-1.5">
              {(["input", "agent", "tool", "merge", "output"] as const).map((k) => {
                const NodeIcon =
                  k === "input" ? Box : k === "agent" ? Bot : k === "tool" ? Wrench : k === "merge" ? GitMerge : LogOut;
                return (
                  <Button key={k} variant="outline" className="w-full justify-start gap-2 text-xs py-2 active-tactile transition-transform" onClick={() => addNode(k)}>
                    <NodeIcon className="h-3.5 w-3.5 text-primary" /> {k}
                  </Button>
                );
              })}
            </div>
          </div>
          
          <div className="pt-2 border-t border-border/40 space-y-3">
            <div>
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Workflow details</Label>
              <Input className="mt-1 text-xs" value={wfName} onChange={(e) => setWfName(e.target.value)} placeholder="Workflow name" />
            </div>
            
            <div className="space-y-1.5">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Run input</Label>
              <Textarea className="min-h-[80px] text-xs resize-none" value={input} onChange={(e) => setInput(e.target.value)} placeholder="JSON or plain text input…" />
              <Button className="w-full gap-2 active-tactile transition-transform text-xs" disabled={running} onClick={run}>
                <Play className="h-3.5 w-3.5" /> {running ? "Running…" : "Run Workflow"}
              </Button>
            </div>
          </div>
        </div>

        <div 
          ref={canvasRef}
          className="relative h-[500px] overflow-auto rounded-xl border border-border/80 bg-card/30 backdrop-blur-sm lg:col-span-2 shadow-inner-edge select-none cursor-grab active:cursor-grabbing"
          style={{ 
            backgroundImage: 'radial-gradient(hsl(var(--foreground) / 0.05) 1px, transparent 1px)', 
            backgroundSize: '16px 16px' 
          }}
        >
          <div className="absolute w-[2000px] h-[1200px] inset-0">
            <svg className="pointer-events-none absolute inset-0 h-full w-full">
              {edges.map((e, i) => {
                const a = pos[e.from_];
                const b = pos[e.to];
                if (!a || !b) return null;
                const x1 = a.x + 80;
                const y1 = a.y + 70;
                const x2 = b.x + 80;
                const y2 = b.y;
                const dy = Math.abs(y2 - y1) * 0.5;
                const path = `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`;
                
                const mx = (x1 + x2) / 2;
                const my = (y1 + y2) / 2;

                return (
                  <g key={i} className="group pointer-events-auto">
                    <path
                      d={path}
                      stroke="hsl(var(--primary) / 0.25)"
                      strokeWidth={6}
                      fill="none"
                      className="opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                    />
                    <path
                      d={path}
                      stroke="hsl(var(--border))"
                      strokeWidth={2}
                      fill="none"
                      className="transition-colors group-hover:stroke-primary"
                    />
                    <path
                      d={path}
                      stroke="transparent"
                      strokeWidth={12}
                      fill="none"
                      className="cursor-pointer"
                      onClick={() => {
                        if (!window.confirm("Xóa kết nối này?")) return;
                        setGraph(nodes, edges.filter((_, j) => j !== i));
                      }}
                    />
                    <g
                      className="opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                      onClick={() => {
                        if (!window.confirm("Xóa kết nối này?")) return;
                        setGraph(nodes, edges.filter((_, j) => j !== i));
                        toast.success("Connection deleted");
                      }}
                    >
                      <circle cx={mx} cy={my} r={8} fill="hsl(var(--destructive))" />
                      <line x1={mx - 3.5} y1={my - 3.5} x2={mx + 3.5} y2={my + 3.5} stroke="white" strokeWidth={1.5} />
                      <line x1={mx + 3.5} y1={my - 3.5} x2={mx - 3.5} y2={my + 3.5} stroke="white" strokeWidth={1.5} />
                    </g>
                  </g>
                );
              })}

              {connectingFromId && (
                (() => {
                  const source = pos[connectingFromId];
                  if (!source) return null;
                  const x1 = source.x + 80;
                  const y1 = source.y + 70;
                  const x2 = mousePosition.x;
                  const y2 = mousePosition.y;
                  const dy = Math.abs(y2 - y1) * 0.5;
                  return (
                    <path
                      d={`M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`}
                      stroke="hsl(var(--primary))"
                      strokeWidth={2}
                      strokeDasharray="4 4"
                      fill="none"
                    />
                  );
                })()
              )}
            </svg>

            {nodes.map((n) => (
              <WorkflowNodeCard
                key={n.id}
                node={n}
                position={pos[n.id] || { x: 0, y: 0 }}
                isSelected={selectedNodeId === n.id}
                status={nodeStatus[n.id]}
                connectingFromId={connectingFromId}
                onNodeMouseDown={onNodeMouseDown}
                onOutputPortMouseDown={onOutputPortMouseDown}
                onInputPortMouseUp={onInputPortMouseUp}
                onDeleteNode={deleteNode}
              />
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-border/80 bg-card/50 p-4 space-y-4 backdrop-blur-xl shadow-3d-card">
          <div className="space-y-2">
            <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Node Config</Label>
            {selectedNodeId ? (
              <div className="space-y-3">
                <div className="space-y-1">
                  <span className="text-[10px] text-muted-foreground">Label name</span>
                  <Input
                    className="text-xs"
                    value={nodes.find((n) => n.id === selectedNodeId)?.label || ""}
                    onChange={(e) => updateNode({ label: e.target.value })}
                    placeholder="Label name"
                  />
                </div>
                {nodes.find((n) => n.id === selectedNodeId)?.kind === "agent" && (
                  <div className="space-y-1">
                    <span className="text-[10px] text-muted-foreground">Target Agent</span>
                    <Select
                      className="text-xs w-full"
                      value={nodes.find((n) => n.id === selectedNodeId)?.agent_id || ""}
                      onChange={(e) => updateNode({ agent_id: e.target.value })}
                    >
                      {agents.data?.map((a) => (
                        <option key={a.id} value={a.id}>{a.name}</option>
                      ))}
                    </Select>
                  </div>
                )}
                {nodes.find((n) => n.id === selectedNodeId)?.kind === "merge" && (
                  <div className="space-y-1">
                    <span className="text-[10px] text-muted-foreground">Merge logic</span>
                    <Select
                      className="text-xs w-full"
                      value={nodes.find((n) => n.id === selectedNodeId)?.merge_mode || "all"}
                      onChange={(e) => updateNode({ merge_mode: e.target.value as any })}
                    >
                      <option value="all">Wait all ancestors</option>
                      <option value="any">Wait any ancestor</option>
                    </Select>
                  </div>
                )}
                {nodes.find((n) => n.id === selectedNodeId)?.kind === "tool" && (
                  <div className="space-y-1">
                    <span className="text-[10px] text-muted-foreground">Tool to invoke</span>
                    <Input
                      className="text-xs"
                      value={nodes.find((n) => n.id === selectedNodeId)?.config.tool || ""}
                      onChange={(e) => updateNode({ config: { tool: e.target.value } })}
                      placeholder="e.g. read_attachment"
                    />
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground/80 py-4 text-center border border-dashed border-border/60 rounded-lg bg-muted/10">
                Select node on canvas
              </div>
            )}
          </div>

          <div className="pt-3 border-t border-border/40 space-y-3">
            <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">Connect Nodes</Label>
            <div className="flex gap-1.5">
              <Select className="text-xs flex-1" value={newEdge.from_} onChange={(e) => setNewEdge({ ...newEdge, from_: e.target.value })}>
                <option value="">From</option>
                {nodes.map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
              </Select>
              <Select className="text-xs flex-1" value={newEdge.to} onChange={(e) => setNewEdge({ ...newEdge, to: e.target.value })}>
                <option value="">To</option>
                {nodes.map((n) => <option key={n.id} value={n.id}>{n.label}</option>)}
              </Select>
            </div>
            <Button size="sm" variant="secondary" className="w-full text-xs active-tactile transition-transform" onClick={addEdge}>Add Connection</Button>
            
            {edges.length > 0 && (
              <div className="pt-2 border-t border-border/30 space-y-1.5">
                <span className="text-[10px] uppercase font-semibold tracking-wider text-muted-foreground/85">Existing Connections</span>
                <div className="space-y-1 max-h-[120px] overflow-y-auto pr-1">
                  {edges.map((e, i) => (
                    <div key={i} className="flex items-center justify-between text-[11px] rounded bg-muted/40 border border-border/30 px-2 py-1">
                      <span className="truncate max-w-[80%] font-mono text-muted-foreground">
                        {nodes.find((n) => n.id === e.from_)?.label} → {nodes.find((n) => n.id === e.to)?.label}
                      </span>
                      <button 
                        onClick={() => {
                          if (!window.confirm("Xóa kết nối này?")) return;
                          setGraph(nodes, edges.filter((_, j) => j !== i));
                        }} 
                        className="text-destructive hover:scale-115 transition-transform font-bold px-1 text-xs"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="animate-slide-up" style={{ animationDelay: "150ms" }}>
        <WorkflowConsole logs={logs} output={output} running={running} />
      </div>
    </div>
  );
}
