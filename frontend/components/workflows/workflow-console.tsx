/**
 * WorkflowConsole - Live SSE logs, real-time node trace & final output viewer.
 * Includes interactive Node Execution Inspector, search filter, and Full Markdown Report Dialog.
 */
"use client";

import * as React from "react";
import {
  Terminal,
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  ChevronRight,
  Maximize2,
  Minimize2,
  Copy,
  RotateCcw,
  Search,
  Wrench,
  Cpu,
  Coins,
  AlertCircle,
  FileText,
  Download,
  Info,
  Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { useTranslation } from "@/lib/i18n";
import type { WorkflowRunDetail, WorkflowNodeRunDetail } from "@/types";

export interface WorkflowLogItem {
  id: string;
  ts: number;
  node?: string;
  node_id?: string;
  event: string;
  message: string;
  output?: unknown;
  data?: Record<string, unknown>;
}

interface WorkflowConsoleProps {
  logs: WorkflowLogItem[];
  output: string;
  running: boolean;
  run?: WorkflowRunDetail | null;
  onReplay?: () => void;
  selectedNodeId?: string | null;
  onSelectNode?: (nodeId: string | null) => void;
  className?: string;
}

export function WorkflowConsole({
  logs,
  output,
  running,
  run,
  onReplay,
  selectedNodeId,
  onSelectNode,
  className,
}: WorkflowConsoleProps) {
  const { t, locale, tx } = useTranslation();
  const [activeTab, setActiveTab] = React.useState<"logs" | "trace" | "output">("logs");
  const [isMaximized, setIsMaximized] = React.useState(false);
  const [searchFilter, setSearchFilter] = React.useState("");
  const [inspectedNodeId, setInspectedNodeId] = React.useState<string | null>(null);
  const [showFinalReportModal, setShowFinalReportModal] = React.useState(false);
  const [outputViewMode, setOutputViewMode] = React.useState<"markdown" | "raw">("markdown");
  const scrollRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (activeTab === "logs" && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, activeTab]);

  React.useEffect(() => {
    if (selectedNodeId) {
      const exists = run?.nodes.some((n) => n.node_id === selectedNodeId);
      if (exists) {
        setInspectedNodeId(selectedNodeId);
      }
    }
  }, [selectedNodeId, run?.nodes]);

  const copyText = (text: string, label: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    toast.success(locale === "vi" ? `Đã sao chép ${label}` : `Copied ${label}`);
  };

  const downloadMarkdownReport = () => {
    if (!output) return;
    const blob = new Blob([output], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `workflow-report-${run?.id || "result"}.md`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(locale === "vi" ? "Đã tải xuống tệp báo cáo .md" : "Downloaded .md report");
  };

  const filteredLogs = React.useMemo(() => {
    if (!searchFilter.trim()) return logs;
    const q = searchFilter.toLowerCase();
    return logs.filter(
      (l) =>
        l.message.toLowerCase().includes(q) ||
        ((l.node || l.node_id) && (l.node || l.node_id)!.toLowerCase().includes(q)) ||
        l.event.toLowerCase().includes(q)
    );
  }, [logs, searchFilter]);

  const inspectedNode: WorkflowNodeRunDetail | undefined = React.useMemo(() => {
    if (!inspectedNodeId || !run?.nodes) return undefined;
    return run.nodes.find((n) => n.node_id === inspectedNodeId);
  }, [inspectedNodeId, run?.nodes]);

  const inspectedTokens = React.useMemo(() => {
    if (!inspectedNode) return null;
    return (
      inspectedNode.tokens ??
      (inspectedNode.output as any)?.tokens ??
      ((inspectedNode.output as any)?.data as any)?.usage?.total_tokens ??
      ((inspectedNode.output as any)?.data as any)?.tokens ??
      null
    );
  }, [inspectedNode]);

  const inspectedCost = React.useMemo(() => {
    if (!inspectedNode) return null;
    return (
      inspectedNode.cost_usd ??
      (inspectedNode.output as any)?.cost_usd ??
      ((inspectedNode.output as any)?.data as any)?.cost_usd ??
      null
    );
  }, [inspectedNode]);

  const inspectedTiming = React.useMemo(() => {
    if (!inspectedNode) return null;
    if (inspectedNode.timing_ms) return inspectedNode.timing_ms;
    if ((inspectedNode.output as any)?.timing_ms) return (inspectedNode.output as any).timing_ms;
    if (inspectedNode.started_at && inspectedNode.finished_at) {
      const diff = new Date(inspectedNode.finished_at).getTime() - new Date(inspectedNode.started_at).getTime();
      return Math.max(0, diff);
    }
    return null;
  }, [inspectedNode]);

  return (
    <>
      <div
        className={cn(
          "flex flex-col rounded-2xl border border-border/80 bg-card/60 backdrop-blur-xl shadow-3d-card transition-all duration-300",
          isMaximized ? "h-[560px]" : "h-[320px]",
          className
        )}
      >
        <div className="flex items-center justify-between border-b border-border/60 px-3.5 py-2.5 bg-muted/20">
          <div className="flex items-center gap-2">
            <div className="flex rounded-xl bg-muted/40 p-0.5 border border-border/40">
              <button
                type="button"
                onClick={() => setActiveTab("logs")}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs transition-colors",
                  activeTab === "logs"
                    ? "bg-card text-foreground font-semibold shadow-inner-edge"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Terminal className="h-3.5 w-3.5 text-primary" />
                {t("pages.workflows.liveLogsTab", "Live Logs")}
                {logs.length > 0 && (
                  <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-primary/10 text-primary font-mono">
                    {logs.length}
                  </span>
                )}
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("trace")}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs transition-colors",
                  activeTab === "trace"
                    ? "bg-card text-foreground font-semibold shadow-inner-edge"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Activity className="h-3.5 w-3.5 text-info" />
                {t("pages.workflows.traceTab", "Node Trace")}
                {run?.nodes && run.nodes.length > 0 && (
                  <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-info/10 text-info font-mono">
                    {run.nodes.length}
                  </span>
                )}
              </button>

              <button
                type="button"
                onClick={() => setActiveTab("output")}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs transition-colors",
                  activeTab === "output"
                    ? "bg-card text-foreground font-semibold shadow-inner-edge"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <FileText className="h-3.5 w-3.5 text-emerald-500" />
                {t("pages.workflows.finalOutput", "Final Output")}
                {output && (
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                )}
              </button>
            </div>

            {running && (
              <span className="flex items-center gap-1.5 text-xs text-primary font-mono animate-pulse">
                <span className="h-2 w-2 rounded-full bg-primary" />
                {t("pages.workflows.statusRunning", "Running")}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {activeTab === "logs" && (
              <div className="relative">
                <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
                <Input
                  className="h-7 w-36 sm:w-48 pl-7 text-[11px] bg-background/50 border-border/40"
                  placeholder={t("pages.workflows.searchLogs", "Search logs...")}
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                />
              </div>
            )}

            {output && (
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs gap-1.5 border-emerald-500/30 text-emerald-600 dark:text-emerald-400 bg-emerald-500/5 hover:bg-emerald-500/10"
                onClick={() => setShowFinalReportModal(true)}
              >
                <FileText className="h-3.5 w-3.5" />
                {t("pages.workflows.viewMarkdownModal", "View Markdown Report")}
              </Button>
            )}

            {onReplay && (
              <Button
                variant="outline"
                size="sm"
                className="h-7 text-xs gap-1"
                onClick={onReplay}
              >
                <RotateCcw className="h-3 w-3" /> {t("pages.workflows.replay", "Replay")}
              </Button>
            )}

            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-foreground"
              title={isMaximized ? t("pages.workflows.minimizeConsole", "Minimize") : t("pages.workflows.maximizeConsole", "Maximize")}
              onClick={() => setIsMaximized((v) => !v)}
            >
              {isMaximized ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 scrollbar-thin">
          {activeTab === "logs" && (
            <div className="space-y-1 font-mono text-[11px]">
              {filteredLogs.length === 0 ? (
                <div className="flex h-36 items-center justify-center text-muted-foreground/60 text-xs">
                  {searchFilter ? "No logs matching search query." : t("pages.workflows.noLogsYet", "No logs yet. Run workflow to stream events.")}
                </div>
              ) : (
                filteredLogs.map((log) => (
                  <div
                    key={log.id}
                    className="flex items-start gap-2 py-0.5 px-1.5 rounded hover:bg-muted/30 transition-colors"
                  >
                    <span className="text-muted-foreground/50 shrink-0 select-none text-[10px]">
                      {new Date(log.ts).toLocaleTimeString()}
                    </span>
                    <span
                      className={cn(
                        "px-1 py-0.2 rounded text-[9px] uppercase font-bold shrink-0",
                        log.event === "start" && "bg-info/10 text-info border border-info/20",
                        log.event === "done" && "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20",
                        log.event === "error" && "bg-destructive/10 text-destructive border border-destructive/20",
                        log.event === "edge" && "bg-primary/10 text-primary border border-primary/20",
                        log.event === "finish" && "bg-emerald-600 text-white"
                      )}
                    >
                      {log.event}
                    </span>
                    {(log.node || log.node_id) && (
                      <span className="text-primary/80 font-bold shrink-0">[{log.node || log.node_id}]</span>
                    )}
                    <span className="text-foreground/90 whitespace-pre-wrap break-all select-text">
                      {log.message}
                    </span>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "trace" && (
            <div className="space-y-2">
              {!run?.nodes || run.nodes.length === 0 ? (
                <div className="flex h-36 items-center justify-center text-muted-foreground/60 text-xs">
                  {t("pages.workflows.noTraceYet", "Run workflow to inspect executed node trace.")}
                </div>
              ) : (
                run.nodes.map((node) => (
                  <div
                    key={node.id}
                    onClick={() => {
                      setInspectedNodeId(node.node_id);
                      if (onSelectNode) onSelectNode(node.node_id);
                    }}
                    className={cn(
                      "flex items-center justify-between p-2.5 rounded-xl border bg-card/40 hover:bg-muted/30 cursor-pointer transition-all active-tactile",
                      inspectedNodeId === node.node_id
                        ? "border-primary ring-1 ring-primary/40 shadow-sm"
                        : "border-border/60 hover:border-border"
                    )}
                  >
                    <div className="flex items-center gap-3">
                      {node.status === "succeeded" ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                      ) : node.status === "failed" ? (
                        <XCircle className="h-4 w-4 text-destructive shrink-0" />
                      ) : (
                        <Clock className="h-4 w-4 text-primary animate-spin shrink-0" />
                      )}
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold text-foreground font-mono">{node.node_id}</span>
                          <Badge variant="outline" className="text-[10px] font-mono">
                            {node.status}
                          </Badge>
                        </div>
                        {node.error && (
                          <p className="text-[11px] text-destructive line-clamp-1 mt-0.5">{node.error}</p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-3 text-[11px] text-muted-foreground font-mono">
                      {node.tokens ? (
                        <span className="flex items-center gap-1">
                          <Cpu className="h-3 w-3 text-amber-500" />
                          {node.tokens} tok
                        </span>
                      ) : null}
                      {node.cost_usd ? (
                        <span className="flex items-center gap-1">
                          <Coins className="h-3 w-3 text-emerald-500" />
                          ${Number(node.cost_usd).toFixed(4)}
                        </span>
                      ) : null}
                      <Button size="sm" variant="ghost" className="h-6 px-2 text-[10px] gap-1">
                        {t("pages.workflows.inspectNode", "Inspect")}
                        <ChevronRight className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "output" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between border-b border-border/40 pb-2">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <FileText className="h-3.5 w-3.5 text-emerald-500" />
                    {t("pages.workflows.finalOutput", "Final Output")}
                  </span>
                  <div className="flex rounded-lg bg-muted/40 p-0.5 border border-border/40 ml-2">
                    <button
                      type="button"
                      onClick={() => setOutputViewMode("markdown")}
                      className={cn(
                        "px-2 py-0.5 rounded text-[11px] transition-colors",
                        outputViewMode === "markdown"
                          ? "bg-card text-foreground font-semibold shadow-inner-edge"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {t("pages.workflows.formattedMarkdown", "Markdown")}
                    </button>
                    <button
                      type="button"
                      onClick={() => setOutputViewMode("raw")}
                      className={cn(
                        "px-2 py-0.5 rounded text-[11px] transition-colors",
                        outputViewMode === "raw"
                          ? "bg-card text-foreground font-semibold shadow-inner-edge"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {t("pages.workflows.rawJson", "Raw JSON")}
                    </button>
                  </div>
                </div>

                <div className="flex items-center gap-1.5">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 text-[10px] gap-1"
                    onClick={() => copyText(output, "Final output")}
                  >
                    <Copy className="h-3 w-3" /> {t("common.copy", "Copy")}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 text-[10px] gap-1"
                    onClick={downloadMarkdownReport}
                  >
                    <Download className="h-3 w-3" /> {t("pages.workflows.downloadReport", "Download .md")}
                  </Button>
                  <Button
                    size="sm"
                    className="h-6 text-[10px] gap-1 bg-emerald-600 hover:bg-emerald-700 text-white font-medium"
                    onClick={() => setShowFinalReportModal(true)}
                  >
                    <Maximize2 className="h-3 w-3" /> {t("pages.workflows.viewMarkdownModal", "Modal")}
                  </Button>
                </div>
              </div>

              {!output ? (
                <div className="flex h-36 items-center justify-center text-muted-foreground/60 text-xs">
                  {t("pages.workflows.noOutputYet", "No output produced yet. Run workflow to generate output.")}
                </div>
              ) : outputViewMode === "markdown" ? (
                <div className="prose prose-sm dark:prose-invert max-w-none p-3.5 rounded-xl border border-border/60 bg-card/40 select-text overflow-y-auto">
                  <MarkdownRenderer content={output} />
                </div>
              ) : (
                <pre className="p-3.5 rounded-xl border border-border/60 bg-black/60 font-mono text-[11px] text-foreground/90 whitespace-pre-wrap select-text overflow-y-auto max-h-72">
                  {output}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 1. Interactive Node Execution Inspector Modal */}
      <Dialog open={Boolean(inspectedNode)} onOpenChange={(open) => !open && setInspectedNodeId(null)}>
        <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto p-6 backdrop-blur-2xl">
          {inspectedNode && (
            <div className="space-y-5">
              <DialogHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20 font-mono font-bold text-xs">
                      {inspectedNode.node_id.slice(0, 3)}
                    </div>
                    <div>
                      <DialogTitle className="text-base font-bold flex items-center gap-2">
                        {inspectedNode.node_id}
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-[10px] font-mono",
                            inspectedNode.status === "succeeded" && "border-emerald-500/30 text-emerald-600 bg-emerald-500/10",
                            inspectedNode.status === "failed" && "border-destructive/30 text-destructive bg-destructive/10"
                          )}
                        >
                          {inspectedNode.status}
                        </Badge>
                      </DialogTitle>
                      <DialogDescription className="text-xs text-muted-foreground">
                        {t("pages.workflows.nodeInspectorDesc", "Inspect input payload, node output, executed tool calls, latency, and cost.")}
                      </DialogDescription>
                    </div>
                  </div>
                </div>
              </DialogHeader>

              {/* KPI Strip */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
                <div className="p-2.5 rounded-xl border border-border/60 bg-muted/20 space-y-0.5">
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                    <Clock className="h-3 w-3" /> {t("pages.workflows.duration", "Duration")}
                  </span>
                  <span className="font-mono font-bold text-foreground">
                    {inspectedTiming != null ? `${inspectedTiming}ms` : "—"}
                  </span>
                </div>

                <div className="p-2.5 rounded-xl border border-border/60 bg-muted/20 space-y-0.5">
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                    <Cpu className="h-3 w-3 text-amber-500" /> {t("pages.workflows.tokens", "Tokens")}
                  </span>
                  <span className="font-mono font-bold text-foreground">
                    {inspectedTokens != null ? Number(inspectedTokens).toLocaleString() : "—"}
                  </span>
                </div>

                <div className="p-2.5 rounded-xl border border-border/60 bg-muted/20 space-y-0.5">
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                    <Coins className="h-3 w-3 text-emerald-500" /> {t("pages.workflows.cost", "Cost")}
                  </span>
                  <span className="font-mono font-bold text-foreground">
                    {inspectedCost != null ? `$${Number(inspectedCost).toFixed(4)}` : "—"}
                  </span>
                </div>

                <div className="p-2.5 rounded-xl border border-border/60 bg-muted/20 space-y-0.5">
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                    <Layers className="h-3 w-3 text-primary" /> Attempt
                  </span>
                  <span className="font-mono font-bold text-foreground">
                    #{inspectedNode.attempt}
                  </span>
                </div>
              </div>

              {/* Error Alert if failed */}
              {inspectedNode.error && (
                <div className="p-3 rounded-xl border border-destructive/40 bg-destructive/10 text-destructive text-xs space-y-1">
                  <span className="font-bold flex items-center gap-1.5">
                    <AlertCircle className="h-3.5 w-3.5" /> Execution Error
                  </span>
                  <p className="font-mono whitespace-pre-wrap">{inspectedNode.error}</p>
                </div>
              )}

              {/* Input payload */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <Terminal className="h-3.5 w-3.5 text-primary" />
                    {t("pages.workflows.nodeInput", "Input Payload")}
                  </span>
                  {inspectedNode.input && Object.keys(inspectedNode.input).length > 0 && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-5 px-1.5 text-[10px] gap-1"
                      onClick={() => copyText(JSON.stringify(inspectedNode.input, null, 2), "Input payload")}
                    >
                      <Copy className="h-3 w-3" /> {t("common.copy", "Copy")}
                    </Button>
                  )}
                </div>
                <pre className="p-3 rounded-xl border border-border/60 bg-black/50 font-mono text-[11px] text-foreground/90 whitespace-pre-wrap max-h-48 overflow-y-auto scrollbar-thin select-text">
                  {inspectedNode.input && Object.keys(inspectedNode.input).length > 0
                    ? JSON.stringify(inspectedNode.input, null, 2)
                    : t("pages.workflows.noInputData", "No input payload available")}
                </pre>
              </div>

              {/* Output payload */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                    {t("pages.workflows.nodeOutput", "Output Payload")}
                  </span>
                  {inspectedNode.output && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-5 px-1.5 text-[10px] gap-1"
                      onClick={() =>
                        copyText(
                          typeof (inspectedNode.output as any)?.text === "string"
                            ? (inspectedNode.output as any).text
                            : JSON.stringify(inspectedNode.output, null, 2),
                          "Output payload"
                        )
                      }
                    >
                      <Copy className="h-3 w-3" /> {t("common.copy", "Copy")}
                    </Button>
                  )}
                </div>

                {typeof (inspectedNode.output as any)?.text === "string" && (inspectedNode.output as any).text.trim() ? (
                  <div className="prose prose-sm dark:prose-invert max-w-none p-3.5 rounded-xl border border-border/60 bg-card/40 max-h-64 overflow-y-auto scrollbar-thin select-text">
                    <MarkdownRenderer content={(inspectedNode.output as any).text} />
                  </div>
                ) : inspectedNode.output && Object.keys(inspectedNode.output).length > 0 ? (
                  <pre className="p-3 rounded-xl border border-border/60 bg-black/50 font-mono text-[11px] text-foreground/90 whitespace-pre-wrap max-h-64 overflow-y-auto scrollbar-thin select-text">
                    {JSON.stringify(inspectedNode.output, null, 2)}
                  </pre>
                ) : (
                  <div className="flex items-center gap-2 p-3 text-xs text-muted-foreground bg-muted/20 border border-border/40 rounded-xl">
                    <Info className="h-4 w-4 text-muted-foreground shrink-0" />
                    {t("pages.workflows.noOutputYet", "No output data produced yet")}
                  </div>
                )}
              </div>

              {/* Tool Calls section */}
              {Array.isArray((inspectedNode.output?.data as any)?.tool_calls) && (inspectedNode.output.data as any).tool_calls.length > 0 && (
                <div className="space-y-1.5">
                  <span className="text-xs font-bold text-foreground flex items-center gap-1.5">
                    <Wrench className="h-3.5 w-3.5 text-info" />
                    {t("pages.workflows.toolCalls", "Tool Calls")} ({(inspectedNode.output?.data as any)?.tool_calls?.length || 0})
                  </span>
                  <div className="space-y-2 max-h-52 overflow-y-auto scrollbar-thin">
                    {(inspectedNode.output?.data as any)?.tool_calls?.map((tc: any, i: number) => (
                      <div key={i} className="p-2.5 rounded-xl border border-border/60 bg-muted/20 text-xs space-y-1 font-mono">
                        <div className="font-bold text-info flex items-center justify-between">
                          <span>{tc.tool || tc.name || `tool_${i}`}</span>
                          {tc.duration_ms && <span className="text-muted-foreground text-[10px]">{tc.duration_ms}ms</span>}
                        </div>
                        {tc.args && (
                          <pre className="text-[10px] text-muted-foreground whitespace-pre-wrap bg-background/50 p-1.5 rounded">
                            {JSON.stringify(tc.args, null, 2)}
                          </pre>
                        )}
                        {tc.result && (
                          <pre className="text-[10px] text-foreground/90 whitespace-pre-wrap bg-background/50 p-1.5 rounded line-clamp-3">
                            {typeof tc.result === "string" ? tc.result : JSON.stringify(tc.result, null, 2)}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* 2. Dedicated Final Output Markdown Modal */}
      <Dialog open={showFinalReportModal} onOpenChange={setShowFinalReportModal}>
        <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col p-6 backdrop-blur-2xl">
          <DialogHeader className="border-b border-border/40 pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                  <FileText className="h-5 w-5" />
                </div>
                <div>
                  <DialogTitle className="text-lg font-bold">
                    {t("pages.workflows.finalReportModalTitle", "Final Workflow Report")}
                  </DialogTitle>
                  <DialogDescription className="text-xs text-muted-foreground">
                    {run?.id ? `Run ID: ${run.id}` : tx("Tổng hợp thực thi cuối của workflow", "Rendered workflow final execution synthesis")}
                  </DialogDescription>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5 text-xs"
                  onClick={() => copyText(output, "Final markdown report")}
                >
                  <Copy className="h-3.5 w-3.5" />
                  {t("common.copy", "Copy")}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5 text-xs"
                  onClick={downloadMarkdownReport}
                >
                  <Download className="h-3.5 w-3.5" />
                  {t("pages.workflows.downloadReport", "Download .md")}
                </Button>
              </div>
            </div>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto py-4 px-1 scrollbar-thin">
            {!output ? (
              <div className="flex h-64 items-center justify-center text-muted-foreground/60 text-sm">
                {t("pages.workflows.noOutputYet", "No output produced yet.")}
              </div>
            ) : (
              <div className="prose prose-sm dark:prose-invert max-w-none p-5 rounded-2xl border border-border/60 bg-card/60 shadow-inner select-text">
                <MarkdownRenderer content={output} />
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
