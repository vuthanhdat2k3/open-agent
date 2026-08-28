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
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getWorkflowCatalog,
  installWorkflowTemplate,
  publishWorkflowToCatalog,
  unpublishWorkflowFromCatalog,
  type WorkflowCatalogItem,
} from "@/lib/automations/api";
import { workflowIcon } from "@/lib/automations/icons";
import { useCurrentRole } from "@/hooks";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/shared";
import {
  Search,
  CheckCircle,
  ShieldCheck,
  Plug,
  ArrowRight,
  Trash2,
  Edit,
  Plus,
} from "lucide-react";
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
  DialogDescription,
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


const marketplaceCategories = [
  { value: "", labelVi: "Tất cả quy trình", labelEn: "All workflows" },
  { value: "daily_planning", labelVi: "Lập kế hoạch hàng ngày", labelEn: "Daily planning" },
  { value: "meetings", labelVi: "Họp & Lịch trình", labelEn: "Meetings" },
  { value: "customer_intelligence", labelVi: "Thông tin khách hàng", labelEn: "Customer intelligence" },
  { value: "research", labelVi: "Nghiên cứu & Báo cáo", labelEn: "Research" },
  { value: "custom", labelVi: "Tùy chỉnh tổ chức", labelEn: "Organization Custom" },
];

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
  const queryClient = useQueryClient();
  const role = useCurrentRole();
  const isOperator = role === "operator";

  // Tab State: "editor" (My Workflows) vs "marketplace" (Workflow Marketplace)
  const [activeTab, setActiveTab] = React.useState<"editor" | "marketplace">("editor");

  // Marketplace State
  const [marketSearch, setMarketSearch] = React.useState("");
  const [marketCategory, setMarketCategory] = React.useState("");
  const [isInstalling, setIsInstalling] = React.useState<string | null>(null);

  // Operator Publish Dialog State
  const [publishWfId, setPublishWfId] = React.useState("");

  // Fetch Marketplace Templates
  const catalogQuery = useQuery({
    queryKey: ["workflow-catalog", marketSearch, marketCategory],
    queryFn: () => getWorkflowCatalog({ query: marketSearch, category: marketCategory }),
  });

  const catalogItems = catalogQuery.data?.data ?? [];

  // Synchronize Tab from URL
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    const tabParam = url.searchParams.get("tab");
    if (tabParam === "marketplace") {
      setActiveTab("marketplace");
    }
  }, []);

  const [publishDialogOpen, setPublishDialogOpen] = React.useState(false);
  const [publishCategory, setPublishCategory] = React.useState("custom");
  const [publishDescription, setPublishDescription] = React.useState("");
  const [isPublishing, setIsPublishing] = React.useState(false);


  const handleUnpublish = async (key: string) => {
    if (!confirm(tx("Bạn có chắc chắn muốn gỡ bỏ quy trình này khỏi Marketplace?", "Are you sure you want to remove this template from Marketplace?"))) {
      return;
    }
    try {
      await unpublishWorkflowFromCatalog(key);
      toast.success(tx("Đã gỡ bỏ template khỏi Marketplace", "Template removed from Marketplace"));
      void queryClient.invalidateQueries({ queryKey: ["workflow-catalog"] });
    } catch (e: any) {
      toast.error(e.message || tx("Không thể gỡ bỏ template", "Failed to unpublish template"));
    }
  };

  const handleOperatorEditTemplate = async (template: WorkflowCatalogItem) => {
    // 1. Try to find the source workflow by ID (template key is "market-{id[:12]}")
    const shortId = template.key.startsWith("market-") ? template.key.replace("market-", "") : null;
    const existingWf = data?.find((w) =>
      shortId ? w.id.startsWith(shortId) : w.name === template.name
    );
    if (existingWf) {
      loadWorkflow(existingWf);
      setActiveTab("editor");
      toast.success(tx(`Đã mở quy trình "${template.name}" để chỉnh sửa`, `Opened "${template.name}" for editing`));
      return;
    }

    // 2. Otherwise, load/install a copy into Operator workspace to tune
    setIsInstalling(template.key);
    try {
      const res = await installWorkflowTemplate({
        template_key: template.key,
        name: template.name,
        timezone: "Asia/Ho_Chi_Minh",
        schedule: { kind: "daily", time: "08:00" },
      });
      toast.success(tx(`Đã nạp quy trình "${template.name}" vào Canvas để chỉnh sửa`, `Loaded "${template.name}" into Canvas for editing`));
      await workflows.refetch();
      if (res.workflow_id) {
        router.push(`/workflows?edit=${res.workflow_id}`);
      }
      setActiveTab("editor");
    } catch (e: any) {
      // If already installed, find by name fallback and open it
      if (e.message?.includes("already installed") || e.message?.includes("already in use")) {
        const fallbackWf = data?.find((w) => w.name === template.name);
        if (fallbackWf) {
          loadWorkflow(fallbackWf);
          setActiveTab("editor");
          toast.success(tx(`Đã mở quy trình "${template.name}" để chỉnh sửa`, `Opened "${template.name}" for editing`));
          return;
        }
      }
      toast.error(e.message || tx("Không thể tải quy trình để chỉnh sửa", "Failed to load workflow for editing"));
    } finally {
      setIsInstalling(null);
    }
  };

  const handleInstallTemplate = async (template: WorkflowCatalogItem) => {
    if (template.installed) {
      toast.info(tx(`"${template.name}" đã được cài đặt rồi`, `"${template.name}" is already installed`));
      return;
    }
    setIsInstalling(template.key);
    try {
      await installWorkflowTemplate({
        template_key: template.key,
        name: template.name,
        timezone: "Asia/Ho_Chi_Minh",
        schedule: { kind: "daily", time: "08:00" },
      });
      toast.success(tx(`Đã cài đặt "${template.name}" thành công! Vào tab Quy trình của tôi để xem.`, `Successfully installed "${template.name}"! Check My Workflows tab.`));
      // Invalidate catalog so template.installed updates to true immediately
      void queryClient.invalidateQueries({ queryKey: ["workflow-catalog"] });
      void workflows.refetch();
    } catch (e: any) {
      toast.error(e.message || tx("Không thể cài đặt quy trình", "Failed to install workflow"));
    } finally {
      setIsInstalling(null);
    }
  };

  const handlePublishToMarketplace = async () => {
    const targetWfId = publishWfId || editId;
    if (!targetWfId) {
      toast.error(tx("Vui lòng chọn workflow trước khi đẩy lên Marketplace", "Please select a workflow before publishing to Marketplace"));
      return;
    }
    setIsPublishing(true);
    try {
      await publishWorkflowToCatalog({
        workflow_id: targetWfId,
        category: publishCategory,
        description: publishDescription || undefined,
        outcome: publishDescription || undefined,
        icon: "zap",
      });
      toast.success(tx("Đã đẩy quy trình lên Marketplace thành công!", "Successfully published workflow to Marketplace!"));
      setPublishDialogOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["workflow-catalog"] });
      await catalogQuery.refetch();
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
      {/* Top Header & Tab Navigation */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2.5">
            <WorkflowIcon className="h-7 w-7 text-primary" />
            {activeTab === "editor"
              ? tx("Quy trình của tôi", "My Workflows")
              : tx("Workflow Marketplace", "Workflow Marketplace")}
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            {activeTab === "editor"
              ? tx(
                  "Thiết kế, tùy biến và kiểm thử các quy trình DAG tự động hóa của riêng bạn",
                  "Design, customize, and execute your personal DAG automation workflows"
                )
              : tx(
                  "Duyệt các mẫu quy trình chuẩn của tổ chức và cài đặt thành bản sao cá nhân",
                  "Browse organization-approved workflow templates and install independent copies"
                )}
          </p>
        </div>

        {/* Tab Switcher Segmented Control */}
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-xl border border-border/80 bg-muted/50 p-1 backdrop-blur-md">
            <button
              type="button"
              onClick={() => setActiveTab("editor")}
              className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${
                activeTab === "editor"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <WorkflowIcon className="h-4 w-4 text-primary" />
              {tx("Quy trình của tôi", "My Workflows")}
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("marketplace")}
              className={`flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all ${
                activeTab === "marketplace"
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <LibraryBig className="h-4 w-4 text-primary" />
              {tx("Marketplace", "Marketplace")}
            </button>
          </div>
        </div>
      </div>

      {/* ================= TAB 1: WORKFLOW CANVAS EDITOR ================= */}
      {activeTab === "editor" && (
        <div className="space-y-4">
          {/* Action Buttons Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-2.5 rounded-xl border border-border/80 bg-card/60 p-2.5 backdrop-blur-xl shadow-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" size="sm" className="gap-1.5 active-tactile text-xs font-medium" onClick={newWorkflow}>
                <FilePlus className="h-4 w-4" /> {dict.pages.workflows.btnNew}
              </Button>
              <Dialog>
                <DialogTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-1.5 active-tactile text-xs font-medium">
                    <FolderOpen className="h-4 w-4" /> {dict.pages.workflows.btnLoad}
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>{tx("Tải Workflow đã lưu", "Load Saved Workflow")}</DialogTitle>
                  </DialogHeader>
                  <div className="space-y-2 max-h-[60vh] overflow-y-auto">
                    {workflows.isLoading ? (
                      <LoadingSkeleton variant="table" />
                    ) : workflows.isError ? (
                      <ErrorState
                        title={tx("Không thể tải workflow", "Unable to load workflows")}
                        description={tx("Danh sách workflow chưa sẵn sàng.", "Saved workflows could not be loaded.")}
                        onRetry={() => void workflows.refetch()}
                      />
                    ) : !data || data.length === 0 ? (
                      <EmptyState
                        title={tx("Chưa có quy trình nào", "No workflows found")}
                        description={tx("Bạn có thể tạo quy trình mới hoặc lên Marketplace cài đặt về.", "Create a new workflow or install one from Marketplace.")}
                        action={
                          <Button size="sm" onClick={() => setActiveTab("marketplace")}>
                            {tx("Khám phá Marketplace", "Browse Marketplace")}
                          </Button>
                        }
                      />
                    ) : (
                      data.map((wf) => (
                        <DialogClose asChild key={wf.id}>
                          <Button
                            variant="outline"
                            className="w-full justify-start text-xs font-medium"
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
              <Button variant="outline" size="sm" className="gap-1.5 active-tactile text-xs font-medium" onClick={handleAutoLayout}>
                <RefreshCw className="h-3.5 w-3.5" /> {dict.pages.workflows.btnAutoLayout}
              </Button>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {/* Operator Publish Button */}
              {isOperator && (
                <Dialog open={publishDialogOpen} onOpenChange={setPublishDialogOpen}>
                  <DialogTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1.5 text-xs font-semibold border-emerald-500/40 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/10"
                      onClick={() => setPublishWfId(editId || "")}
                    >
                      <UploadCloud className="h-4 w-4" /> {tx("Đẩy lên Market", "Publish to Market")}
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="sm:max-w-[480px]">
                    <DialogHeader>
                      <DialogTitle className="flex items-center gap-2">
                        <UploadCloud className="h-5 w-5 text-emerald-600" />
                        {tx("Xuất bản lên Marketplace (Operator)", "Publish to Marketplace (Operator)")}
                      </DialogTitle>
                      <DialogDescription className="text-xs">
                        {tx(
                          "Chia sẻ quy trình này thành mẫu chuẩn của tổ chức để toàn bộ thành viên có thể cài đặt và sử dụng độc lập.",
                          "Publish this workflow as an organization-approved template for all members to install."
                        )}
                      </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3.5 py-2 text-xs">
                      <div className="space-y-1.5">
                        <Label>{tx("Chọn Workflow", "Select Workflow")}</Label>
                        <Select className="w-full text-xs" value={publishWfId} onChange={(e) => setPublishWfId(e.target.value)}>
                          <option value="">{tx("-- Chọn workflow cần đẩy --", "-- Select workflow --")}</option>
                          {data?.map((w) => (
                            <option key={w.id} value={w.id}>{w.name}</option>
                          ))}
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label>{tx("Danh mục (Category)", "Category")}</Label>
                        <Select className="w-full text-xs" value={publishCategory} onChange={(e) => setPublishCategory(e.target.value)}>
                          {marketplaceCategories.filter((c) => c.value).map((c) => (
                            <option key={c.value} value={c.value}>{locale === "vi" ? c.labelVi : c.labelEn}</option>
                          ))}
                        </Select>
                      </div>
                      <div className="space-y-1.5">
                        <Label>{tx("Mô tả tóm tắt", "Summary Description")}</Label>
                        <Textarea
                          className="text-xs min-h-[80px]"
                          placeholder={tx("Mô tả mục tiêu và kết quả của quy trình mẫu này...", "Describe the goals and outcome of this template...")}
                          value={publishDescription}
                          onChange={(e) => setPublishDescription(e.target.value)}
                        />
                      </div>
                    </div>
                    <div className="flex justify-end gap-2 pt-2">
                      <Button variant="outline" size="sm" onClick={() => setPublishDialogOpen(false)}>
                        {tx("Hủy", "Cancel")}
                      </Button>
                      <Button
                        size="sm"
                        className="bg-emerald-600 hover:bg-emerald-700 text-white font-medium gap-1.5"
                        disabled={isPublishing || !publishWfId}
                        onClick={handlePublishToMarketplace}
                      >
                        {isPublishing ? tx("Đang xuất bản...", "Publishing...") : tx("Xác nhận Đẩy lên Market", "Publish Now")}
                      </Button>
                    </div>
                  </DialogContent>
                </Dialog>
              )}

              {/* AI Generator */}
              <Dialog>
                <DialogTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-1.5 text-xs font-semibold border-primary/40 bg-primary/5 hover:bg-primary/10">
                    <Sparkles className="h-4 w-4 text-primary animate-pulse" /> {dict.pages.workflows.btnAiGenerate}
                  </Button>
                </DialogTrigger>
                <DialogContent className="sm:max-w-[540px]">
                  <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                      <Sparkles className="h-5 w-5 text-primary" />
                      {tx("AI Thiết kế Workflow Tự động", "Generate Workflow with AI")}
                    </DialogTitle>
                  </DialogHeader>
                  <div className="space-y-4 pt-2 text-xs">
                    <div className="space-y-1.5">
                      <Label className="font-semibold text-muted-foreground">{tx("Mô tả quy trình mong muốn", "Describe what the workflow should do")}</Label>
                      <Textarea
                        className="min-h-[100px] text-xs leading-relaxed"
                        value={aiPrompt}
                        onChange={(e) => setAiPrompt(e.target.value)}
                        placeholder={dict.pages.workflows.aiPromptPlaceholder}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="font-semibold text-muted-foreground">{tx("AI Model", "AI Model")}</Label>
                      <Select className="text-xs w-full" value={aiModelId} onChange={(e) => setAiModelId(e.target.value)}>
                        {models.data?.map((m) => (
                          <option key={m.id} value={m.id}>{m.display_name || m.name}</option>
                        ))}
                      </Select>
                    </div>
                    {generate.isPending ? (
                      <div className="p-4 rounded-xl border border-primary/30 bg-primary/10 text-center animate-pulse text-xs text-primary font-semibold">
                        {tx("AI đang phân tích và thiết kế đồ thị DAG...", "AI is generating workflow DAG...")}
                      </div>
                    ) : (
                      <Button className="w-full gap-2 font-semibold" disabled={!aiPrompt.trim() || !aiModelId} onClick={handleGenerate}>
                        <Sparkles className="h-4 w-4" /> {tx("Sinh quy trình", "Generate Workflow")}
                      </Button>
                    )}
                    {aiResult && (
                      <div className="p-3.5 rounded-xl border border-emerald-500/30 bg-emerald-500/5 space-y-2">
                        <div className="font-bold text-foreground">{aiResult.name}</div>
                        <p className="text-xs text-muted-foreground">{aiResult.description}</p>
                        <DialogClose asChild>
                          <Button size="sm" className="w-full bg-emerald-600 hover:bg-emerald-700 text-white" onClick={applyGenerated}>
                            {tx("Áp dụng vào Canvas", "Apply to canvas")}
                          </Button>
                        </DialogClose>
                      </div>
                    )}
                  </div>
                </DialogContent>
              </Dialog>

              <Button size="sm" onClick={save} className="gap-1.5 active-tactile font-semibold">
                <Save className="h-4 w-4" /> {tx("Lưu", "Save")}
              </Button>
            </div>
          </div>

          {/* Workflow Name Bar */}
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

          {activeRunId && <RunKpiStrip run={workflowRun.data} />}

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
      )}

      {/* ================= TAB 2: WORKFLOW MARKETPLACE ================= */}
      {activeTab === "marketplace" && (
        <div className="space-y-6">
          {/* Operator Management Banner */}
          {isOperator && (
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 backdrop-blur-md shadow-sm">
              <div className="flex items-center gap-3">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                  <ShieldCheck className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
                    {tx("Khu vực Quản trị Marketplace (Operator)", "Marketplace Management Console (Operator)")}
                    <Badge variant="outline" className="text-[10px] border-emerald-500/40 text-emerald-600 dark:text-emerald-400">
                      Operator Access
                    </Badge>
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    {tx(
                      "Bạn có toàn quyền xuất bản các quy trình chuẩn của tổ chức hoặc gỡ bỏ các mẫu lỗi thời khỏi Marketplace.",
                      "You have permissions to publish organization workflows or unpublish obsolete templates from Marketplace."
                    )}
                  </p>
                </div>
              </div>

              <Dialog open={publishDialogOpen} onOpenChange={setPublishDialogOpen}>
                <DialogTrigger asChild>
                  <Button className="gap-2 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs shrink-0">
                    <Plus className="h-4 w-4" /> {tx("Xuất bản quy trình lên Market", "Publish Workflow to Market")}
                  </Button>
                </DialogTrigger>
                <DialogContent className="sm:max-w-[480px]">
                  <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                      <UploadCloud className="h-5 w-5 text-emerald-600" />
                      {tx("Xuất bản Workflow lên Marketplace", "Publish Workflow to Marketplace")}
                    </DialogTitle>
                  </DialogHeader>
                  <div className="space-y-3.5 py-2 text-xs">
                    <div className="space-y-1.5">
                      <Label>{tx("Chọn Workflow của bạn", "Select Your Workflow")}</Label>
                      <Select className="w-full text-xs" value={publishWfId} onChange={(e) => setPublishWfId(e.target.value)}>
                        <option value="">{tx("-- Chọn workflow cần xuất bản --", "-- Select workflow --")}</option>
                        {data?.map((w) => (
                          <option key={w.id} value={w.id}>{w.name}</option>
                        ))}
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label>{tx("Danh mục (Category)", "Category")}</Label>
                      <Select className="w-full text-xs" value={publishCategory} onChange={(e) => setPublishCategory(e.target.value)}>
                        {marketplaceCategories.filter((c) => c.value).map((c) => (
                          <option key={c.value} value={c.value}>{locale === "vi" ? c.labelVi : c.labelEn}</option>
                        ))}
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label>{tx("Mô tả tóm tắt", "Summary Description")}</Label>
                      <Textarea
                        className="text-xs min-h-[80px]"
                        placeholder={tx("Mô tả mục tiêu và kết quả của quy trình mẫu này...", "Describe the goals and outcome of this template...")}
                        value={publishDescription}
                        onChange={(e) => setPublishDescription(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="flex justify-end gap-2 pt-2">
                    <Button variant="outline" size="sm" onClick={() => setPublishDialogOpen(false)}>
                      {tx("Hủy", "Cancel")}
                    </Button>
                    <Button
                      size="sm"
                      className="bg-emerald-600 hover:bg-emerald-700 text-white font-medium gap-1.5"
                      disabled={isPublishing || !publishWfId}
                      onClick={handlePublishToMarketplace}
                    >
                      {isPublishing ? tx("Đang xuất bản...", "Publishing...") : tx("Xác nhận Đẩy lên Market", "Publish Now")}
                    </Button>
                  </div>
                </DialogContent>
              </Dialog>
            </div>
          )}

          {/* Search & Category Filter Bar */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="relative w-full sm:w-80">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="pl-9 text-xs h-9"
                placeholder={tx("Tìm kiếm quy trình trong Marketplace...", "Search templates in Marketplace...")}
                value={marketSearch}
                onChange={(e) => setMarketSearch(e.target.value)}
              />
            </div>
            <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0">
              {marketplaceCategories.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => setMarketCategory(c.value)}
                  className={`rounded-full px-3 py-1 text-xs font-medium whitespace-nowrap transition-all ${
                    marketCategory === c.value
                      ? "bg-primary text-primary-foreground shadow-sm"
                      : "border border-border/80 bg-card/60 text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {locale === "vi" ? c.labelVi : c.labelEn}
                </button>
              ))}
            </div>
          </div>

          {/* Marketplace Grid Cards */}
          {catalogQuery.isLoading ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="h-56 rounded-2xl border border-border/80 bg-card/40 animate-pulse" />
              ))}
            </div>
          ) : catalogItems.length === 0 ? (
            <EmptyState
              title={tx("Không tìm thấy quy trình nào", "No templates found")}
              description={tx("Hãy thử thay đổi từ khóa tìm kiếm hoặc chọn danh mục khác.", "Try changing search terms or filtering by another category.")}
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {catalogItems.map((template) => {
                const Icon = workflowIcon(template.icon);

                return (
                  <Card
                    key={template.key}
                    className="flex flex-col border-border/80 bg-card/70 hover:border-primary/40 hover:shadow-3d-card transition-all duration-200"
                  >
                    <CardHeader className="space-y-2.5 pb-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/15 text-primary border border-primary/25">
                          <Icon className="h-5 w-5" />
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Badge variant="outline" className="text-[10px] uppercase font-semibold">
                            {template.category.replace("_", " ")}
                          </Badge>
                          {template.recommendation?.recommended && (
                            <Badge variant="info" className="text-[10px]">
                              <Sparkles className="h-3 w-3 mr-1" />
                              {tx("Khuyên dùng", "Recommended")}
                            </Badge>
                          )}
                        </div>
                      </div>
                      <div>
                        <CardTitle className="text-sm font-bold text-foreground line-clamp-1">
                          {template.name}
                        </CardTitle>
                        <CardDescription className="text-xs text-muted-foreground line-clamp-2 mt-1">
                          {template.description}
                        </CardDescription>
                      </div>
                    </CardHeader>

                    <CardContent className="flex flex-1 flex-col justify-between gap-4 pt-0">
                      <div className="space-y-2 border-t border-border/50 pt-2.5 text-[11px] text-muted-foreground">
                        <p className="line-clamp-2 text-foreground/80 font-medium">
                          🎯 {template.outcome}
                        </p>
                        <div className="flex flex-wrap items-center gap-1.5 pt-1">
                          {template.required_integrations.map((integration) => (
                            <Badge key={integration} variant="secondary" className="text-[10px]">
                              <Plug className="h-3 w-3 mr-1" /> {integration}
                            </Badge>
                          ))}
                        </div>
                      </div>

                      <div className="flex items-center justify-between gap-2 pt-2 border-t border-border/40">
                        {/* Operator Actions: Edit & Remove */}
                        {isOperator ? (
                          <div className="flex items-center justify-between gap-2 w-full">
                            <Button
                              variant="outline"
                              size="sm"
                              className="gap-1.5 text-xs font-semibold flex-1 border-primary/30 hover:bg-primary/10"
                              onClick={() => handleOperatorEditTemplate(template)}
                            >
                              <Edit className="h-3.5 w-3.5 text-primary" /> {tx("Chỉnh sửa", "Edit")}
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 px-2.5 text-destructive hover:bg-destructive/10 text-xs font-semibold gap-1"
                              onClick={() => handleUnpublish(template.key)}
                              title={tx("Gỡ bỏ khỏi Marketplace", "Remove from Marketplace")}
                            >
                              <Trash2 className="h-3.5 w-3.5" /> {tx("Gỡ bỏ", "Remove")}
                            </Button>
                          </div>
                        ) : (
                          /* User Action: Install to Personal Workflows */
                          <div className="flex items-center justify-end gap-2 ml-auto w-full">
                            {template.installed ? (
                              <Button
                                size="sm"
                                variant="outline"
                                className="w-full gap-1.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400 border-emerald-500/40 cursor-default"
                                disabled
                              >
                                <CheckCircle className="h-3.5 w-3.5" />
                                {tx("Đã cài đặt", "Installed")}
                              </Button>
                            ) : (
                              <Button
                                size="sm"
                                className="w-full gap-1.5 text-xs font-semibold active-tactile"
                                disabled={isInstalling === template.key}
                                onClick={() => handleInstallTemplate(template)}
                              >
                                {isInstalling === template.key ? (
                                  tx("Đang cài đặt...", "Installing...")
                                ) : (
                                  <>
                                    {tx("Cài đặt", "Install")} <ArrowRight className="h-3.5 w-3.5" />
                                  </>
                                )}
                              </Button>
                            )}
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
