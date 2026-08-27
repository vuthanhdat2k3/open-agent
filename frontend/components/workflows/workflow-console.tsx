"use client";

import * as React from "react";
import {
  Terminal,
  CheckCircle2,
  Clock,
  Copy,
  Check,
  RefreshCw,
  Maximize2,
  Minimize2,
  Search,
  AlertCircle,
  Wrench,
  Code2,
  Eye,
  Info,
  DollarSign,
  Zap,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { useTranslation } from "@/lib/i18n";
import type { WorkflowRunDetail, WorkflowNodeRunDetail } from "@/types";

export type WorkflowLogItem = {
  id: string;
  ts: number;
  event: string;
  node_id?: string;
  message: string;
  output?: string;
};

interface WorkflowConsoleProps {
  logs: WorkflowLogItem[];
  output: string;
  running: boolean;
  run?: WorkflowRunDetail | undefined;
  onReplay?: () => void;
  selectedNodeId?: string | null;
  onSelectNode?: (nodeId: string | null) => void;
}

const NODE_STATUS: Record<string, { labelKey: string; className: string }> = {
  succeeded: { labelKey: "pages.workflows.statusDone", className: "bg-success/12 text-success border-success/30" },
  failed: { labelKey: "pages.workflows.statusFailed", className: "bg-destructive/12 text-destructive border-destructive/30" },
  running: { labelKey: "pages.workflows.statusRunning", className: "bg-info/12 text-info border-info/30" },
  skipped: { labelKey: "pages.workflows.statusSkipped", className: "bg-muted/20 text-muted-foreground border-border/40" },
  waiting_approval: { labelKey: "pages.workflows.statusWaiting", className: "bg-warning/12 text-warning border-warning/30" },
  pending: { labelKey: "pages.workflows.statusPending", className: "bg-muted/20 text-muted-foreground border-border/40" },
};

function fmtDurationMs(ms?: number) {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function WorkflowConsole({
  logs,
  output,
  running,
  run,
  onReplay,
  selectedNodeId,
  onSelectNode,
}: WorkflowConsoleProps) {
  const { t, locale } = useTranslation();
  const [activeTab, setActiveTab] = React.useState<"logs" | "trace" | "output">("logs");
  const [copied, setCopied] = React.useState(false);
  const [isMaximized, setIsMaximized] = React.useState(false);
  const [filterQuery, setFilterQuery] = React.useState("");
  const [inspectedNode, setInspectedNode] = React.useState<WorkflowNodeRunDetail | null>(null);
  const logEndRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (activeTab === "logs" && !filterQuery) {
      logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs.length, activeTab, filterQuery]);

  // If user selected node from canvas while in trace tab, open inspector
  React.useEffect(() => {
    if (selectedNodeId && run?.nodes) {
      const match = run.nodes.find((n) => n.node_id === selectedNodeId);
      if (match && activeTab === "trace") {
        setInspectedNode(match);
      }
    }
  }, [selectedNodeId, run?.nodes, activeTab]);

  const copyOutput = () => {
    if (!output) return;
    navigator.clipboard.writeText(output);
    setCopied(true);
    toast.success(t("pages.workflows.outputCopied", "Output copied to clipboard"));
    setTimeout(() => setCopied(false), 2000);
  };

  const copyText = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} ${t("common.copied", "copied")}`);
  };

  const filteredLogs = React.useMemo(() => {
    if (!filterQuery.trim()) return logs;
    const q = filterQuery.toLowerCase();
    return logs.filter(
      (item) =>
        item.message?.toLowerCase().includes(q) ||
        item.node_id?.toLowerCase().includes(q) ||
        item.event?.toLowerCase().includes(q),
    );
  }, [logs, filterQuery]);

  const getEventBadge = (event: string) => {
    switch (event) {
      case "node_start":
        return <Badge variant="outline" className="border-info/40 text-info bg-info/10 text-[9px] py-0 font-mono">{t("pages.workflows.eventStart", "START")}</Badge>;
      case "node_done":
        return <Badge variant="outline" className="border-success/40 text-success bg-success/10 text-[9px] py-0 font-mono">{t("pages.workflows.eventDone", "DONE")}</Badge>;
      case "node_error":
      case "error":
        return <Badge variant="outline" className="border-destructive/40 text-destructive bg-destructive/10 text-[9px] py-0 font-mono">{t("pages.workflows.eventError", "ERROR")}</Badge>;
      case "approval_required":
        return <Badge variant="outline" className="border-warning/40 text-warning bg-warning/10 text-[9px] py-0 font-mono">{t("pages.workflows.eventWait", "WAIT")}</Badge>;
      case "edge":
        return <Badge variant="outline" className="border-border text-muted-foreground text-[9px] py-0 font-mono">{t("pages.workflows.eventEdge", "EDGE")}</Badge>;
      case "done":
        return <Badge variant="outline" className="border-primary/40 text-primary bg-primary/10 text-[9px] py-0 font-mono font-bold">{t("pages.workflows.eventFinish", "FINISH")}</Badge>;
      default:
        return <Badge variant="outline" className="text-[9px] py-0 font-mono">{event}</Badge>;
    }
  };

  const getEventTextColor = (event: string) => {
    switch (event) {
      case "node_error":
      case "error":
        return "text-destructive font-semibold";
      case "node_done":
      case "done":
        return "text-success font-medium";
      case "node_start":
        return "text-info";
      case "approval_required":
        return "text-warning font-semibold";
      case "edge":
        return "text-muted-foreground/80";
      default:
        return "text-foreground";
    }
  };

  const consoleHeightClass = isMaximized ? "max-h-[560px] h-[560px]" : "max-h-80";

  return (
    <>
      <Card glass className="overflow-hidden shadow-3d-card border-border/80 transition-all duration-300">
        <CardHeader className="flex flex-row items-center justify-between border-b border-border/60 bg-muted/20 px-4 py-2.5">
          <div className="flex items-center gap-3">
            <div className="grid h-8 w-8 place-items-center rounded-xl bg-primary/10 text-primary shadow-inner-edge border border-primary/25">
              <Terminal className="h-4 w-4" />
            </div>
            <div>
              <CardTitle className="text-sm font-semibold tracking-tight text-foreground flex items-center gap-2">
                {t("pages.workflows.consoleLogs", "Workflow Run")}
                {running && (
                  <Badge variant="outline" className="border-info/40 text-info bg-info/10 text-[10px] py-0 font-mono animate-pulse">
                    {t("pages.workflows.statusRunning", "running")}
                  </Badge>
                )}
              </CardTitle>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {activeTab === "logs" && logs.length > 5 && (
              <div className="relative hidden sm:block w-40 md:w-56">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground/60" />
                <Input
                  value={filterQuery}
                  onChange={(e) => setFilterQuery(e.target.value)}
                  placeholder={t("pages.workflows.searchLogs", "Filter logs...")}
                  className="h-7 pl-8 pr-2 text-xs bg-card/60 border-border/40 rounded-lg"
                />
              </div>
            )}

            <div className="flex rounded-lg bg-muted/50 p-1 border border-border/40 text-xs font-medium">
              <button
                onClick={() => setActiveTab("logs")}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-colors ${
                  activeTab === "logs" ? "bg-card text-foreground shadow-inner-edge font-semibold" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Clock className="h-3 w-3" />
                {t("pages.workflows.liveLogsTab", "Live Logs")}
                {logs.length > 0 && <span className="text-[10px] opacity-70">({logs.length})</span>}
              </button>
              <button
                onClick={() => setActiveTab("trace")}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-colors ${
                  activeTab === "trace" ? "bg-card text-foreground shadow-inner-edge font-semibold" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Terminal className="h-3 w-3" />
                {t("pages.workflows.traceTab", "Node Trace")}
                {run?.nodes?.length ? <span className="text-[10px] opacity-70">({run.nodes.length})</span> : null}
              </button>
              <button
                onClick={() => setActiveTab("output")}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-colors ${
                  activeTab === "output" ? "bg-card text-foreground shadow-inner-edge font-semibold" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <CheckCircle2 className="h-3 w-3" />
                {t("pages.workflows.finalOutput", "Final Output")}
              </button>
            </div>

            {onReplay && run && !running && (
              <Button size="sm" variant="outline" className="h-7 gap-1 text-[11px]" onClick={onReplay}>
                <RefreshCw className="h-3 w-3" /> {t("pages.workflows.replay", "Replay")}
              </Button>
            )}
            {activeTab === "output" && output && (
              <Button size="sm" variant="outline" className="h-7 gap-1 text-[11px]" onClick={copyOutput}>
                {copied ? <Check className="h-3 w-3 text-success" /> : <Copy className="h-3 w-3" />}
                {copied ? t("common.copied", "Copied") : t("common.copy", "Copy")}
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
              onClick={() => setIsMaximized((prev) => !prev)}
              title={isMaximized ? t("pages.workflows.minimizeConsole", "Minimize") : t("pages.workflows.maximizeConsole", "Maximize")}
            >
              {isMaximized ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </CardHeader>

        <CardContent className="p-0 bg-black/40 font-mono text-[11px] select-text">
          {activeTab === "logs" ? (
            <div className={`${consoleHeightClass} overflow-auto p-3 space-y-1.5 scrollbar-thin`}>
              {filteredLogs.length > 0 ? (
                filteredLogs.map((item) => {
                  const dateStr = new Date(item.ts).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
                  return (
                    <div key={item.id} className="flex items-start gap-2 py-0.5 border-b border-border/10 last:border-0 hover:bg-white/5 px-1.5 rounded transition-colors">
                      <span className="text-[10px] text-muted-foreground/60 shrink-0 mt-0.5">{dateStr}</span>
                      <span className="shrink-0 mt-0.5">{getEventBadge(item.event)}</span>
                      {item.node_id && (
                        <button
                          type="button"
                          onClick={() => {
                            if (run?.nodes) {
                              const match = run.nodes.find((n) => n.node_id === item.node_id);
                              if (match) setInspectedNode(match);
                            }
                          }}
                          className="text-[10px] bg-muted/30 hover:bg-primary/20 hover:text-primary border border-border/30 text-muted-foreground px-1.5 py-0.2 rounded font-mono shrink-0 mt-0.5 cursor-pointer transition-colors"
                        >
                          {item.node_id}
                        </button>
                      )}
                      <span className={`break-all leading-relaxed ${getEventTextColor(item.event)}`}>{item.message}</span>
                    </div>
                  );
                })
              ) : (
                <div className="py-12 text-center text-muted-foreground/60 text-xs font-sans">
                  {running ? (
                    <span className="flex items-center justify-center gap-2 text-info">
                      <span className="h-2 w-2 rounded-full bg-info animate-ping" />
                      {t("pages.workflows.runningStreaming", "Executing workflow and streaming live events…")}
                    </span>
                  ) : (
                    t("pages.workflows.noLogsYet", "No execution logs yet. Run workflow to stream real-time events.")
                  )}
                </div>
              )}
              <div ref={logEndRef} />
            </div>
          ) : activeTab === "trace" ? (
            <div className={`${consoleHeightClass} overflow-auto p-3 space-y-1.5 scrollbar-thin`}>
              {run?.nodes?.length ? (
                run.nodes.map((node, idx) => {
                  const status = NODE_STATUS[node.status] ?? { labelKey: node.status, className: "bg-muted/20 text-muted-foreground" };
                  const timing = node.timing_ms ?? (node.finished_at && node.started_at ? new Date(node.finished_at).getTime() - new Date(node.started_at).getTime() : undefined);
                  return (
                    <button
                      key={node.id}
                      type="button"
                      onClick={() => {
                        setInspectedNode(node);
                        onSelectNode?.(node.node_id);
                      }}
                      className="w-full flex items-center gap-3 rounded-lg border border-border/40 bg-white/[0.03] hover:bg-white/[0.08] hover:border-primary/50 px-3 py-2 text-left transition-all group cursor-pointer"
                    >
                      <span className="text-[10px] text-muted-foreground/50 w-6 text-right font-mono">{idx + 1}</span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="truncate font-semibold text-foreground/95 text-xs group-hover:text-primary transition-colors">
                            {node.node_id}
                          </span>
                          <span className="text-[9px] text-muted-foreground/60 font-sans">
                            ({t("pages.workflows.inspectNode", "Click to inspect")})
                          </span>
                        </div>
                      </div>
                      <span className="hidden sm:inline text-[10px] text-muted-foreground/80 font-mono">
                        {fmtDurationMs(timing)}
                      </span>
                      <span className="hidden md:inline text-[10px] text-muted-foreground/80 font-mono">
                        {node.tokens ? `${(node.tokens / 1000).toFixed(1)}k tok` : "—"}
                      </span>
                      <span className="hidden lg:inline text-[10px] text-muted-foreground/80 font-mono">
                        {node.cost_usd ? `$${node.cost_usd.toFixed(4)}` : "—"}
                      </span>
                      <Badge variant="outline" className={`text-[9px] py-0 font-mono shrink-0 ${status.className}`}>
                        {t(status.labelKey, status.labelKey)}
                      </Badge>
                      <Eye className="h-3.5 w-3.5 text-muted-foreground/40 group-hover:text-primary transition-colors shrink-0" />
                    </button>
                  );
                })
              ) : (
                <div className="py-12 text-center text-muted-foreground/60 text-xs font-sans">
                  {running
                    ? t("pages.workflows.waitingNodeResults", "Waiting for node results…")
                    : t("pages.workflows.noTraceYet", "Run a workflow to see per-node trace.")}
                </div>
              )}
            </div>
          ) : (
            <pre className={`${consoleHeightClass} overflow-auto whitespace-pre-wrap p-4 text-foreground leading-relaxed scrollbar-thin select-text`}>
              {output || t("pages.workflows.noLogsYet", "Console waiting for workflow execution output…")}
            </pre>
          )}
        </CardContent>
      </Card>

      {/* Node Detail Execution Inspector Modal */}
      <Dialog open={Boolean(inspectedNode)} onOpenChange={(open) => !open && setInspectedNode(null)}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-hidden flex flex-col p-6">
          <DialogHeader className="border-b border-border/60 pb-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className="grid h-8 w-8 place-items-center rounded-xl bg-primary/10 text-primary border border-primary/30">
                  <Code2 className="h-4 w-4" />
                </div>
                <div>
                  <DialogTitle className="text-base font-bold text-foreground flex items-center gap-2">
                    {inspectedNode?.node_id}
                    {inspectedNode && (
                      <Badge
                        variant="outline"
                        className={`text-[10px] py-0 font-mono ${
                          (NODE_STATUS[inspectedNode.status] ?? { className: "" }).className
                        }`}
                      >
                        {t((NODE_STATUS[inspectedNode.status] ?? { labelKey: inspectedNode.status }).labelKey, inspectedNode.status)}
                      </Badge>
                    )}
                  </DialogTitle>
                  <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                    {t("pages.workflows.nodeInspectorDesc", "Inspect input payload, node output, executed tool calls, latency, and cost.")}
                  </DialogDescription>
                </div>
              </div>
            </div>
          </DialogHeader>

          {inspectedNode && (
            <div className="flex-1 overflow-y-auto space-y-4 py-3 pr-1 text-xs scrollbar-thin">
              {/* KPIs strip */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <div className="p-2.5 rounded-xl border border-border/60 bg-muted/20 flex flex-col">
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1 font-medium">
                    <Clock className="h-3 w-3 text-info" /> {t("pages.workflows.duration", "Duration")}
                  </span>
                  <span className="font-mono font-bold text-foreground mt-0.5">
                    {fmtDurationMs(
                      inspectedNode.timing_ms ??
                        (inspectedNode.finished_at && inspectedNode.started_at
                          ? new Date(inspectedNode.finished_at).getTime() - new Date(inspectedNode.started_at).getTime()
                          : undefined),
                    )}
                  </span>
                </div>

                <div className="p-2.5 rounded-xl border border-border/60 bg-muted/20 flex flex-col">
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1 font-medium">
                    <Zap className="h-3 w-3 text-amber-500" /> {t("pages.workflows.tokens", "Tokens")}
                  </span>
                  <span className="font-mono font-bold text-foreground mt-0.5">
                    {inspectedNode.tokens ? `${inspectedNode.tokens.toLocaleString()} tok` : "—"}
                  </span>
                </div>

                <div className="p-2.5 rounded-xl border border-border/60 bg-muted/20 flex flex-col">
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1 font-medium">
                    <DollarSign className="h-3 w-3 text-emerald-500" /> {t("pages.workflows.cost", "Cost")}
                  </span>
                  <span className="font-mono font-bold text-foreground mt-0.5">
                    {inspectedNode.cost_usd ? `$${inspectedNode.cost_usd.toFixed(4)}` : "—"}
                  </span>
                </div>

                <div className="p-2.5 rounded-xl border border-border/60 bg-muted/20 flex flex-col">
                  <span className="text-[10px] text-muted-foreground flex items-center gap-1 font-medium">
                    <Info className="h-3 w-3 text-primary" /> Attempt
                  </span>
                  <span className="font-mono font-bold text-foreground mt-0.5">
                    #{inspectedNode.attempt || 1}
                  </span>
                </div>
              </div>

              {/* Error Block if failed */}
              {inspectedNode.error && (
                <div className="p-3 rounded-xl border border-destructive/40 bg-destructive/10 text-destructive space-y-1">
                  <div className="flex items-center gap-1.5 font-bold">
                    <AlertCircle className="h-4 w-4" /> {t("pages.workflows.eventError", "Execution Error")}
                  </div>
                  <pre className="font-mono text-[11px] whitespace-pre-wrap leading-relaxed">
                    {inspectedNode.error}
                  </pre>
                </div>
              )}

              {/* Input section */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-foreground flex items-center gap-1.5">
                    <Terminal className="h-3.5 w-3.5 text-primary" />
                    {t("pages.workflows.nodeInput", "Input Payload")}
                  </span>
                  {inspectedNode.input && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 px-2 text-[10px] gap-1"
                      onClick={() => copyText(JSON.stringify(inspectedNode.input, null, 2), "Input payload")}
                    >
                      <Copy className="h-3 w-3" /> {t("common.copy", "Copy")}
                    </Button>
                  )}
                </div>
                <pre className="p-3 rounded-xl border border-border/60 bg-black/50 font-mono text-[11px] text-foreground/90 whitespace-pre-wrap max-h-48 overflow-y-auto scrollbar-thin select-text">
                  {inspectedNode.input
                    ? typeof inspectedNode.input === "string"
                      ? inspectedNode.input
                      : JSON.stringify(inspectedNode.input, null, 2)
                    : t("pages.workflows.noInputData", "No input payload available")}
                </pre>
              </div>

              {/* Output section */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-foreground flex items-center gap-1.5">
                    <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                    {t("pages.workflows.nodeOutput", "Output Payload")}
                  </span>
                  {inspectedNode.output && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 px-2 text-[10px] gap-1"
                      onClick={() =>
                        copyText(
                          typeof inspectedNode.output?.text === "string"
                            ? inspectedNode.output.text
                            : JSON.stringify(inspectedNode.output, null, 2),
                          "Output payload",
                        )
                      }
                    >
                      <Copy className="h-3 w-3" /> {t("common.copy", "Copy")}
                    </Button>
                  )}
                </div>
                <pre className="p-3 rounded-xl border border-border/60 bg-black/50 font-mono text-[11px] text-foreground/90 whitespace-pre-wrap max-h-64 overflow-y-auto scrollbar-thin select-text">
                  {typeof inspectedNode.output?.text === "string"
                    ? inspectedNode.output.text
                    : inspectedNode.output && Object.keys(inspectedNode.output).length > 0
                      ? JSON.stringify(inspectedNode.output, null, 2)
                      : t("pages.workflows.noOutputYet", "No output data produced yet")}
                </pre>
              </div>

              {/* Tool Calls section if present */}
              {Array.isArray((inspectedNode.output?.data as any)?.tool_calls) && (inspectedNode.output.data as any).tool_calls.length > 0 && (
                <div className="space-y-1.5">
                  <span className="font-bold text-foreground flex items-center gap-1.5">
                    <Wrench className="h-3.5 w-3.5 text-info" />
                    {t("pages.workflows.toolCalls", "Tool Calls")} ({(inspectedNode.output?.data as any)?.tool_calls?.length || 0})
                  </span>
                  <div className="space-y-2">
                    {(inspectedNode.output?.data as any)?.tool_calls?.map((tc: any, i: number) => (
                      <div key={i} className="p-2.5 rounded-lg border border-border/40 bg-muted/20 font-mono text-[11px] space-y-1">
                        <div className="font-semibold text-info flex items-center gap-1">
                          <Wrench className="h-3 w-3" /> {tc.name || tc.tool || `Tool #${i + 1}`}
                        </div>
                        {tc.args && (
                          <div className="text-[10px] text-muted-foreground">
                            Args: {typeof tc.args === "string" ? tc.args : JSON.stringify(tc.args)}
                          </div>
                        )}
                        {tc.result && (
                          <div className="text-[10px] text-foreground/80 bg-black/30 p-1.5 rounded">
                            Result: {typeof tc.result === "string" ? tc.result.slice(0, 300) : JSON.stringify(tc.result).slice(0, 300)}
                          </div>
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
    </>
  );
}
