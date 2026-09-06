"use client";

import * as React from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import {
  X,
  Maximize2,
  Minimize2,
  Copy,
  Check,
  Download,
  Play,
  RotateCw,
  ExternalLink,
  Code2,
  Eye,
  FileCode,
  Terminal,
  Loader2,
  AlertCircle,
  Network,
  Workflow as WorkflowIcon,
  ArrowUpRight,
  CheckCircle2,
  XCircle,
  Clock,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { useCanvasStore } from "@/stores";
import { api, streamSSE } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { inferLanguage } from "@/lib/chat/canvas-utils";
import { WorkflowCanvas } from "@/components/workflows/workflow-canvas";
import { calculateDagLayout } from "@/lib/workflows/dag-layout";
import { useWorkflowRun } from "@/hooks";
import type { GraphEdge, GraphNode } from "@/types";

interface ChatCanvasPanelProps {
  isDragging?: boolean;
}

export function ChatCanvasPanel({ isDragging }: ChatCanvasPanelProps = {}) {
  const { tx } = useTranslation();
  const { activeItem, isFullscreen, closeCanvas, toggleFullscreen, panelWidthPercentage } =
    useCanvasStore();

  const isWorkflow =
    activeItem?.type === "workflow" ||
    Boolean(activeItem?.workflowGraph) ||
    Boolean(activeItem?.workflowId);

  const [activeTab, setActiveTab] = React.useState<"code" | "preview" | "workflow" | "logs">(
    isWorkflow ? "workflow" : "code",
  );
  const [copied, setCopied] = React.useState(false);

  // Content fetching state
  const [content, setContent] = React.useState<string>(activeItem?.code || "");
  const [isLoadingContent, setIsLoadingContent] = React.useState(false);
  const [contentError, setContentError] = React.useState<string | null>(null);

  // Workflow DAG states
  const [wfNodes, setWfNodes] = React.useState<GraphNode[]>(activeItem?.workflowGraph?.nodes || []);
  const [wfEdges, setWfEdges] = React.useState<GraphEdge[]>(activeItem?.workflowGraph?.edges || []);
  const [selectedNodeId, setSelectedNodeId] = React.useState<string | null>(null);

  // Live Workflow Run status query if workflowRunId is provided
  const runId = activeItem?.workflowRunId || null;
  const workflowRunQuery = useWorkflowRun(runId);

  // Derive node status from workflow run details
  const workflowNodeStatus = React.useMemo(() => {
    const statusMap: Record<string, string> = {};
    const runData = workflowRunQuery.data;
    if (!runData?.nodes) return statusMap;

    runData.nodes.forEach((nr) => {
      if (nr.status === "succeeded") statusMap[nr.node_id] = "done";
      else if (nr.status === "running") statusMap[nr.node_id] = "running";
      else if (nr.status === "failed") statusMap[nr.node_id] = "error";
      else if (nr.status === "waiting_approval") statusMap[nr.node_id] = "waiting_approval";
      else statusMap[nr.node_id] = nr.status;
    });

    return statusMap;
  }, [workflowRunQuery.data]);

  // HTML preview reload key
  const [iframeKey, setIframeKey] = React.useState(0);

  // Sandbox run state
  const [isRunning, setIsRunning] = React.useState(false);
  const [logs, setLogs] = React.useState<string[]>([]);
  const [exitCode, setExitCode] = React.useState<number | null>(null);
  const [runError, setRunError] = React.useState<string | null>(null);
  const logEndRef = React.useRef<HTMLDivElement>(null);

  const lang = (
    activeItem?.language || (activeItem?.title ? inferLanguage(activeItem.title) : "")
  ).toLowerCase();
  const isHtml = lang === "html" || lang === "htm" || activeItem?.title?.toLowerCase().endsWith(".svg");
  const isRunnable =
    lang === "python" || lang === "bash" || lang === "sh" || lang === "javascript" || lang === "node";
  const hasPreview = isHtml || isRunnable;

  // Initialize or fetch content whenever activeItem changes
  React.useEffect(() => {
    if (!activeItem) return;

    if (isWorkflow) {
      setActiveTab(activeItem.initialTab === "code" ? "code" : activeItem.initialTab === "console" ? "logs" : "workflow");
    } else if (activeItem.initialTab) {
      setActiveTab(activeItem.initialTab === "preview" ? "preview" : "code");
    } else if (isHtml) {
      setActiveTab("preview");
    } else {
      setActiveTab("code");
    }

    setLogs([]);
    setExitCode(null);
    setRunError(null);

    // 1. Handle Workflow item initialization
    if (isWorkflow) {
      if (activeItem.workflowGraph) {
        const rawNodes = activeItem.workflowGraph.nodes || [];
        const rawEdges = activeItem.workflowGraph.edges || [];
        const unplaced = rawNodes.filter((n) => n.position?.x == null);
        const layoutPos = unplaced.length > 0 ? calculateDagLayout(rawNodes, rawEdges) : {};
        const positionedNodes = rawNodes.map((n) =>
          n.position?.x != null ? n : { ...n, position: layoutPos[n.id] || { x: 40, y: 40 } },
        );

        setWfNodes(positionedNodes);
        setWfEdges(rawEdges);
        setContent(
          JSON.stringify(
            {
              name: activeItem.workflowName || activeItem.title,
              description: activeItem.workflowDescription || "",
              graph: { nodes: positionedNodes, edges: rawEdges },
            },
            null,
            2,
          ),
        );
        setIsLoadingContent(false);
        setContentError(null);
        return;
      }

      if (activeItem.workflowId) {
        setIsLoadingContent(true);
        setContentError(null);
        api
          .get<any>(`/api/workflows/${activeItem.workflowId}`)
          .then((wf) => {
            const rawNodes: GraphNode[] = Array.isArray(wf.graph?.nodes) ? wf.graph.nodes : [];
            const rawEdges: GraphEdge[] = Array.isArray(wf.graph?.edges) ? wf.graph.edges : [];
            const unplaced = rawNodes.filter((n) => n.position?.x == null);
            const layoutPos = unplaced.length > 0 ? calculateDagLayout(rawNodes, rawEdges) : {};
            const positionedNodes = rawNodes.map((n) =>
              n.position?.x != null ? n : { ...n, position: layoutPos[n.id] || { x: 40, y: 40 } },
            );

            setWfNodes(positionedNodes);
            setWfEdges(rawEdges);
            setContent(JSON.stringify(wf, null, 2));
            setIsLoadingContent(false);
          })
          .catch((err) => {
            setContentError(err instanceof Error ? err.message : "Error loading workflow");
            setIsLoadingContent(false);
          });
        return;
      }
    }

    // 2. Handle Code & File items
    if (activeItem.code !== undefined) {
      setContent(activeItem.code);
      setIsLoadingContent(false);
      setContentError(null);
      return;
    }

    if (activeItem.contentUrl) {
      setIsLoadingContent(true);
      setContentError(null);
      fetch(activeItem.contentUrl)
        .then(async (res) => {
          if (!res.ok) {
            throw new Error(`Failed to load content (${res.status})`);
          }
          return res.text();
        })
        .then((text) => {
          setContent(text);
          setIsLoadingContent(false);
        })
        .catch((err) => {
          setContentError(err instanceof Error ? err.message : "Error loading content");
          setIsLoadingContent(false);
        });
    }
  }, [
    activeItem,
    activeItem?.code,
    activeItem?.contentUrl,
    activeItem?.workflowId,
    activeItem?.workflowGraph,
    isWorkflow,
    isHtml,
  ]);

  // Auto scroll terminal logs
  React.useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, exitCode, runError]);

  if (!activeItem) return null;

  const handleCopy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(content);
      } else {
        const ta = document.createElement("textarea");
        ta.value = content;
        ta.style.position = "fixed";
        ta.style.left = "-9999px";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore
    }
  };

  const handleDownload = () => {
    if (activeItem.downloadUrl) {
      const a = document.createElement("a");
      a.href = activeItem.downloadUrl;
      a.download = activeItem.title;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      return;
    }

    const isSvg = activeItem.title.toLowerCase().endsWith(".svg");
    const mime = isWorkflow
      ? "application/json;charset=utf-8"
      : isSvg
      ? "image/svg+xml"
      : "text/plain;charset=utf-8";
    const filename = isWorkflow
      ? `${(activeItem.workflowName || activeItem.title).replace(/\s+/g, "_")}.json`
      : activeItem.title;
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleOpenNewTab = () => {
    const isSvg = activeItem.title.toLowerCase().endsWith(".svg");
    const mime = isSvg ? "image/svg+xml" : "text/html;charset=utf-8";
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  };

  const handleRunCode = async () => {
    if (isRunning || !content) return;
    setIsRunning(true);
    setLogs([]);
    setExitCode(null);
    setRunError(null);
    setActiveTab("preview");

    const targetLang = lang === "sh" ? "bash" : lang === "javascript" ? "node" : lang;

    try {
      await streamSSE(
        "/api/sandbox/run",
        { language: targetLang, code: content },
        (ev) => {
          if (ev.event === "stdout") {
            const line = ev.data?.line ?? "";
            setLogs((prev) => [...prev, line]);
          } else if (ev.event === "exit") {
            const code = ev.data?.code ?? 0;
            setExitCode(code);
          } else if (ev.event === "error") {
            setRunError(ev.data?.message || tx("Lỗi thực thi", "Execution error"));
          }
        },
      );
    } catch (e: any) {
      setRunError(e.message || tx("Lỗi thực thi", "Execution error"));
    } finally {
      setIsRunning(false);
    }
  };

  const lines = content.split("\n");
  const targetWorkflowId = activeItem.workflowId;
  const targetRunId = activeItem.workflowRunId;

  const panelContent = (
    <div
      style={!isFullscreen ? { width: `${panelWidthPercentage}%` } : undefined}
      className={cn(
        "flex flex-col bg-background",
        isFullscreen
          ? "fixed inset-0 z-[100] w-screen h-screen shadow-2xl"
          : "fixed inset-0 z-40 w-full h-full border-l-0 lg:relative lg:inset-auto lg:z-20 lg:border-l lg:border-border/80 min-h-0 shrink-0",
        !isDragging && !isFullscreen && "transition-all duration-100",
      )}
    >
      {/* 1. Header Toolbar */}
      <div className="flex h-13 shrink-0 items-center justify-between border-b border-border/70 bg-card/60 px-4 backdrop-blur-xs">
        {/* Title & Icon info */}
        <div className="flex items-center gap-2 min-w-0 pr-2">
          <div
            className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
              isWorkflow
                ? "bg-indigo-500/10 text-indigo-500 dark:text-indigo-400 border border-indigo-500/20"
                : "bg-primary/10 text-primary",
            )}
          >
            {isWorkflow ? (
              <Network className="h-4 w-4" aria-hidden="true" />
            ) : (
              <FileCode className="h-4 w-4" aria-hidden="true" />
            )}
          </div>
          <div className="min-w-0 flex flex-col">
            <span
              className="truncate text-xs font-semibold text-foreground font-mono max-w-[120px] sm:max-w-[180px] lg:max-w-[200px]"
              title={activeItem.workflowName || activeItem.title}
            >
              {activeItem.workflowName || activeItem.title}
            </span>
            <div className="flex items-center gap-1.5 pt-0.5">
              {isWorkflow ? (
                <span className="text-[10px] uppercase tracking-wider text-indigo-600 dark:text-indigo-400 font-mono font-medium">
                  DAG Workflow ({wfNodes.length} nodes)
                </span>
              ) : lang ? (
                <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-mono">
                  {lang}
                </span>
              ) : null}
              {targetRunId && (
                <Badge variant="outline" className="text-[9px] px-1 py-0 h-3.5 font-mono">
                  #{targetRunId.slice(0, 8)}
                </Badge>
              )}
            </div>
          </div>
        </div>

        {/* Tab & Action Controls */}
        <div className="flex items-center gap-1.5 shrink-0">
          {/* Tabs switch */}
          {isWorkflow ? (
            <div className="flex items-center rounded-lg border border-border/70 bg-muted/60 p-0.5 mr-1">
              <button
                type="button"
                onClick={() => setActiveTab("workflow")}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                  activeTab === "workflow"
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Network className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{tx("Sơ đồ (DAG)", "DAG Graph")}</span>
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("code")}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                  activeTab === "code"
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Code2 className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{tx("JSON", "JSON")}</span>
              </button>
              {targetRunId && (
                <button
                  type="button"
                  onClick={() => setActiveTab("logs")}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                    activeTab === "logs"
                      ? "bg-background text-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  <Terminal className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{tx("Nhật ký", "Logs")}</span>
                </button>
              )}
            </div>
          ) : hasPreview ? (
            <div className="flex items-center rounded-lg border border-border/70 bg-muted/60 p-0.5 mr-1">
              <button
                type="button"
                onClick={() => setActiveTab("code")}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                  activeTab === "code"
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Code2 className="h-3.5 w-3.5" aria-hidden="true" />
                <span>{tx("Mã nguồn", "Code")}</span>
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("preview")}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all",
                  activeTab === "preview"
                    ? "bg-background text-foreground shadow-xs"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {isHtml ? (
                  <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                ) : (
                  <Terminal className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                <span>{isHtml ? tx("Xem trước", "Preview") : tx("Chạy thử", "Run")}</span>
              </button>
            </div>
          ) : null}

          {/* Workflow Canvas Link */}
          {isWorkflow && (targetWorkflowId || targetRunId) && (
            <Link
              href={`/workflows?${targetWorkflowId ? `edit=${targetWorkflowId}` : ""}${
                targetRunId ? `&run=${targetRunId}` : ""
              }`}
            >
              <Button
                size="sm"
                variant="outline"
                className="h-8 gap-1.5 px-2 text-xs font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 border-indigo-200 dark:border-indigo-800"
                title={tx("Mở trong trình soạn thảo Workflow toàn diện", "Open in full Workflow Editor")}
              >
                <ArrowUpRight className="h-3.5 w-3.5" />
                <span className="hidden xl:inline">{tx("Workflow Editor", "Editor")}</span>
              </Button>
            </Link>
          )}

          {/* Run button for runnable code files */}
          {isRunnable && !isWorkflow && (
            <Button
              size="sm"
              variant="default"
              className="h-8 gap-1.5 px-2.5 text-xs font-medium bg-emerald-600 hover:bg-emerald-700 text-white"
              onClick={handleRunCode}
              disabled={isRunning || isLoadingContent}
              title={tx("Chạy code trong Sandbox an toàn", "Run code in isolated sandbox")}
            >
              {isRunning ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                  <span className="hidden xl:inline">{tx("Đang chạy...", "Running...")}</span>
                </>
              ) : (
                <>
                  <Play className="h-3.5 w-3.5 fill-current" aria-hidden="true" />
                  <span className="hidden xl:inline">{tx("Chạy", "Run")}</span>
                </>
              )}
            </Button>
          )}

          {/* Copy button */}
          <Button
            size="sm"
            variant="outline"
            className="h-8 gap-1.5 px-2 text-xs"
            onClick={handleCopy}
            disabled={isLoadingContent || !content}
            title={copied ? tx("Đã sao chép", "Copied") : tx("Sao chép nội dung", "Copy content")}
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-emerald-500" aria-hidden="true" />
            ) : (
              <Copy className="h-3.5 w-3.5" aria-hidden="true" />
            )}
            <span className="hidden xl:inline">{copied ? tx("Đã chép", "Copied") : tx("Sao chép", "Copy")}</span>
          </Button>

          {/* Download button */}
          <Button
            size="sm"
            variant="outline"
            className="h-8 w-8 p-0"
            onClick={handleDownload}
            disabled={isLoadingContent || !content}
            title={tx("Tải tệp xuống", "Download file")}
          >
            <Download className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>

          {/* Fullscreen toggle button */}
          <Button
            size="sm"
            variant="ghost"
            className={cn(
              "h-8 gap-1 px-2 text-xs",
              isFullscreen
                ? "text-primary bg-primary/10 hover:bg-primary/20"
                : "text-muted-foreground hover:text-foreground p-0 w-8",
            )}
            onClick={toggleFullscreen}
            title={
              isFullscreen
                ? tx("Thu nhỏ (Esc)", "Exit fullscreen (Esc)")
                : tx("Toàn màn hình", "Fullscreen")
            }
          >
            {isFullscreen ? (
              <>
                <Minimize2 className="h-4 w-4" aria-hidden="true" />
                <span className="inline font-medium">{tx("Thu nhỏ", "Exit")}</span>
              </>
            ) : (
              <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
            )}
          </Button>

          {/* Close button */}
          <Button
            size="sm"
            variant="ghost"
            className="h-8 w-8 p-0 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            onClick={closeCanvas}
            title={tx("Đóng Canvas (Esc)", "Close Canvas (Esc)")}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>

      {/* 2. Content Body */}
      <div className="relative flex flex-1 min-h-0 flex-col overflow-hidden bg-card/20">
        {isLoadingContent ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin text-primary" aria-hidden="true" />
            <span className="text-xs">
              {isWorkflow
                ? tx("Đang nạp sơ đồ Workflow...", "Loading workflow DAG...")
                : tx("Đang tải nội dung tệp...", "Loading file content...")}
            </span>
          </div>
        ) : contentError ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-destructive">
            <AlertCircle className="h-8 w-8" aria-hidden="true" />
            <span className="text-sm font-semibold">
              {tx("Không thể tải nội dung", "Could not load content")}
            </span>
            <span className="text-xs text-muted-foreground">{contentError}</span>
          </div>
        ) : isWorkflow && activeTab === "workflow" ? (
          /* Workflow Interactive DAG Canvas */
          <div className="absolute inset-0 bg-slate-50/50 dark:bg-zinc-950">
            {wfNodes.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground p-6 text-center">
                <Network className="h-8 w-8 text-muted-foreground/40" />
                <p className="text-sm font-medium">{tx("Sơ đồ quy trình trống", "Empty workflow graph")}</p>
                <p className="text-xs text-muted-foreground">
                  {tx("Chưa có node nào được định nghĩa trong workflow này.", "No nodes defined in this workflow.")}
                </p>
              </div>
            ) : (
              <WorkflowCanvas
                className="h-full w-full rounded-none border-0 bg-transparent"
                graphNodes={wfNodes}
                graphEdges={wfEdges}
                nodeStatus={workflowNodeStatus}
                selectedNodeId={selectedNodeId}
                onSelectNode={setSelectedNodeId}
                onGraphChange={(newNodes, newEdges) => {
                  setWfNodes(newNodes);
                  setWfEdges(newEdges);
                }}
                onCreateNode={() => {}}
              />
            )}

            {/* Bottom floating badge info for workflow */}
            <div className="absolute bottom-3 left-3 z-10 flex items-center gap-2 rounded-lg border border-border/80 bg-background/90 px-3 py-1.5 shadow-sm backdrop-blur-xs text-xs font-mono">
              <span className="text-muted-foreground">Nodes:</span>
              <span className="font-semibold text-foreground">{wfNodes.length}</span>
              <span className="text-muted-foreground/50">|</span>
              <span className="text-muted-foreground">Edges:</span>
              <span className="font-semibold text-foreground">{wfEdges.length}</span>
              {workflowRunQuery.data?.status && (
                <>
                  <span className="text-muted-foreground/50">|</span>
                  <Badge
                    variant="outline"
                    className={cn(
                      "text-[10px] uppercase font-mono tracking-wider",
                      workflowRunQuery.data.status === "succeeded"
                        ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400"
                        : workflowRunQuery.data.status === "failed"
                        ? "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-400"
                        : "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950/40 dark:text-sky-400",
                    )}
                  >
                    {workflowRunQuery.data.status}
                  </Badge>
                </>
              )}
            </div>
          </div>
        ) : isWorkflow && activeTab === "logs" && targetRunId ? (
          /* Workflow Run Execution Timeline & Logs */
          <div className="flex h-full flex-col overflow-y-auto p-4 space-y-3 bg-zinc-950 text-zinc-100 font-mono text-xs">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
              <div className="flex items-center gap-2">
                <Terminal className="h-4 w-4 text-indigo-400" />
                <span className="font-semibold text-zinc-200">
                  {tx("Tiến trình thực thi Run:", "Execution Run:")} #{targetRunId.slice(0, 8)}
                </span>
              </div>
              {workflowRunQuery.data?.status && (
                <span className="text-[11px] uppercase font-bold text-zinc-400">
                  Status: {workflowRunQuery.data.status}
                </span>
              )}
            </div>

            {workflowRunQuery.data?.nodes && workflowRunQuery.data.nodes.length > 0 ? (
              <div className="space-y-2 pt-1">
                {workflowRunQuery.data.nodes.map((nr, idx) => {
                  const isDone = nr.status === "succeeded";
                  const isErr = nr.status === "failed";
                  const isRun = nr.status === "running";
                  return (
                    <div
                      key={idx}
                      className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3 space-y-2 leading-relaxed"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 font-semibold">
                          {isDone ? (
                            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                          ) : isErr ? (
                            <XCircle className="h-4 w-4 text-rose-400 shrink-0" />
                          ) : isRun ? (
                            <Loader2 className="h-4 w-4 text-sky-400 animate-spin shrink-0" />
                          ) : (
                            <Clock className="h-4 w-4 text-zinc-500 shrink-0" />
                          )}
                          <span className="text-zinc-200">{nr.node_id}</span>
                        </div>
                        <span className="text-[10px] text-zinc-400 uppercase font-bold">
                          {nr.status}
                        </span>
                      </div>

                      {nr.output && (
                        <div className="pt-1">
                          <span className="text-[10px] uppercase text-zinc-500 font-bold block mb-1">
                            Output:
                          </span>
                          <pre className="p-2 rounded bg-zinc-950 border border-zinc-800/80 text-[11px] text-zinc-300 max-h-40 overflow-auto whitespace-pre-wrap">
                            {typeof nr.output === "string"
                              ? nr.output
                              : JSON.stringify(nr.output, null, 2)}
                          </pre>
                        </div>
                      )}

                      {nr.error && (
                        <div className="pt-1 text-rose-400 text-xs font-semibold">
                          Error: {nr.error}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="py-12 text-center text-zinc-500 italic">
                {tx("Đang chờ các bước workflow bắt đầu...", "Waiting for workflow node runs to begin...")}
              </div>
            )}
          </div>
        ) : activeTab === "code" ? (
          /* Code / JSON View with Line Numbers */
          <div className="flex h-full w-full overflow-auto font-mono text-xs select-text">
            {/* Line numbers column */}
            <div
              className="sticky left-0 flex flex-col shrink-0 select-none border-r border-border/40 bg-muted/20 px-3 py-4 text-right text-[11px] text-muted-foreground/60"
              aria-hidden="true"
            >
              {lines.map((_, idx) => (
                <span key={idx} className="leading-relaxed">
                  {idx + 1}
                </span>
              ))}
            </div>

            {/* Code lines */}
            <div className="flex-1 min-w-0 p-4">
              <pre className="m-0 whitespace-pre leading-relaxed text-foreground/90 font-mono">
                <code>{content}</code>
              </pre>
            </div>
          </div>
        ) : isHtml ? (
          /* Live HTML / Web Preview */
          <div className="flex h-full flex-col">
            <div className="flex h-9 shrink-0 items-center justify-between border-b border-border/60 bg-muted/40 px-3">
              <span className="text-[11px] text-muted-foreground font-mono">
                {tx("Sandbox HTML Preview", "Sandbox HTML Preview")}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2 text-[11px] gap-1 text-muted-foreground hover:text-foreground"
                  onClick={() => setIframeKey((k) => k + 1)}
                  title={tx("Tải lại preview", "Reload preview")}
                >
                  <RotateCw className="h-3 w-3" aria-hidden="true" />
                  <span>{tx("Tải lại", "Reload")}</span>
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2 text-[11px] gap-1 text-muted-foreground hover:text-foreground"
                  onClick={handleOpenNewTab}
                  title={tx("Mở trang trong tab mới", "Open in new tab")}
                >
                  <ExternalLink className="h-3 w-3" aria-hidden="true" />
                  <span>{tx("Tab mới", "New tab")}</span>
                </Button>
              </div>
            </div>
            <div className="flex-1 min-h-0 bg-white">
              <iframe
                key={iframeKey}
                title={activeItem.title}
                srcDoc={content}
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                className={cn("h-full w-full border-0", isDragging && "pointer-events-none")}
              />
            </div>
          </div>
        ) : (
          /* Live Code Execution Console Output */
          <div className="flex h-full flex-col overflow-hidden">
            {/* Top mini code view */}
            <div className="max-h-[45%] flex-1 overflow-auto border-b border-border/70 bg-muted/10 p-4 font-mono text-xs">
              <pre className="m-0 whitespace-pre-wrap leading-relaxed text-muted-foreground font-mono">
                <code>{content}</code>
              </pre>
            </div>

            {/* Bottom terminal logs */}
            <div className="flex flex-1 flex-col min-h-0 bg-zinc-950 text-zinc-100 font-mono text-xs">
              <div className="flex h-8 shrink-0 items-center justify-between border-b border-zinc-800 px-3">
                <div className="flex items-center gap-1.5 text-zinc-400 text-[11px]">
                  <Terminal className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>{tx("Sandbox Terminal Console", "Sandbox Terminal Console")}</span>
                </div>
                {exitCode !== null && (
                  <span
                    className={cn(
                      "rounded px-1.5 py-0.5 text-[10px] font-semibold",
                      exitCode === 0
                        ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                        : "bg-rose-950 text-rose-400 border border-rose-800",
                    )}
                  >
                    exit: {exitCode}
                  </span>
                )}
              </div>

              <div className="flex-1 min-h-0 overflow-auto p-3 space-y-1 select-text">
                {logs.length === 0 && !isRunning && !runError && (
                  <div className="text-zinc-500 text-[11px] italic">
                    {tx("Bấm 'Chạy' để thực thi mã nguồn trong sandbox.", "Click 'Run' to execute code in sandbox.")}
                  </div>
                )}
                {logs.map((line, idx) => (
                  <div key={idx} className="whitespace-pre-wrap leading-tight text-zinc-200">
                    {line}
                  </div>
                ))}
                {runError && (
                  <div className="text-rose-400 text-xs font-semibold pt-1">{runError}</div>
                )}
                <div ref={logEndRef} />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  if (isFullscreen && typeof document !== "undefined") {
    return createPortal(panelContent, document.body);
  }

  return panelContent;
}
