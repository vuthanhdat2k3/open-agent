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
  LibraryBig,
  UploadCloud,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { publishWorkflowToCatalog } from "@/lib/automations/api";
import { api, streamSSE } from "@/lib/api";
import { useWorkflows, useCreateWorkflow, useUpdateWorkflow, useAgents, useModels, useGenerateWorkflow, useWorkflowRun } from "@/hooks";
import { useWorkflowStore } from "@/stores";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingSkeleton } from "@/components/shared";
import { useTranslation } from "@/lib/i18n";
import { WorkflowNodePalette } from "@/components/workflows/workflow-node-palette";
import { WorkflowCanvas } from "@/components/workflows/workflow-canvas";
import { WorkflowNodeConfig } from "@/components/workflows/workflow-node-config";
import { WorkflowConsole, type WorkflowLogItem } from "@/components/workflows/workflow-console";
import { RunKpiStrip } from "@/components/workflows/run-kpi-strip";
import type { GraphEdge, GraphNode } from "@/types";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

function calculateDagLayout(nodes: GraphNode[], edges: GraphEdge[]) {
  if (nodes.length === 0) return {};
  const adj: Record<string, string[]> = {};
  const inDegree: Record<string, number> = {};
  nodes.forEach((n) => {
    adj[n.id] = [];
    inDegree[n.id] = 0;
  });
  edges.forEach((e) => {
    if (adj[e.from_]) adj[e.from_].push(e.to);
    inDegree[e.to] = (inDegree[e.to] || 0) + 1;
  });

  const roots = nodes.filter((n) => inDegree[n.id] === 0 || ["input", "scheduler", "integration"].includes(n.kind));
  const queue: { id: string; layer: number }[] = (roots.length > 0 ? roots : [nodes[0]]).map((n) => ({ id: n.id, layer: 0 }));

  const layer: Record<string, number> = {};
  queue.forEach((q) => (layer[q.id] = 0));
  const visited = new Set<string>(queue.map((q) => q.id));

  while (queue.length > 0) {
    const { id: cur, layer: curL } = queue.shift()!;
    (adj[cur] || []).forEach((nxt) => {
      const nextL = curL + 1;
      if (!layer[nxt] || nextL > layer[nxt]) {
        layer[nxt] = nextL;
      }
      if (!visited.has(nxt)) {
        visited.add(nxt);
        queue.push({ id: nxt, layer: nextL });
      }
    });
  }

  nodes.forEach((n) => {
    if (layer[n.id] == null) layer[n.id] = 0;
  });

  const perLayer: Record<number, GraphNode[]> = {};
  nodes.forEach((n) => {
    const l = layer[n.id] ?? 0;
    (perLayer[l] = perLayer[l] || []).push(n);
  });

  const nodeWidth = 214;
  const nodeGapX = 66;
  const rankGapY = 170;
  const centerX = 460;

  const pos: Record<string, { x: number; y: number }> = {};
  Object.entries(perLayer).forEach(([lStr, ns]) => {
    const l = parseInt(lStr, 10);
    const rowWidth = ns.length * nodeWidth + (ns.length - 1) * nodeGapX;
    const startX = Math.max(40, centerX - rowWidth / 2);
    ns.forEach((n, i) => {
      pos[n.id] = {
        x: Math.round(startX + i * (nodeWidth + nodeGapX)),
        y: Math.round(40 + l * rankGapY),
      };
    });
  });

  return pos;
}

