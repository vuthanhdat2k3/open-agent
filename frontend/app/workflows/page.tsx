"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Workflow as WorkflowIcon,
  Play,
  Square,
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
  getWorkflowInstallations,
  installWorkflowTemplate,
  deleteWorkflowInstallation,
  publishWorkflowToCatalog,
  unpublishWorkflowFromCatalog,
  type WorkflowCatalogItem,
} from "@/lib/automations/api";
import { workflowIcon } from "@/lib/automations/icons";
import { useCurrentRole, useCurrentRoles, useUrlSearchParam } from "@/hooks";
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
  RotateCcw,
} from "lucide-react";
import { api, streamSSE } from "@/lib/api";
import { useWorkflows, useCreateWorkflow, useUpdateWorkflow, useDeleteWorkflow, useResetWorkflowTemplate, useAgents, useModels, useGenerateWorkflow, useWorkflowRun } from "@/hooks";
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
  DialogFooter,
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
  const deleteWf = useDeleteWorkflow();
  const resetTemplate = useResetWorkflowTemplate();
  const generate = useGenerateWorkflow();
  const agents = useAgents();
  const models = useModels(true);
  const data = workflows.data;
  const {
    activeWorkflowId,
    activeWorkflowName,
    nodes,
    edges,
    selectedNodeId,
    activeRunId,
    activeRunStatus,
    setGraph,
    setActiveWorkflow,
    setSelectedNode,
    setActiveRun,
    reset,
  } = useWorkflowStore();
  const workflowRun = useWorkflowRun(activeRunId);
  const router = useRouter();
  const queryClient = useQueryClient();
  const role = useCurrentRole();
  const roles = useCurrentRoles();
  const isOperator = roles.includes("operator");

  // Tab State: "editor" (My Workflows) vs "marketplace" (Workflow Marketplace) with URL synchronization
  const [tabParam, setTabParam] = useUrlSearchParam("tab");
  const activeTab = (tabParam as "editor" | "marketplace") || "editor";
  const setActiveTab = (tab: "editor" | "marketplace") => {
    setTabParam(tab === "editor" ? null : tab);
  };

  // Marketplace State
  const [marketSearch, setMarketSearch] = React.useState("");
  const [marketCategory, setMarketCategory] = React.useState("");
  const [isInstalling, setIsInstalling] = React.useState<string | null>(null);

  // Operator Publish Dialog State
  const [publishWfId, setPublishWfId] = React.useState("");

  // Fetch user's installations to detect which workflows came from marketplace
  const installationsQuery = useQuery({
    queryKey: ["workflow-installations"],
    queryFn: getWorkflowInstallations,
    enabled: !isOperator,
  });

  // Fetch Marketplace Templates
  const catalogQuery = useQuery({
    queryKey: ["workflow-catalog", marketSearch, marketCategory],
    queryFn: () => getWorkflowCatalog({ query: marketSearch, category: marketCategory }),
  });

  const catalogItems = catalogQuery.data?.data ?? [];

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

  const handleDeleteWorkflow = async (wfId: string, wfName: string, closeDialog?: () => void) => {
    if (!confirm(tx(`Bạn có chắc muốn xóa workflow "${wfName}"? Hành động này không thể hoàn tác.`, `Delete workflow "${wfName}"? This cannot be undone.`))) {
      return;
    }
    try {
      // Check if this workflow is installed from marketplace → also archive the installation
      const installations = installationsQuery.data ?? [];
      const installation = installations.find((i) => i.workflow_id === wfId);
      if (installation) {
        await deleteWorkflowInstallation(installation.id);
        void queryClient.invalidateQueries({ queryKey: ["workflow-catalog"] });
        void queryClient.invalidateQueries({ queryKey: ["workflow-installations"] });
      }
      await deleteWf.mutateAsync(wfId);
      // Clear canvas if the deleted workflow was currently loaded
      if (editId === wfId || activeWorkflowId === wfId) {
        newWorkflow();
      }
      toast.success(tx(`Đã xóa workflow "${wfName}"`, `Deleted workflow "${wfName}"`) );
      closeDialog?.();
    } catch (e: any) {
      toast.error(e.message || tx("Không thể xóa workflow", "Failed to delete workflow"));
    }
  };

  const handleOperatorEditTemplate = async (template: WorkflowCatalogItem) => {
    // 1. Try to find the source workflow by ID in current workflows data
    const shortId = template.key.startsWith("market-") ? template.key.replace("market-", "") : null;
    const existingWf = data?.find((w) =>
      shortId ? w.id.startsWith(shortId) : (w.template_key === template.key || w.name === template.name)
    );
    if (existingWf) {
      loadWorkflow(existingWf);
      setActiveTab("editor");
      toast.success(tx(`Đã mở quy trình "${template.name}" để chỉnh sửa`, `Opened "${template.name}" for editing`));
      return;
    }

    // 2. Fetch directly from workflow service (virtual blueprint or published template)
    setIsInstalling(template.key);
    try {
      const wf = await api.get<any>(`/api/workflows/${template.key}`);
      if (wf && wf.graph) {
        loadWorkflow(wf);
        setActiveTab("editor");
        toast.success(tx(`Đã nạp quy trình "${template.name}" vào Canvas để chỉnh sửa`, `Loaded "${template.name}" into Canvas for editing`));
        return;
      }
    } catch {
      // Fallback: try installing a copy
    }

    // 3. Fallback: try installing a copy into workspace
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
      handleOpenInstalledTemplate(template);
      return;
    }
    setIsInstalling(template.key);
    try {
      const res = await installWorkflowTemplate({
        template_key: template.key,
        name: template.name,
        timezone: "Asia/Ho_Chi_Minh",
        schedule: { kind: "daily", time: "08:00" },
      });
      toast.success(tx(`Đã cài đặt "${template.name}" thành công!`, `Successfully installed "${template.name}"!`));
      void queryClient.invalidateQueries({ queryKey: ["workflow-catalog"] });
      void queryClient.invalidateQueries({ queryKey: ["workflow-installations"] });
      const refetched = await workflows.refetch();
      const newWf = refetched.data?.find((w) => w.id === res.workflow_id || w.name === template.name);
      if (newWf) {
        loadWorkflow(newWf);
      } else if (res.workflow_id) {
        setEditId(res.workflow_id);
        setWfName(res.name || template.name);
      }
      setActiveTab("editor");
    } catch (e: any) {
      toast.error(e.message || tx("Không thể cài đặt quy trình", "Failed to install workflow"));
    } finally {
      setIsInstalling(null);
    }
  };

  const handleOpenInstalledTemplate = (template: WorkflowCatalogItem) => {
    const installations = installationsQuery.data ?? [];
    const inst = installations.find((i) => i.template_key === template.key);
    const targetWf = data?.find((w) => (inst ? w.id === inst.workflow_id : w.name === template.name));
    if (targetWf) {
      loadWorkflow(targetWf);
      setActiveTab("editor");
      toast.success(tx(`Đã mở quy trình "${template.name}"`, `Opened "${template.name}"`));
    } else {
      setActiveTab("editor");
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

  // Load a workflow directly when opened with ?edit=<id> or sync with activeWorkflowId from store
  const didLoadEditRef = React.useRef(false);
  const lastLoadedEditIdRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (typeof window === "undefined" || !data) return;
    const url = new URL(window.location.href);
    const editIdParam = url.searchParams.get("edit");
    if (editIdParam) {
      if (editIdParam === lastLoadedEditIdRef.current) return;
      const wf = data.find((w) => w.id === editIdParam);
      if (wf) {
        didLoadEditRef.current = true;
        loadWorkflow(wf);
      } else {
        didLoadEditRef.current = true;
        newWorkflow();
      }
    } else if (!didLoadEditRef.current) {
      didLoadEditRef.current = true;
      if (activeWorkflowId) {
        if (activeWorkflowId === lastLoadedEditIdRef.current) return;
        const wf = data.find((w) => w.id === activeWorkflowId);
        if (wf) {
          loadWorkflow(wf);
        } else {
          newWorkflow();
        }
      }
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
  // Live SSE stream handling: an AbortController lets run() be cancelled when
  // the user navigates away / starts another run, and sseActiveRef tells the
  // polling effect not to clobber live node status with stale snapshot rows.
  const sseAbortRef = React.useRef<AbortController | null>(null);
  const sseActiveRef = React.useRef(false);
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
    reset();
    setWfName("");
    setEditId(null);
    setInput("");
    setOutput("");
    setLogs([]);
    setNodeStatus({});
    setActiveRun(null);
    setSelectedNode(null);
    lastLoadedEditIdRef.current = null;
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.delete("edit");
      url.searchParams.delete("run");
      window.history.replaceState(null, "", url.toString());
    }
    toast.success(tx("Workflow mới — đã xóa canvas", "New workflow — canvas cleared"));
  };

  const loadWorkflow = (wf: any) => {
    if (!wf) return;
    lastLoadedEditIdRef.current = wf.id;
    setWfName(wf.name);
    setEditId(wf.id);
    setActiveWorkflow(wf.id, wf.name);
    const loadedNodes: GraphNode[] = Array.isArray(wf.graph?.nodes) ? wf.graph.nodes : [];
    const loadedEdges: GraphEdge[] = Array.isArray(wf.graph?.edges) ? wf.graph.edges : [];
    setGraph(loadedNodes, loadedEdges);
    setSelectedNode(null);
    setLogs([]);
    setOutput("");
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("edit", wf.id);
      window.history.replaceState(null, "", url.toString());
    }
    toast.success(tx(`Đã tải workflow: ${wf.name}`, `Loaded workflow: ${wf.name}`));
  };

  const save = async (): Promise<string | null> => {
    const trimmedName = wfName.trim();
    if (!trimmedName) {
      toast.error(tx("Vui lòng nhập tên workflow trước khi lưu", "Please enter a workflow name before saving"));
      return null;
    }
    if (nodes.length === 0) {
      toast.error(tx("Canvas chưa có node nào. Hãy thêm ít nhất 1 node.", "Canvas is empty. Add at least 1 node."));
      return null;
    }
    try {
      if (editId) {
        await update.mutateAsync({
          id: editId,
          data: {
            name: trimmedName,
            graph: { nodes, edges },
          },
        });
        toast.success(tx("Đã lưu workflow", "Workflow saved"));
        return editId;
      } else {
        const created = await create.mutateAsync({
          name: trimmedName,
          description: "",
          graph: { nodes, edges },
        });
        setEditId(created.id);
        toast.success(tx("Đã lưu workflow", "Workflow saved"));
        return created.id;
      }
    } catch (e: any) {
      const msg = e.message || "";
      toast.error(
        msg.includes("already exists")
          ? tx("Tên workflow đã tồn tại. Vui lòng chọn tên khác.", "Workflow name already exists. Please choose another name.")
          : msg || tx("Không thể lưu workflow", "Failed to save workflow"),
      );
      return null;
    }
  };

  React.useEffect(() => {
    if (!aiModelId && models.data?.length) setAiModelId(models.data[0].id);
  }, [models.data, aiModelId]);

  React.useEffect(() => {
    const run = workflowRun.data;
    if (!run) return;
    if (activeRunId !== run.id || activeRunStatus !== run.status) {
      setActiveRun(run.id, run.status);
    }
    // Auto-bind parent workflow when viewing run if not already bound
    if (!editId && (run as any).workflow_id && data?.length) {
      const parentWf = data.find((w) => w.id === (run as any).workflow_id);
      if (parentWf) {
        setWfName(parentWf.name);
        setEditId(parentWf.id);
        const loadedNodes: GraphNode[] = Array.isArray(parentWf.graph?.nodes) ? parentWf.graph.nodes : [];
        const loadedEdges: GraphEdge[] = Array.isArray(parentWf.graph?.edges) ? parentWf.graph.edges : [];
        if (nodes.length === 0) {
          setGraph(loadedNodes, loadedEdges);
        }
      }
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
    // While a live SSE run is streaming, the poll snapshot is already stale —
    // overwriting node status here would reset a node mid-run back to "idle".
    // Merge only the nodes the stream has not marked yet instead.
    setNodeStatus((current) => {
      if (sseActiveRef.current) {
        return { ...statuses, ...current };
      }
      return statuses;
    });
    if (run.output?.text) setOutput(String(run.output.text));
    setRunning(!["succeeded", "failed", "diverged", "cancelled", "waiting_approval"].includes(run.status));
    setLogs((previous) => {
      if (!sseActiveRef.current) {
        return restoredLogs.length > 0 ? restoredLogs : previous;
      }
      return previous.length === 0 ? restoredLogs : previous;
    });
  }, [workflowRun.data, setActiveRun, activeRunId, activeRunStatus, editId, data, nodes.length, setGraph]);

  // Synchronize immediately when an approval is resolved (e.g. via 3D companion or approvals drawer)
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const handleApprovalDecided = () => {
      void workflowRun.refetch();
    };
    window.addEventListener("approval-decided", handleApprovalDecided);
    return () => window.removeEventListener("approval-decided", handleApprovalDecided);
  }, [workflowRun]);

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

  const [edgeConditionTarget, setEdgeConditionTarget] = React.useState<string | null>(null);
  const [edgeConditionDraft, setEdgeConditionDraft] = React.useState("");

  const handleEditEdgeCondition = (edgeId: string) => {
    const [fromId, rest] = edgeId.split("->");
    const toId = rest?.split("#")[0] ?? "";
    const edge = edges.find((e) => e.from_ === fromId && e.to === toId);
    setEdgeConditionDraft(edge?.condition ?? "");
    setEdgeConditionTarget(edgeId);
  };

  const applyEdgeCondition = () => {
    if (!edgeConditionTarget) return;
    const [fromId, rest] = edgeConditionTarget.split("->");
    const toId = rest?.split("#")[0] ?? "";
    const nextEdges = edges.map((e) =>
      e.from_ === fromId && e.to === toId
        ? { ...e, condition: edgeConditionDraft.trim() || undefined }
        : e,
    );
    setGraph(nodes, nextEdges);
    setEdgeConditionTarget(null);
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
    if (nodes.length === 0) {
      toast.error(tx("Canvas chưa có node nào. Hãy thêm node trước khi chạy.", "Canvas has no nodes. Add nodes before running."));
      return;
    }
    let targetId = editId;
    if (!targetId) {
      if (!wfName.trim()) {
        toast.error(tx("Vui lòng đặt tên và Lưu workflow trước khi chạy", "Please enter a workflow name and Save before running"));
        return;
      }
      targetId = await save();
      if (!targetId) return;
    } else {
      await save();
    }
    setRunning(true);
    setOutput("");
    setNodeStatus({});
    fadedNodeIdsRef.current.clear();
    setLogs([]);
    sseAbortRef.current?.abort();
    const abortController = new AbortController();
    sseAbortRef.current = abortController;
    sseActiveRef.current = true;
    try {
      await streamSSE(
        `/api/workflows/${targetId}/run`,
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
                message: tx(`Node "${d.node_id}" đã bắt đầu (${d.kind || "execution"})`, `Node "${d.node_id}" started (${d.kind || "execution"})`),
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
                message: tx(`Node "${d.node_id}" đã hoàn thành${outSnippet}`, `Node "${d.node_id}" completed${outSnippet}`),
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
                message: d.message || tx(`Node "${d.node_id}" đã thất bại`, `Node "${d.node_id}" failed`),
              },
            ]);
          } else if (ev.event === "edge") {
            setLogs((prev) => [
              ...prev,
              {
                id: logId,
                ts,
                event: "edge",
                message: tx(`Edge ${d.from} → ${d.to} được kích hoạt`, `Edge ${d.from} → ${d.to} taken`),
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
                message: tx(`Node "${d.node_id}" đang chờ phê duyệt (approval_id: ${d.approval_id})`, `Node "${d.node_id}" waiting for approval (approval_id: ${d.approval_id})`),
              },
            ]);
          } else if (ev.event === "error") {
            setLogs((prev) => [
              ...prev,
              {
                id: logId,
                ts,
                event: "error",
                message: d.message || tx("Lỗi thực thi workflow", "Workflow execution error"),
              },
            ]);
          } else if (ev.event === "workflow_cancelled") {
            setLogs((prev) => [
              ...prev,
              {
                id: logId,
                ts,
                event: "done",
                message: tx("Workflow đã được hủy", "Workflow cancelled"),
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
                message: tx("Workflow hoàn tất thành công", "Workflow finished successfully"),
                output: typeof d.output === "string" ? d.output : JSON.stringify(d.output, null, 2),
              },
            ]);
          }
        },
        abortController.signal,
      );
    } catch (e: any) {
      toast.error(e.message);
      setLogs((prev) => [
        ...prev,
        {
          id: Math.random().toString(36).slice(2, 9),
          ts: Date.now(),
          event: "error",
          message: e.message || tx("Đã xảy ra lỗi thực thi", "Execution error occurred"),
        },
      ]);
    } finally {
      // The durable run owns the lifecycle; polling will update the UI.
      sseActiveRef.current = false;
      if (sseAbortRef.current === abortController) {
        sseAbortRef.current = null;
      }
    }
  };

  const cancelRun = async () => {
    if (!activeRunId) return;
    // Stop the client-side stream immediately; the backend flips the run to
    // cancelled (cooperatively at the next node boundary) and the poll takes
    // over the UI.
    sseAbortRef.current?.abort();
    try {
      await api.post(`/api/workflows/runs/${activeRunId}/cancel`);
      toast.success(tx("Đã yêu cầu hủy workflow", "Workflow cancel requested"));
    } catch (e: any) {
      toast.error(e.message || tx("Không thể hủy workflow", "Failed to cancel workflow"));
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
              : tx("Kho workflow dùng chung", "Workflow Marketplace")}
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
              {tx("Kho dùng chung", "Marketplace")}
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
                        <div key={wf.id} className="flex items-center gap-1.5 p-1 rounded-lg border border-border/40 hover:bg-accent/40 transition-colors">
                          <DialogClose asChild>
                            <Button
                              variant="ghost"
                              className="flex-1 justify-start text-xs font-medium h-auto py-1.5 px-2"
                              onClick={() => loadWorkflow(wf)}
                            >
                              <div className="flex flex-col items-start gap-0.5 text-left truncate">
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <span className="font-semibold text-foreground">{wf.name}</span>
                                  {wf.template_key ? (
                                    <Badge variant={wf.is_customized ? "outline" : "secondary"} className="text-[10px] px-1.5 py-0">
                                      {wf.is_customized ? tx("Đã tùy chỉnh", "Customized") : tx("Mẫu hệ thống", "System Template")}
                                    </Badge>
                                  ) : null}
                                </div>
                                {wf.description && (
                                  <span className="text-[11px] text-muted-foreground line-clamp-1">{wf.description}</span>
                                )}
                                {isOperator && wf.created_by_user_id && (
                                  <span className="text-[10px] text-muted-foreground/60">
                                    {tx("Tạo bởi", "By")}: {wf.creator_email || wf.creator_name || wf.created_by_user_id.slice(0, 8)}
                                  </span>
                                )}
                              </div>
                            </Button>
                          </DialogClose>
                          {wf.template_key && wf.is_customized && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 px-2 text-xs text-amber-600 dark:text-amber-400 hover:bg-amber-500/10 shrink-0 gap-1"
                              title={tx("Khôi phục về mẫu gốc", "Reset to original system template")}
                              onClick={async () => {
                                if (confirm(tx("Khôi phục workflow này về cấu hình mẫu gốc của hệ thống?", "Reset this workflow back to system template default?"))) {
                                  await resetTemplate.mutateAsync(wf.id);
                                  toast.success(tx("Đã khôi phục về mẫu hệ thống", "Reset to system template"));
                                }
                              }}
                            >
                              <RotateCcw className="h-3 w-3" />
                              <span className="text-[10px] hidden sm:inline">{tx("Khôi phục", "Reset")}</span>
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0 text-destructive hover:bg-destructive/10 shrink-0"
                            title={tx("Xóa workflow này", "Delete this workflow")}
                            onClick={() => handleDeleteWorkflow(wf.id, wf.name)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
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
                      <Label className="font-semibold text-muted-foreground">{tx("Mô hình AI", "AI Model")}</Label>
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
              {editId && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="gap-1.5 text-xs font-medium text-destructive hover:bg-destructive/10"
                  onClick={() => handleDeleteWorkflow(editId, wfName)}
                >
                  <Trash2 className="h-3.5 w-3.5" /> {tx("Xóa", "Delete")}
                </Button>
              )}
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
              <Play className="h-3.5 w-3.5" /> {running ? tx("Đang chạy…", "Running…") : tx("Chạy Workflow", "Run Workflow")}
            </Button>
            {activeRunId && !["succeeded", "failed", "diverged", "cancelled", "waiting_approval"].includes(workflowRun.data?.status ?? "") && (
              <Button variant="outline" className="gap-2 self-end text-xs" onClick={cancelRun}>
                <Square className="h-3.5 w-3.5" /> {tx("Hủy", "Cancel")}
              </Button>
            )}
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
                      {tx("Truy cập Operator", "Operator Access")}
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
                        {/* Unified Actions: Install/Open + Edit in Canvas (Operator) + Remove (Creator/Admin) */}
                        <div className="flex items-center justify-between gap-2 w-full">
                          {template.installed ? (
                            <Button
                              size="sm"
                              variant="outline"
                              className="w-full gap-1.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400 border-emerald-500/40 hover:bg-emerald-500/10 active-tactile flex-1"
                              onClick={() => handleOpenInstalledTemplate(template)}
                            >
                              <CheckCircle className="h-3.5 w-3.5" />
                              {tx("Mở quy trình", "Open Workflow")} <ArrowRight className="h-3.5 w-3.5" />
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              className="w-full gap-1.5 text-xs font-semibold active-tactile flex-1"
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

                          {isOperator && (
                            <Button
                              variant="outline"
                              size="sm"
                              className="gap-1.5 text-xs font-semibold border-primary/30 hover:bg-primary/10 shrink-0"
                              onClick={() => handleOperatorEditTemplate(template)}
                              title={tx("Mở trong Canvas để chỉnh sửa", "Open in Canvas to edit")}
                            >
                              <Edit className="h-3.5 w-3.5 text-primary" /> {tx("Chỉnh sửa", "Edit")}
                            </Button>
                          )}

                          {template.capabilities?.can_delete && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 px-2 text-destructive hover:bg-destructive/10 text-xs font-semibold gap-1 shrink-0"
                              onClick={() => handleUnpublish(template.key)}
                              title={tx("Gỡ bỏ khỏi Marketplace", "Remove from Marketplace")}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}

      <Dialog open={edgeConditionTarget !== null} onOpenChange={(open) => !open && setEdgeConditionTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{tx("Điều kiện cạnh (Edge Condition)", "Edge Condition")}</DialogTitle>
            <DialogDescription>
              {tx(
                "Nhập điều kiện JS (bỏ trống để xóa).\nVí dụ:\n  output.category == 'sales'\n  'urgent' in output.text\n  true",
                "Enter a JS condition (leave empty to clear).\nExamples:\n  output.category == 'sales'\n  'urgent' in output.text\n  true",
              )}
            </DialogDescription>
          </DialogHeader>
          <Textarea
            className="text-xs font-mono min-h-[120px]"
            value={edgeConditionDraft}
            onChange={(e) => setEdgeConditionDraft(e.target.value)}
            placeholder={tx("output.category == 'sales'", "output.category == 'sales'")}
          />
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">{tx("Hủy", "Cancel")}</Button>
            </DialogClose>
            <Button onClick={applyEdgeCondition}>{tx("Áp dụng", "Apply")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
