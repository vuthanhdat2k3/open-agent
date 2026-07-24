"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Workflow as WorkflowIcon,
  Plus,
  Play,
  Save,
  FolderOpen,
  Box,
  Bot,
  Wrench,
  GitMerge,
  LogOut,
  Terminal,
  Trash2,
  RefreshCw,
} from "lucide-react";
import { streamSSE } from "@/lib/api";
import { useWorkflows, useCreateWorkflow, useDeleteWorkflow, useAgents } from "@/hooks";
import { useWorkflowStore } from "@/stores";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { PageHeader } from "@/components/page-header";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

type GNode = {
  id: string;
  kind: "input" | "agent" | "tool" | "merge" | "output" | "approval" | "sub_workflow";
  label: string;
  agent_id?: string;
  merge_mode?: "all" | "any";
  config: Record<string, any>;
  position?: { x: number; y: number };
};
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
  const pos: Record<string, { x: number; y: number }> = {};
  Object.entries(perLayer).forEach(([l, ns]) => {
    ns.forEach((n, i) => (pos[n.id] = { x: 40 + +l * 240, y: 40 + i * 120 }));
  });
  return pos;
}

export default function WorkflowsPage() {
  const { data, isLoading } = useWorkflows();
  const create = useCreateWorkflow();
  const del = useDeleteWorkflow();
  const agents = useAgents();
  const { nodes, edges, selectedNodeId, setGraph, setSelectedNode } = useWorkflowStore();

  const [wfName, setWfName] = React.useState("");
  const [input, setInput] = React.useState("");
  const [newEdge, setNewEdge] = React.useState<GEdge>({ from_: "", to: "" });
  const [running, setRunning] = React.useState(false);
  const [nodeStatus, setNodeStatus] = React.useState<Record<string, string>>({});
  const [output, setOutput] = React.useState("");
  const [editId, setEditId] = React.useState<string | null>(null);

  // Drag and drop states
  const canvasRef = React.useRef<HTMLDivElement>(null);
  const [draggingNode, setDraggingNode] = React.useState<{
    id: string;
    offsetX: number;
    offsetY: number;
  } | null>(null);

  // Connection dragging states
  const [connectingFromId, setConnectingFromId] = React.useState<string | null>(null);
  const [mousePosition, setMousePosition] = React.useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // Compute node positions dynamically
  const pos = React.useMemo(() => {
    const layoutPos = layout(nodes, edges);
    const p: Record<string, { x: number; y: number }> = {};
    nodes.forEach((n) => {
      p[n.id] = n.position || layoutPos[n.id] || { x: 40, y: 40 };
    });
    return p;
  }, [nodes, edges]);

  // Handle global mousemove and mouseup for smooth node/connection dragging
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

  // Initialize node positions using autolayout if loaded without coordinates
  React.useEffect(() => {
    if (nodes.length > 0 && !nodes.every((n) => n.position?.x != null)) {
      const calculatedPos = layout(nodes, edges);
      const updatedNodes = nodes.map((n) => ({
        ...n,
        position: n.position || calculatedPos[n.id] || { x: 40, y: 40 },
      }));
      setGraph(updatedNodes, edges);
    }
  }, [nodes.length]);

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

  const loadWorkflow = (wf: any) => {
    setWfName(wf.name);
    setEditId(wf.id);
    setGraph(wf.graph.nodes, wf.graph.edges);
    setSelectedNode(null);
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
    try {
      await streamSSE(
        `/api/workflows/${editId}/run`,
        { input, stream: true },
        (ev) => {
          const d = ev.data;
          if (ev.event === "node_start")
            setNodeStatus((s) => ({ ...s, [d.node_id]: "running" }));
          else if (ev.event === "node_done")
            setNodeStatus((s) => ({ ...s, [d.node_id]: "done" }));
          else if (ev.event === "node_error")
            setNodeStatus((s) => ({ ...s, [d.node_id]: "error" }));
          else if (ev.event === "done") setOutput(d.output || "");
        },
      );
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setRunning(false);
    }
  };

  // Node drag start handler
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

  // Connection dragging source port mouse down handler
  const onOutputPortMouseDown = (e: React.MouseEvent, sourceId: string) => {
    e.stopPropagation();
    e.preventDefault();
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const node = nodes.find((n) => n.id === sourceId);
    if (!node) return;

    const nodeX = node.position?.x ?? pos[sourceId]?.x ?? 0;
    const nodeY = node.position?.y ?? pos[sourceId]?.y ?? 0;

    const portX = nodeX + 160; // Right port x position (node width is 160)
    const portY = nodeY + 35;  // Center port y position (node height is 70)

    setConnectingFromId(sourceId);
    setMousePosition({ x: portX, y: portY });
  };

  // Connection dragging target port mouse up handler
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

  const nodeColor = (id?: string) =>
    id && nodeStatus[id] === "done"
      ? "border-success"
      : id && nodeStatus[id] === "running"
        ? "border-info"
        : id && nodeStatus[id] === "error"
          ? "border-destructive"
          : "border-border";

  return (
    <div className="space-y-6">
      <PageHeader
        icon={WorkflowIcon}
        title="Workflows"
        description="Connect agents into a parallel graph"
        actions={
          <>
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
                    <Button
                      key={wf.id}
                      variant="outline"
                      className="w-full justify-start"
                      onClick={() => loadWorkflow(wf)}
                    >
                      {wf.name}
                    </Button>
                  ))}
                </div>
              </DialogContent>
            </Dialog>
            <Button variant="outline" className="gap-2 active-tactile transition-transform" onClick={handleAutoLayout}>
              <RefreshCw className="h-4 w-4" /> Auto-Layout
            </Button>
            <Button onClick={save} className="gap-2 active-tactile transition-transform">
              <Save className="h-4 w-4" /> Save
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4 stagger">
        <div className="rounded-xl border border-border/60 bg-card/40 p-4 space-y-4 backdrop-blur-md">
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
          className="relative h-[500px] overflow-auto rounded-xl border border-border bg-card/30 backdrop-blur-sm lg:col-span-2 shadow-inner-edge select-none cursor-grab active:cursor-grabbing"
          style={{ 
            backgroundImage: 'radial-gradient(hsl(var(--foreground) / 0.05) 1px, transparent 1px)', 
            backgroundSize: '16px 16px' 
          }}
        >
          {/* Scrollable canvas wrapper */}
          <div className="absolute w-[2000px] h-[1200px] inset-0">
            <svg className="pointer-events-none absolute inset-0 h-full w-full">
              {/* Connection curves */}
              {edges.map((e, i) => {
                const a = pos[e.from_];
                const b = pos[e.to];
                if (!a || !b) return null;
                const x1 = a.x + 160;
                const y1 = a.y + 35;
                const x2 = b.x;
                const y2 = b.y + 35;
                const dx = Math.abs(x2 - x1) * 0.5;
                const path = `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
                
                const mx = (x1 + x2) / 2;
                const my = (y1 + y2) / 2;

                return (
                  <g key={i} className="group pointer-events-auto">
                    {/* Hover highlights */}
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
                    {/* Invisible fat line to make hover easier */}
                    <path
                      d={path}
                      stroke="transparent"
                      strokeWidth={12}
                      fill="none"
                      className="cursor-pointer"
                      onClick={() => setGraph(nodes, edges.filter((_, j) => j !== i))}
                    />
                    {/* Tiny delete connection button */}
                    <g
                      className="opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                      onClick={() => {
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

              {/* Live drawing connection curve */}
              {connectingFromId && (
                (() => {
                  const source = pos[connectingFromId];
                  if (!source) return null;
                  const x1 = source.x + 160;
                  const y1 = source.y + 35;
                  const x2 = mousePosition.x;
                  const y2 = mousePosition.y;
                  const dx = Math.abs(x2 - x1) * 0.5;
                  return (
                    <path
                      d={`M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`}
                      stroke="hsl(var(--primary))"
                      strokeWidth={2}
                      strokeDasharray="4 4"
                      fill="none"
                    />
                  );
                })()
              )}
            </svg>

            {/* Draggable workflow Nodes */}
            {nodes.map((n) => {
              const p = pos[n.id] || { x: 0, y: 0 };
              const NodeIcon =
                n.kind === "input" ? Box : n.kind === "agent" ? Bot : n.kind === "tool" ? Wrench : n.kind === "merge" ? GitMerge : LogOut;
              return (
                <div
                  key={n.id}
                  className={`absolute flex w-[160px] h-[70px] select-none cursor-grab active:cursor-grabbing flex-col justify-between rounded-xl border bg-card/95 dark:bg-card/85 p-3 text-xs shadow-card transition-shadow duration-200 hover:shadow-md hover:border-primary/45 ${nodeColor(n.id)} ${
                    selectedNodeId === n.id ? "ring-2 ring-primary border-primary/50" : ""
                  }`}
                  style={{ left: p.x, top: p.y }}
                  onMouseDown={(e) => onNodeMouseDown(e, n.id)}
                >
                  {/* Target Port handle (Left) */}
                  <div
                    className={`absolute -left-2 top-[25px] h-4.5 w-4.5 rounded-full border border-border bg-background flex items-center justify-center cursor-crosshair z-30 transition-all hover:scale-125 hover:border-primary ${
                      connectingFromId && connectingFromId !== n.id ? "animate-pulse-soft border-primary/80 bg-primary/20 scale-110" : ""
                    }`}
                    onMouseUp={(e) => onInputPortMouseUp(e, n.id)}
                    title="Connect parent output here"
                  >
                    <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground hover:bg-primary" />
                  </div>

                  {/* Source Port handle (Right) */}
                  <div
                    className="absolute -right-2 top-[25px] h-4.5 w-4.5 rounded-full border border-border bg-background flex items-center justify-center cursor-crosshair z-30 transition-all hover:scale-125 hover:border-primary"
                    onMouseDown={(e) => onOutputPortMouseDown(e, n.id)}
                    title="Drag to child input"
                  >
                    <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground hover:bg-primary" />
                  </div>

                  <div className="flex items-center justify-between gap-1 font-bold tracking-tight">
                    <div className="flex items-center gap-1.5">
                      <NodeIcon className="h-3.5 w-3.5 text-primary" /> 
                      <span className="capitalize">{n.kind}</span>
                    </div>
                    {/* Delete node button */}
                    <button
                      className="no-drag text-muted-foreground hover:text-destructive transition-colors p-0.5 rounded hover:bg-muted"
                      onClick={(e) => {
                        e.stopPropagation();
                        setGraph(
                          nodes.filter((x) => x.id !== n.id),
                          edges.filter((edge) => edge.from_ !== n.id && edge.to !== n.id)
                        );
                        if (selectedNodeId === n.id) setSelectedNode(null);
                        toast.success("Node deleted");
                      }}
                      title="Delete node"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>
                  <div className="truncate text-[10px] text-muted-foreground/90 font-mono bg-muted/40 px-1.5 py-0.5 rounded border border-border/30">{n.label}</div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="rounded-xl border border-border/60 bg-card/40 p-4 space-y-4 backdrop-blur-md">
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
                      <button onClick={() => setGraph(nodes, edges.filter((_, j) => j !== i))} className="text-destructive hover:scale-115 transition-transform font-bold px-1 text-xs">
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
        <Card glass className="overflow-hidden">
          <CardHeader className="flex flex-row items-center gap-3 border-b border-border/60 bg-muted/20 px-4 py-3">
            <div className="grid h-8 w-8 place-items-center rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 text-primary shadow-inner-edge">
              <Terminal className="h-4 w-4" />
            </div>
            <CardTitle className="text-sm font-semibold tracking-tight">Run Output Console</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <pre className="max-h-80 overflow-auto whitespace-pre-wrap bg-muted/10 p-4 font-mono text-[11px] text-foreground leading-normal scrollbar-thin">
              {output || "Console waiting for workflow execution input…"}
            </pre>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