export default function WorkflowEditor() {
  const { t, dict, locale, tx } = useTranslation();
  const workflows = useWorkflows();
  const create = useCreateWorkflow();
  const update = useUpdateWorkflow();
  const generate = useGenerateWorkflow();
  const agents = useAgents();
  const models = useModels(true);
  const data = workflows.data;
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
  const router = useRouter();
  const [publishDialogOpen, setPublishDialogOpen] = React.useState(false);
  const [publishCategory, setPublishCategory] = React.useState("custom");
  const [publishDescription, setPublishDescription] = React.useState("");
  const [isPublishing, setIsPublishing] = React.useState(false);

  const handlePublishToMarketplace = async () => {
    if (!editId) {
      toast.error(tx("Vui lòng lưu workflow trước khi đẩy lên Marketplace", "Please save the workflow before publishing to Marketplace"));
      return;
    }
    setIsPublishing(true);
    try {
      await publishWorkflowToCatalog({
        workflow_id: editId,
        category: publishCategory,
        description: publishDescription || undefined,
        outcome: publishDescription || undefined,
        icon: "zap",
      });
      toast.success(tx("Đã đẩy quy trình lên Marketplace thành công!", "Successfully published workflow to Marketplace!"));
      setPublishDialogOpen(false);
    } catch (e: any) {
      toast.error(e.message || tx("Không thể xuất bản lên Marketplace", "Failed to publish to Marketplace"));
    } finally {
      setIsPublishing(false);
    }
  };

  // Initialize activeRunId once on mount if 'run' is present in URL
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const initialRun = url.searchParams.get("run");
    if (initialRun && initialRun !== activeRunId) {
      setActiveRun(initialRun);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load a workflow directly when opened with ?edit=<id> (e.g. from Automations)
  const didLoadEditRef = React.useRef(false);
  React.useEffect(() => {
    if (didLoadEditRef.current || typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const editIdParam = url.searchParams.get("edit");
    if (!editIdParam) return;
    const wf = data?.find((w) => w.id === editIdParam);
    if (wf) {
      didLoadEditRef.current = true;
      loadWorkflow(wf);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  // Update browser URL silently without triggering Next.js router re-render or scrolling reset
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const currentRun = url.searchParams.get("run");
    if (activeRunId && currentRun !== activeRunId) {
      url.searchParams.set("run", activeRunId);
      window.history.replaceState(null, "", url.toString());
    } else if (!activeRunId && currentRun) {
      url.searchParams.delete("run");
      window.history.replaceState(null, "", url.toString());
    }
  }, [activeRunId]);

  const [wfName, setWfName] = React.useState("");
  const [aiPrompt, setAiPrompt] = React.useState("");
  const [aiModelId, setAiModelId] = React.useState("");
  const [aiResult, setAiResult] = React.useState<{
    name: string;
    description: string;
    graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  } | null>(null);
  const [input, setInput] = React.useState("");
  const [inputMode, setInputMode] = React.useState<"text" | "json">("text");
  const [followRunningNode, setFollowRunningNode] = React.useState(true);
  const [running, setRunning] = React.useState(false);
  const [nodeStatus, setNodeStatus] = React.useState<Record<string, string>>({});
  const [output, setOutput] = React.useState("");
  const [logs, setLogs] = React.useState<WorkflowLogItem[]>([]);
  const [editId, setEditId] = React.useState<string | null>(null);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) || null;

  // Fade a node/edge's "done" status back to idle a few seconds after it
  // finishes, so the running-state highlight reads as transient feedback
  // rather than a permanent marker. Only applies while a run is actively
  // streaming — restoring a past completed run's status (see the
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
    // Only auto-place nodes that the user has not positioned yet.
    // Re-laying out the whole graph on any change would clobber positions
    // the user just dragged — the effect must be a no-op for already-placed
    // nodes and only compute coordinates for new arrivals.
    const unplaced = nodes.filter((n) => n.position?.x == null);
    if (unplaced.length === 0) return;
    const calculatedPos = calculateDagLayout(nodes, edges);
    const updatedNodes = nodes.map((n) =>
      n.position?.x != null
        ? n
        : { ...n, position: calculatedPos[n.id] || { x: 40, y: 40 } },
    );
    setGraph(updatedNodes, edges);
  }, [nodes, edges, setGraph]);

  const addNode = (kind: GraphNode["kind"], position: { x: number; y: number }) => {
    const id = `${kind}-${Math.random().toString(36).slice(2, 7)}`;
    const node: GraphNode = {
      id,
      kind,
      label: kind,
      parameters: kind === "tool" ? { tool: "" } : kind === "agent" ? { mode: "custom", temperature: 0.7, max_iterations: 12 } : {},
      config: {},
      merge_mode: kind === "merge" ? "all" : undefined,
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
    toast.success(tx("Workflow mới — đã xóa canvas", "New workflow — canvas cleared"));
  };

  const loadWorkflow = (wf: any) => {
    setWfName(wf.name);
    setEditId(wf.id);
    const loadedNodes: GraphNode[] = Array.isArray(wf.graph?.nodes) ? wf.graph.nodes : [];
    const loadedEdges: GraphEdge[] = Array.isArray(wf.graph?.edges) ? wf.graph.edges : [];
    setGraph(loadedNodes, loadedEdges);
    setSelectedNode(null);
    setLogs([]);
    setOutput("");
    toast.success(`Loaded workflow: ${wf.name}`);
  };

  const save = async () => {
    try {
      if (editId) {
        await update.mutateAsync({
          id: editId,
          data: {
            name: wfName || "workflow",
            graph: { nodes, edges },
          },
        });
      } else {
        const created = await create.mutateAsync({
          name: wfName || "workflow",
          description: "",
          graph: { nodes, edges },
        });
        setEditId(created.id);
      }
      toast.success(tx("Đã lưu workflow", "Workflow saved"));
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
    if (activeRunId !== run.id) {
      setActiveRun(run.id, run.status);
    }
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
  }, [workflowRun.data, setActiveRun, activeRunId]);

  const runReplay = async (runId: string) => {
    try {
      setRunning(true);
      setLogs([]);
      setOutput("");
      setNodeStatus({});
      const res = await api.post<any>(`/api/workflows/runs/${runId}/replay`);
      setOutput(res.output || "");
      const divergence = res.diverged;
      setLogs([
        {
          id: `replay-${Date.now()}`,
          ts: Date.now(),
          event: "done",
          message: divergence
            ? t("pages.workflows.replayDiverged", "Replay diverged from original run")
            : t("pages.workflows.replayCompleted", "Replay completed (deterministic, no side effects)"),
        },
      ]);
      toast.success(
        divergence
          ? t("pages.workflows.replayDiverged", "Replay diverged from original run")
          : t("pages.workflows.replayCompleted", "Replay completed"),
      );
    } catch (e: any) {
      toast.error(e.message || t("pages.workflows.replay", "Replay failed"));
    } finally {
      setRunning(false);
    }
  };

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
    const calculatedPos = calculateDagLayout(aiResult.graph.nodes, aiResult.graph.edges);
    const positionedNodes = aiResult.graph.nodes.map((n) => ({
      ...n,
      position: n.position || calculatedPos[n.id] || { x: 40, y: 40 },
    }));
    setGraph(positionedNodes, aiResult.graph.edges);
    setSelectedNode(null);
    setAiResult(null);
    setAiPrompt("");
    toast.success(tx("Đã áp dụng vào canvas — hãy xem lại và Lưu", "Applied to canvas — review and Save"));
  };

  const handleAutoLayout = () => {
    const calculatedPos = calculateDagLayout(nodes, edges);
    const updatedNodes = nodes.map((n) => ({
      ...n,
      position: calculatedPos[n.id] || { x: 40, y: 40 },
    }));
    setGraph(updatedNodes, edges);
    toast.success(tx("Đã áp dụng tự động sắp xếp Graph", "Graph auto-layout applied"));
  };

  const handleDeleteNode = (id: string) => {
    setGraph(
      nodes.filter((n) => n.id !== id),
      edges.filter((e) => e.from_ !== id && e.to !== id),
    );
    if (selectedNodeId === id) setSelectedNode(null);
    toast.success(tx("Đã xóa Node", "Node deleted"));
  };

  const handleEditEdgeCondition = (edgeId: string) => {
    const [fromId, rest] = edgeId.split("->");
    const toId = rest?.split("#")[0] ?? "";
    const edge = edges.find((e) => e.from_ === fromId && e.to === toId);
    const current = edge?.condition ?? "";
    const input = window.prompt(
      t(
        "pages.workflows.edgeConditionPrompt",
        "Edge condition (leave empty to clear).\n\nExamples:\n  output.category == 'sales'\n  'urgent' in output.text\n  true",
      ),
      current,
    );
    if (input === null) return;
    const nextEdges = edges.map((e) =>
      e.from_ === fromId && e.to === toId ? { ...e, condition: input.trim() || undefined } : e,
    );
    setGraph(nodes, nextEdges);
  };

  const formatJsonInput = () => {
    if (!input.trim()) return;
    try {
      const parsed = JSON.parse(input);
      setInput(JSON.stringify(parsed, null, 2));
      toast.success(t("pages.workflows.formatJson", "Formatted JSON"));
    } catch {
      toast.error(t("pages.workflows.invalidJson", "Invalid JSON payload"));
    }
  };

  const run = async () => {
    if (!editId) {
      toast.error(tx("Lưu workflow trước khi chạy", "Save the workflow first to run it"));
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

  return (
    <div className="space-y-6">
      <PageHeader
        icon={WorkflowIcon}
        title={dict.pages.workflows.title}
        description={dict.pages.workflows.description}
        actions={
          <>
            <Button
              variant="outline"
              className="gap-2 active-tactile transition-transform text-primary border-primary/30 hover:bg-primary/10"
              onClick={() => router.push("/automations")}
            >
              <LibraryBig className="h-4 w-4 text-primary" /> {tx("Marketplace", "Marketplace")}
            </Button>
            {editId && (
              <Dialog open={publishDialogOpen} onOpenChange={setPublishDialogOpen}>
                <DialogTrigger asChild>
                  <Button variant="outline" className="gap-2 active-tactile transition-transform border-emerald-500/40 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/10">
                    <UploadCloud className="h-4 w-4" /> {tx("Đẩy lên Market", "Publish to Market")}
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>{tx("Xuất bản lên Workflow Marketplace", "Publish to Workflow Marketplace")}</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 py-2 text-xs">
                    <p className="text-muted-foreground">
                      {tx(
                        "Quy trình này sẽ xuất hiện trên Marketplace của tổ chức để các thành viên khác có thể cài đặt và sử dụng bản sao độc lập.",
                        "This workflow will be available on the organization Marketplace for other members to install and run independently."
                      )}
                    </p>
                    <div className="space-y-1.5">
                      <Label>{tx("Danh mục (Category)", "Category")}</Label>
                      <Select className="w-full text-xs" value={publishCategory} onChange={(e) => setPublishCategory(e.target.value)}>
                        <option value="custom">{tx("Tùy chỉnh (Custom)", "Custom")}</option>
                        <option value="daily_planning">{tx("Lập kế hoạch hàng ngày (Daily planning)", "Daily planning")}</option>
                        <option value="customer_intelligence">{tx("Thông tin khách hàng (Customer intelligence)", "Customer intelligence")}</option>
                        <option value="research">{tx("Nghiên cứu & Báo cáo (Research)", "Research")}</option>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label>{tx("Mô tả tóm tắt", "Summary Description")}</Label>
                      <Textarea
                        className="text-xs"
                        placeholder={tx("Mô tả mục tiêu của workflow mẫu...", "Describe the template goal...")}
                        value={publishDescription}
                        onChange={(e) => setPublishDescription(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="flex justify-end gap-2">
                    <Button variant="outline" size="sm" onClick={() => setPublishDialogOpen(false)}>
                      {tx("Hủy", "Cancel")}
                    </Button>
                    <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white" disabled={isPublishing} onClick={handlePublishToMarketplace}>
                      {isPublishing ? tx("Đang xuất bản...", "Publishing...") : tx("Xác nhận Đẩy lên Market", "Publish Now")}
                    </Button>
                  </div>
                </DialogContent>
              </Dialog>
            )}
            <Button variant="outline" className="gap-2 active-tactile transition-transform" onClick={newWorkflow}>
              <FilePlus className="h-4 w-4" /> {dict.pages.workflows.btnNew}
            </Button>
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="outline" className="gap-2 active-tactile transition-transform">
                  <FolderOpen className="h-4 w-4" /> {dict.pages.workflows.btnLoad}
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>{tx("Tải Workflow đã lưu", "Load Saved Workflow")}</DialogTitle>
                </DialogHeader>
                <div className="space-y-2">
                  {workflows.isLoading ? (
                    <LoadingSkeleton variant="table" />
                  ) : workflows.isError ? (
                    <ErrorState
                      title={tx("Không thể tải workflow", "Unable to load workflows")}
                      description={tx("Danh sách workflow chưa sẵn sàng.", "Saved workflows could not be loaded.")}
                      onRetry={() => void workflows.refetch()}
                    />
                  ) : (
                    data?.map((wf) => (
                      <DialogClose asChild key={wf.id}>
                        <Button
                          variant="outline"
                          className="w-full justify-start"
                          onClick={() => loadWorkflow(wf)}
                        >
                          {wf.name}
                        </Button>
                      </DialogClose>
                    ))
                  )}
                </div>
              </DialogContent>
            </Dialog>
            <Button variant="outline" className="gap-2 active-tactile transition-transform" onClick={handleAutoLayout}>
              <RefreshCw className="h-4 w-4" /> {dict.pages.workflows.btnAutoLayout}
            </Button>
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="outline" className="gap-2 active-tactile transition-transform border-primary/40 bg-primary/5 hover:bg-primary/10">
                  <Sparkles className="h-4 w-4 text-primary animate-pulse" /> {dict.pages.workflows.btnAiGenerate}
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-[540px] bg-card/95 backdrop-blur-2xl border-border/80 shadow-2xl">
                <DialogHeader>
                  <div className="flex items-center gap-2.5">
                    <div className="grid h-9 w-9 place-items-center rounded-xl bg-primary/15 text-primary border border-primary/30">
                      <Sparkles className="h-5 w-5" />
                    </div>
                    <div>
                      <DialogTitle className="text-base font-bold">
                        {tx("AI Thiết kế Workflow Tự động", "Generate Workflow with AI")}
                      </DialogTitle>
                      <p className="text-xs text-muted-foreground">
                        {tx("Mô tả quy trình tự động hóa của bạn bằng ngôn ngữ tự nhiên", "Describe your automation routine in natural language")}
                      </p>
                    </div>
                  </div>
                </DialogHeader>

                <div className="space-y-4 pt-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
                      {tx("Mô tả quy trình mong muốn", "Describe what the workflow should do")}
                    </Label>
                    <Textarea
                      className="min-h-[110px] text-xs leading-relaxed"
                      value={aiPrompt}
                      onChange={(e) => setAiPrompt(e.target.value)}
                      placeholder={dict.pages.workflows.aiPromptPlaceholder}
                    />
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      <button
                        type="button"
                        onClick={() => setAiPrompt(tx("Quét Google Drive 6h sáng hàng ngày, lọc các file mới cập nhật và phân tích tổng hợp báo cáo", "Scan Google Drive daily at 6 AM, filter updated files and synthesize summary report"))}
                        className="rounded-full border border-border/60 bg-muted/40 px-2 py-0.5 text-[10px] text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                      >
                        {tx("⚡ Quét Drive 6h sáng hàng ngày", "⚡ Daily Drive Scan 6 AM")}
                      </button>
                      <button
                        type="button"
                        onClick={() => setAiPrompt(tx("Đọc Gmail mỗi sáng lúc 8h, lọc email khẩn cấp và tạo bản nháp phản hồi để tôi duyệt", "Read Gmail daily at 8 AM, filter urgent emails and draft response for my approval"))}
                        className="rounded-full border border-border/60 bg-muted/40 px-2 py-0.5 text-[10px] text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                      >
                        {tx("⚡ Triage Gmail & Phê duyệt", "⚡ Gmail Triage & Approvals")}
                      </button>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">{tx("AI Model", "AI Model")}</Label>
                    <Select className="text-xs w-full" value={aiModelId} onChange={(e) => setAiModelId(e.target.value)}>
                      {models.data?.map((m) => (
                        <option key={m.id} value={m.id}>{m.display_name || m.name}</option>
                      ))}
                    </Select>
                  </div>

                  {generate.isPending && (
                    <div className="space-y-2.5 rounded-xl border border-primary/40 bg-primary/10 p-4 animate-pulse">
                      <div className="flex items-center gap-2.5 text-xs font-semibold text-primary">
                        <Sparkles className="h-4 w-4 animate-spin" />
                        <span>{tx("AI is architecting your multi-agent workflow DAG...", "AI is architecting your multi-agent workflow DAG...")}</span>
                      </div>
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-primary/20">
                        <div className="h-full w-2/3 animate-[shimmer_1.5s_infinite] bg-primary rounded-full" />
                      </div>
                      <p className="text-[11px] text-muted-foreground">
                        {tx("Synthesizing triggers, connectors, triage policies, and agent routing graph...", "Synthesizing triggers, connectors, triage policies, and agent routing graph...")}</p>
                    </div>
                  )}

                  {!generate.isPending && (
                    <Button
                      className="w-full gap-2 active-tactile transition-transform font-semibold"
                      disabled={!aiPrompt.trim() || !aiModelId}
                      onClick={handleGenerate}
                    >
                      <Sparkles className="h-4 w-4 text-primary-foreground" /> {tx("Generate Workflow", "Generate Workflow")}</Button>
                  )}

                  {aiResult && (
                    <div className="space-y-3 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-4 shadow-sm">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="text-sm font-bold text-foreground">{aiResult.name}</div>
                          {aiResult.description && (
                            <p className="mt-0.5 text-xs text-muted-foreground leading-relaxed">{aiResult.description}</p>
                          )}
                        </div>
                        <span className="shrink-0 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-bold text-emerald-600 dark:text-emerald-400">
                          {aiResult.graph.nodes.length} {tx("nodes ·", "nodes ·")}{aiResult.graph.edges.length} {tx("edges", "edges")}</span>
                      </div>

                      {/* Visual node flow chain preview */}
                      <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-border/50 bg-background/60 p-2 text-[10px]">
                        {aiResult.graph.nodes.map((node: any, idx: number) => (
                          <React.Fragment key={node.id}>
                            <span className="rounded border border-border/80 bg-muted/60 px-2 py-0.5 font-medium text-foreground">
                              {node.label || node.kind}
                            </span>
                            {idx < aiResult.graph.nodes.length - 1 && (
                              <span className="text-muted-foreground/60 font-bold">→</span>
                            )}
                          </React.Fragment>
                        ))}
                      </div>

                      <DialogClose asChild>
                        <Button size="sm" className="w-full gap-2 bg-emerald-600 hover:bg-emerald-700 text-white font-medium" onClick={applyGenerated}>
                          {tx("Apply to canvas", "Apply to canvas")}</Button>
                      </DialogClose>
                    </div>
                  )}
                </div>
              </DialogContent>
            </Dialog>
            <Button onClick={save} className="gap-2 active-tactile transition-transform">
              <Save className="h-4 w-4" />{tx("Lưu", "Save")}</Button>
          </>
        }
      />

      <div className="space-y-3">
        {activeRunId && <RunKpiStrip run={workflowRun.data} />}
        <div className="flex items-center gap-2 rounded-xl border border-border/80 bg-card/50 p-3 backdrop-blur-xl shadow-3d-card">
          <div className="flex-1 space-y-1">
            <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">{tx("Tên workflow", "Workflow name")}</Label>
            <Input className="text-xs" value={wfName} onChange={(e) => setWfName(e.target.value)} placeholder={tx("Tên workflow", "Workflow name")} />
          </div>
          <div className="flex-[2] space-y-1">
            <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">{tx("Đầu vào chạy", "Run input")}</Label>
            <Textarea
              className="min-h-[38px] text-xs resize-none"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={tx("Đầu vào JSON hoặc văn bản thuần túy…", "JSON or plain text input…")}
            />
          </div>
          <Button className="gap-2 active-tactile transition-transform self-end text-xs" disabled={running} onClick={run}>
            <Play className="h-3.5 w-3.5" /> {running ? "Running…" : "Run Workflow"}
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
            onEditEdgeCondition={handleEditEdgeCondition}
          />
        </div>
      </div>

      <WorkflowNodeConfig
        node={selectedNode}
        open={Boolean(selectedNode)}
        onOpenChange={(open) => !open && setSelectedNode(null)}
        onUpdate={updateNode}
        onDeleteNode={handleDeleteNode}
      />

      <div className="animate-slide-up" style={{ animationDelay: "150ms" }}>
        <WorkflowConsole
          logs={logs}
          output={output}
          running={running}
          run={workflowRun.data}
          onReplay={activeRunId && !running ? () => runReplay(activeRunId) : undefined}
        />
      </div>
    </div>
  );
}
