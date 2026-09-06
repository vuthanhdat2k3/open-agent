"use client";

import * as React from "react";
import Link from "next/link";
import {
  FileText,
  CheckCircle2,
  XCircle,
  Loader2,
  ExternalLink,
  Copy,
  Check,
  Search,
  X,
  Clock,
  Zap,
  RotateCw,
  Code2,
  LayoutGrid,
  List,
  TrendingUp,
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
} from "lucide-react";
import { toast } from "sonner";
import { useWorkflowRuns, useWorkflows } from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { useTranslation } from "@/lib/i18n";
import { formatVietnamDateTime } from "@/lib/datetime";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared";
import { MarkdownRenderer } from "@/components/markdown-renderer";
import { cn } from "@/lib/utils";
import type { WorkflowRunSummary } from "@/types";

function outputText(run: WorkflowRunSummary): string {
  const out = run.output;
  if (!out) return "";
  if (typeof out.text === "string") return out.text;
  if (typeof out.output === "string") return out.output;
  try {
    return JSON.stringify(out, null, 2);
  } catch {
    return "";
  }
}

function formatRunDuration(startedAt?: string | null, finishedAt?: string | null): string | null {
  if (!startedAt || !finishedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = new Date(finishedAt).getTime();
  if (isNaN(start) || isNaN(end) || end < start) return null;
  const diffMs = end - start;
  if (diffMs < 1000) return `${diffMs}ms`;
  const diffSecs = (diffMs / 1000).toFixed(1);
  if (Number(diffSecs) < 60) return `${diffSecs}s`;
  const mins = Math.floor(diffMs / 60000);
  const remSecs = Math.round((diffMs % 60000) / 1000);
  return `${mins}m ${remSecs}s`;
}

/**
 * StatusIndicator: Clean pastel background with saturated text
 * Succeeded: #ECFDF5 bg, #059669 text
 * Failed: #FEF2F2 bg, #DC2626 text
 */
function StatusIndicator({ status, compact = false }: { status: string; compact?: boolean }) {
  const { tx } = useTranslation();
  if (status === "succeeded") {
    return (
      <div
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full font-medium transition-colors",
          compact ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
          "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800"
        )}
      >
        <span className="relative flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60"></span>
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-600 dark:bg-emerald-400"></span>
        </span>
        <span>{tx("Thành công", "Succeeded")}</span>
      </div>
    );
  }
  if (status === "failed" || status === "diverged") {
    return (
      <div
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full font-medium transition-colors",
          compact ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
          "bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800"
        )}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-rose-600 dark:bg-rose-400 shrink-0" />
        <span>{tx("Thất bại", "Failed")}</span>
      </div>
    );
  }
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-medium transition-colors",
        compact ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
        "bg-sky-50 text-sky-700 border border-sky-200 dark:bg-sky-950/40 dark:text-sky-300 dark:border-sky-800"
      )}
    >
      <Loader2 className="h-3 w-3 animate-spin text-sky-600 dark:text-sky-400" />
      <span>{tx("Đang chạy", "Running")}</span>
    </div>
  );
}

/**
 * ReportDetailDialog: Clean high-contrast modal inspection dialog
 */
interface ReportDetailDialogProps {
  run: WorkflowRunSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function ReportDetailDialog({ run, open, onOpenChange }: ReportDetailDialogProps) {
  const { tx } = useTranslation();
  const [activeTab, setActiveTab] = React.useState<"markdown" | "raw">("markdown");
  const [copied, setCopied] = React.useState(false);
  const [copiedId, setCopiedId] = React.useState(false);

  if (!run) return null;

  const text = outputText(run);
  const duration = formatRunDuration(run.started_at, run.finished_at);
  const rawJson = (() => {
    try {
      return JSON.stringify(run.output, null, 2);
    } catch {
      return "";
    }
  })();

  const handleCopy = async (content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      toast.success(tx("Đã sao chép nội dung báo cáo", "Report content copied"));
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error(tx("Không thể sao chép", "Failed to copy"));
    }
  };

  const handleCopyId = async (id: string) => {
    try {
      await navigator.clipboard.writeText(id);
      setCopiedId(true);
      toast.success(tx("Đã sao chép Run ID", "Run ID copied"));
      setTimeout(() => setCopiedId(false), 2000);
    } catch {
      // Ignore
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl p-0 gap-0 overflow-hidden border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 shadow-2xl rounded-2xl text-gray-900 dark:text-zinc-100">
        {/* Header Bar */}
        <div className="border-b border-gray-200 dark:border-zinc-800 bg-gray-50/60 dark:bg-zinc-900/40 px-6 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4 pr-7">
            <div className="space-y-2 min-w-0">
              <div className="flex items-center gap-3">
                <div
                  className={cn(
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border transition-all",
                    run.status === "succeeded"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
                      : run.status === "failed"
                      ? "border-rose-200 bg-rose-50 text-rose-600 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-300"
                      : "border-sky-200 bg-sky-50 text-sky-600 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-300"
                  )}
                >
                  <FileText className="h-5 w-5" aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <DialogTitle className="text-base sm:text-lg font-semibold truncate text-gray-900 dark:text-zinc-100 tracking-tight">
                    {run.workflow_name}
                  </DialogTitle>
                  <button
                    type="button"
                    onClick={() => handleCopyId(run.id)}
                    className="group/id flex items-center gap-1.5 text-xs text-gray-500 dark:text-zinc-400 font-mono pt-0.5 hover:text-gray-900 dark:hover:text-zinc-200 transition-colors"
                    title={tx("Nhấp để sao chép Run ID", "Click to copy Run ID")}
                  >
                    <span className="text-gray-400 dark:text-zinc-500">ID:</span>
                    <span className="truncate max-w-[200px]">{run.id}</span>
                    {copiedId ? (
                      <Check className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
                    ) : (
                      <Copy className="h-3 w-3 opacity-0 group-hover/id:opacity-100 transition-opacity" />
                    )}
                  </button>
                </div>
              </div>

              {/* Metadata Badges */}
              <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
                <StatusIndicator status={run.status} compact />
                <div className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-gray-600 dark:text-zinc-400 text-xs">
                  <Clock className="h-3 w-3 text-gray-400 dark:text-zinc-500" />
                  <span>{formatVietnamDateTime(run.finished_at || run.started_at)}</span>
                </div>
                {duration && (
                  <div className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 text-gray-700 dark:text-zinc-300 text-xs">
                    <Zap className="h-3 w-3 text-amber-500 dark:text-amber-400" />
                    <span>{duration}</span>
                  </div>
                )}
                {run.trigger_type && (
                  <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-gray-200 dark:border-zinc-800 bg-gray-100 dark:bg-zinc-900 text-gray-600 dark:text-zinc-400 text-[11px] font-mono">
                    <span>{run.trigger_type}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Header Action Buttons */}
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 text-xs h-8 bg-white dark:bg-zinc-900 border-gray-200 dark:border-zinc-800 text-gray-700 dark:text-zinc-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-zinc-800 shadow-xs"
                onClick={() => void handleCopy(activeTab === "markdown" ? text : rawJson)}
              >
                {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                <span>{copied ? tx("Đã chép", "Copied") : tx("Sao chép", "Copy")}</span>
              </Button>
              <Link href={`/workflows?edit=${run.workflow_id}&run=${run.id}`}>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5 text-xs h-8 bg-white dark:bg-zinc-900 border-gray-200 dark:border-zinc-800 text-gray-700 dark:text-zinc-300 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-zinc-800 shadow-xs"
                >
                  <span>{tx("Workflow Canvas", "Workflow Canvas")}</span>
                  <ArrowUpRight className="h-3.5 w-3.5" />
                </Button>
              </Link>
            </div>
          </div>

          {/* Segmented View Switcher */}
          {text && rawJson && (
            <div className="flex items-center gap-1 mt-4 pt-3 border-t border-gray-200 dark:border-zinc-800">
              <button
                type="button"
                onClick={() => setActiveTab("markdown")}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-all",
                  activeTab === "markdown"
                    ? "bg-white dark:bg-zinc-800 text-gray-900 dark:text-zinc-100 shadow-xs border border-gray-200 dark:border-zinc-700"
                    : "text-gray-600 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-900"
                )}
              >
                <FileText className="h-3.5 w-3.5" />
                <span>{tx("Bản báo cáo (Markdown)", "Report (Markdown)")}</span>
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("raw")}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-all",
                  activeTab === "raw"
                    ? "bg-white dark:bg-zinc-800 text-gray-900 dark:text-zinc-100 shadow-xs border border-gray-200 dark:border-zinc-700"
                    : "text-gray-600 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-900"
                )}
              >
                <Code2 className="h-3.5 w-3.5" />
                <span>{tx("Dữ liệu thô (JSON)", "Raw JSON")}</span>
              </button>
            </div>
          )}
        </div>

        {/* Modal Body */}
        <div className="max-h-[64vh] overflow-y-auto p-6 space-y-4 bg-white dark:bg-zinc-950">
          {run.status === "failed" && run.error && (
            <div className="rounded-xl border border-rose-200 bg-rose-50/80 dark:border-rose-900 dark:bg-rose-950/30 p-4 text-sm text-rose-800 dark:text-rose-300 shadow-xs space-y-1.5">
              <div className="flex items-center gap-2 font-semibold text-rose-900 dark:text-rose-200">
                <AlertTriangle className="h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" />
                <span>{tx("Workflow thực thi thất bại", "Workflow execution failed")}</span>
              </div>
              <p className="font-mono text-xs whitespace-pre-wrap pl-6 text-rose-700 dark:text-rose-300/90 select-all leading-relaxed">
                {run.error}
              </p>
            </div>
          )}

          {activeTab === "markdown" ? (
            text ? (
              <div className="rounded-xl border border-gray-200 dark:border-zinc-800 bg-gray-50/40 dark:bg-zinc-900/30 p-5 sm:p-6 text-gray-800 dark:text-zinc-200 leading-relaxed">
                <MarkdownRenderer content={text} />
              </div>
            ) : (
              <div className="py-16 text-center text-sm text-gray-500 dark:text-zinc-500 italic">
                {tx(
                  "Chưa có nội dung báo cáo nào được sinh ra cho lần chạy này.",
                  "No report output was generated for this run."
                )}
              </div>
            )
          ) : (
            <pre className="rounded-xl border border-gray-200 dark:border-zinc-800 bg-gray-50/80 dark:bg-zinc-900 p-4 text-xs font-mono text-gray-800 dark:text-zinc-200 overflow-x-auto select-all max-h-[55vh] leading-relaxed">
              {rawJson || "{}"}
            </pre>
          )}
        </div>

        {/* Modal Footer */}
        <div className="border-t border-gray-200 dark:border-zinc-800 bg-gray-50/60 dark:bg-zinc-900/40 px-6 py-3.5 flex items-center justify-between text-xs text-gray-500 dark:text-zinc-400">
          <div className="flex items-center gap-2 font-mono">
            <span className="text-gray-400 dark:text-zinc-500">{tx("Run:", "Run:")}</span>
            <code className="text-gray-700 dark:text-zinc-300 bg-gray-100 dark:bg-zinc-900 px-1.5 py-0.5 rounded border border-gray-200 dark:border-zinc-800 select-all">
              {run.id}
            </code>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onOpenChange(false)}
            className="text-xs text-gray-600 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-zinc-800 h-8"
          >
            {tx("Đóng", "Close")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/**
 * ReportCard: Clean, lightweight modern SaaS card
 * Layout:
 * ┌────────────────────────────┐
 * │ 📄 Daily Tech News   ●     │
 * │                            │
 * │ Bản tin Công nghệ mới...   │
 * │                            │
 * │ ⚡ 2m 49s · 21:02          │
 * │                            │
 * │ View details →             │
 * └────────────────────────────┘
 */
function ReportCard({
  run,
  onSelectReport,
}: {
  run: WorkflowRunSummary;
  onSelectReport: (run: WorkflowRunSummary) => void;
}) {
  const { tx } = useTranslation();
  const [copied, setCopied] = React.useState(false);
  const text = outputText(run);
  const duration = formatRunDuration(run.started_at, run.finished_at);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      toast.success(tx("Đã sao chép nội dung báo cáo", "Report content copied"));
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error(tx("Không thể sao chép", "Failed to copy"));
    }
  };

  const snippet = React.useMemo(() => {
    if (!text) return "";
    return text.replace(/[#*`_\[\]()]/g, "").trim().slice(0, 220);
  }, [text]);

  const isFailed = run.status === "failed" || run.status === "diverged";

  return (
    <div
      onClick={() => onSelectReport(run)}
      className="group flex flex-col justify-between rounded-xl p-4 sm:p-5 transition-all duration-150 cursor-pointer select-none bg-white dark:bg-card border border-gray-200/90 dark:border-border hover:border-gray-300 dark:hover:border-zinc-700 shadow-xs hover:shadow-md"
    >
      <div className="space-y-3">
        {/* Row 1: Icon + Title + Status Dot/Badge */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-100 dark:bg-zinc-800 text-gray-600 dark:text-zinc-300 border border-gray-200/60 dark:border-zinc-700/60">
              <FileText className="h-4 w-4" aria-hidden="true" />
            </div>
            <h3
              className="truncate text-sm font-semibold text-gray-900 dark:text-foreground group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors"
              title={run.workflow_name}
            >
              {run.workflow_name}
            </h3>
          </div>
          <StatusIndicator status={run.status} compact />
        </div>

        {/* Row 2: Description Snippet (Clear typography: #4B5563 on light) */}
        {isFailed && run.error ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50/70 dark:border-rose-900/50 dark:bg-rose-950/20 p-2.5 text-xs text-rose-700 dark:text-rose-300 line-clamp-3 font-mono leading-relaxed">
            {run.error}
          </div>
        ) : snippet ? (
          <p className="text-xs text-gray-600 dark:text-gray-300 line-clamp-3 leading-relaxed min-h-[54px]">
            {snippet}
          </p>
        ) : (
          <p className="text-xs italic text-gray-400 dark:text-zinc-500 py-3">
            {tx("Chưa có nội dung kết quả.", "No output yet.")}
          </p>
        )}

        {/* Row 3: Meta info (duration, trigger, timestamp) */}
        <div className="flex flex-wrap items-center gap-2 pt-1 text-[11px] text-gray-500 dark:text-muted-foreground">
          {duration && (
            <span className="inline-flex items-center gap-1 font-medium text-gray-700 dark:text-zinc-300 bg-gray-100 dark:bg-zinc-800 px-2 py-0.5 rounded-md">
              <Zap className="h-3 w-3 text-amber-500 dark:text-amber-400" />
              <span>{duration}</span>
            </span>
          )}
          {run.trigger_type && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-md border border-gray-200 dark:border-zinc-800 bg-gray-50 dark:bg-zinc-900 text-gray-600 dark:text-zinc-400 font-mono text-[10.5px]">
              {run.trigger_type}
            </span>
          )}
          <span className="text-gray-400 dark:text-zinc-500">
            {formatVietnamDateTime(run.finished_at || run.started_at)}
          </span>
        </div>
      </div>

      {/* Row 4: Clean Footer link + quick actions */}
      <div
        className="flex items-center justify-between gap-2 pt-3 mt-4 border-t border-gray-100 dark:border-border"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={() => onSelectReport(run)}
          className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 group/link transition-colors"
        >
          <span>{tx("Xem chi tiết", "View details")}</span>
          <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover/link:translate-x-0.5" />
        </button>

        <div className="flex items-center gap-1">
          <Link href={`/workflows?edit=${run.workflow_id}&run=${run.id}`}>
            <button
              type="button"
              className="p-1.5 rounded-md text-gray-400 hover:text-gray-700 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
              title={tx("Mở workflow canvas", "Open workflow canvas")}
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </button>
          </Link>

          {text && (
            <button
              type="button"
              className="p-1.5 rounded-md text-gray-400 hover:text-gray-700 dark:hover:text-zinc-200 hover:bg-gray-100 dark:hover:bg-zinc-800 transition-colors"
              onClick={handleCopy}
              title={tx("Sao chép nội dung", "Copy content")}
            >
              {copied ? (
                <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * ReportRow: Clean modern table row view
 */
function ReportRow({
  run,
  onSelectReport,
}: {
  run: WorkflowRunSummary;
  onSelectReport: (run: WorkflowRunSummary) => void;
}) {
  const { tx } = useTranslation();
  const text = outputText(run);
  const duration = formatRunDuration(run.started_at, run.finished_at);
  const snippet = text ? text.replace(/[#*`_\[\]()]/g, "").trim().slice(0, 120) : "";

  return (
    <div
      onClick={() => onSelectReport(run)}
      className="group flex items-center justify-between gap-4 px-4 py-3.5 border-b border-gray-100 dark:border-border hover:bg-gray-50/80 dark:hover:bg-zinc-900/60 cursor-pointer transition-colors bg-white dark:bg-card"
    >
      <div className="flex items-center gap-3 min-w-[240px] max-w-[320px]">
        <StatusIndicator status={run.status} compact />
        <div className="min-w-0">
          <span className="truncate text-sm font-semibold text-gray-900 dark:text-foreground group-hover:text-indigo-600 dark:group-hover:text-indigo-400 block transition-colors">
            {run.workflow_name}
          </span>
          <span className="text-[11px] font-mono text-gray-400 dark:text-zinc-500 truncate block">
            #{run.id.slice(0, 8)}
          </span>
        </div>
      </div>

      <div className="hidden md:flex flex-1 items-center min-w-0 text-xs text-gray-600 dark:text-gray-300">
        <span className="truncate">{run.status === "failed" ? run.error : snippet || "—"}</span>
      </div>

      <div className="flex items-center gap-4 shrink-0 text-xs text-gray-500 dark:text-muted-foreground">
        {duration && (
          <span className="hidden sm:inline-flex items-center gap-1 font-medium text-gray-700 dark:text-zinc-300 bg-gray-100 dark:bg-zinc-800 px-2 py-0.5 rounded-md">
            <Zap className="h-3 w-3 text-amber-500" />
            {duration}
          </span>
        )}
        <span className="text-[11px] text-gray-400 dark:text-zinc-500 whitespace-nowrap">
          {formatVietnamDateTime(run.finished_at || run.started_at)}
        </span>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onSelectReport(run);
          }}
          className="p-1.5 rounded-md text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 transition-colors"
        >
          <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

export default function ReportsPage() {
  const { tx } = useTranslation();
  const [searchQuery, setSearchQuery] = React.useState("");
  const [workflowId, setWorkflowId] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState<"all" | "succeeded" | "failed" | "running">("all");
  const [viewMode, setViewMode] = React.useState<"grid" | "list">("grid");
  const [selectedRun, setSelectedRun] = React.useState<WorkflowRunSummary | null>(null);

  const workflowsQuery = useWorkflows({ all: true });
  const runsQuery = useWorkflowRuns({
    workflowId: workflowId || undefined,
    status: statusFilter === "all" ? undefined : statusFilter,
    limit: 60,
  });

  const runs = runsQuery.data || [];

  // Metrics computation for KPI strip
  const stats = React.useMemo(() => {
    const total = runs.length;
    const succeeded = runs.filter((r) => r.status === "succeeded").length;
    const failed = runs.filter((r) => r.status === "failed" || r.status === "diverged").length;
    const running = runs.filter((r) => r.status === "running").length;
    const successRate = total > 0 ? Math.round((succeeded / total) * 100) : 0;
    return { total, succeeded, failed, running, successRate };
  }, [runs]);

  // Search filter
  const filteredRuns = React.useMemo(() => {
    if (!runs) return [];
    if (!searchQuery.trim()) return runs;
    const q = searchQuery.toLowerCase().trim();
    return runs.filter((run) => {
      const nameMatch = run.workflow_name?.toLowerCase().includes(q);
      const idMatch = run.id?.toLowerCase().includes(q);
      const textMatch = outputText(run).toLowerCase().includes(q);
      const errorMatch = run.error?.toLowerCase().includes(q);
      return nameMatch || idMatch || textMatch || errorMatch;
    });
  }, [runs, searchQuery]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top Header */}
      <PageHeader
        icon={FileText}
        title={tx("Báo cáo", "Reports")}
        description={tx(
          "Nhật ký kết quả thực thi các workflow, cập nhật theo thời gian thực.",
          "Workflow execution log and reports, updated in real time."
        )}
      />

      {/* KPI Stats Strip: Clean white cards, bold numbers 28-32px, subtle borders */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* TOTAL RUNS */}
        <div className="rounded-xl border border-gray-200/90 dark:border-border bg-white dark:bg-card p-4 sm:p-5 shadow-xs flex items-center justify-between">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-muted-foreground">
              {tx("Tổng số lượt", "Total Runs")}
            </p>
            <p className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-foreground tracking-tight">
              {stats.total}
            </p>
          </div>
          <div className="h-10 w-10 rounded-xl bg-gray-100 dark:bg-zinc-800 flex items-center justify-center text-gray-600 dark:text-zinc-300">
            <FileText className="h-5 w-5" />
          </div>
        </div>

        {/* SUCCESS RATE */}
        <div className="rounded-xl border border-gray-200/90 dark:border-border bg-white dark:bg-card p-4 sm:p-5 shadow-xs flex items-center justify-between">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-muted-foreground">
              {tx("Tỷ lệ thành công", "Success Rate")}
            </p>
            <p className="text-2xl sm:text-3xl font-bold text-emerald-600 dark:text-emerald-400 tracking-tight">
              {stats.successRate}%
            </p>
          </div>
          <div className="h-10 w-10 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
            <TrendingUp className="h-5 w-5" />
          </div>
        </div>

        {/* SUCCEEDED */}
        <div className="rounded-xl border border-gray-200/90 dark:border-border bg-white dark:bg-card p-4 sm:p-5 shadow-xs flex items-center justify-between">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-muted-foreground">
              {tx("Thành công", "Succeeded")}
            </p>
            <p className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-foreground tracking-tight">
              {stats.succeeded}
            </p>
          </div>
          <div className="h-10 w-10 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
            <CheckCircle2 className="h-5 w-5" />
          </div>
        </div>

        {/* FAILED */}
        <div className="rounded-xl border border-gray-200/90 dark:border-border bg-white dark:bg-card p-4 sm:p-5 shadow-xs flex items-center justify-between">
          <div className="space-y-1">
            <p className="text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-muted-foreground">
              {tx("Thất bại", "Failed")}
            </p>
            <p className="text-2xl sm:text-3xl font-bold text-rose-600 dark:text-rose-400 tracking-tight">
              {stats.failed}
            </p>
          </div>
          <div className="h-10 w-10 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 flex items-center justify-center text-rose-600 dark:text-rose-400">
            <AlertTriangle className="h-5 w-5" />
          </div>
        </div>
      </div>

      {/* Modern Filter Toolbar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 p-3 rounded-xl border border-gray-200/90 dark:border-border bg-white dark:bg-card shadow-xs">
        {/* Left: Search and Workflow Filter */}
        <div className="flex flex-wrap items-center gap-2.5 flex-1">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 dark:text-zinc-500" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={tx("Tìm theo tên, ID hoặc từ khóa...", "Search by name, ID or text...")}
              className="pl-9 pr-8 h-9 text-xs bg-gray-50/70 dark:bg-zinc-900 border-gray-200 dark:border-zinc-800 text-gray-900 dark:text-zinc-100 placeholder:text-gray-400 dark:placeholder:text-zinc-500 focus-visible:ring-indigo-500"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-zinc-300"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <Select
            value={workflowId}
            onChange={(e) => setWorkflowId(e.target.value)}
            className="w-48 h-9 text-xs bg-gray-50/70 dark:bg-zinc-900 border-gray-200 dark:border-zinc-800 text-gray-900 dark:text-zinc-100"
          >
            <option value="">{tx("Tất cả workflow", "All workflows")}</option>
            {workflowsQuery.data?.map((wf) => (
              <option key={wf.id} value={wf.id}>
                {wf.name}
              </option>
            ))}
          </Select>

          {/* Filter status pills */}
          <div className="hidden sm:flex items-center gap-1 bg-gray-100 dark:bg-zinc-900 p-0.5 rounded-lg border border-gray-200/80 dark:border-zinc-800 text-xs">
            <button
              type="button"
              onClick={() => setStatusFilter("all")}
              className={cn(
                "px-2.5 py-1 rounded-md transition-colors text-[11px] font-medium",
                statusFilter === "all"
                  ? "bg-white text-gray-900 shadow-xs dark:bg-zinc-800 dark:text-white"
                  : "text-gray-600 hover:text-gray-900 dark:text-zinc-400 dark:hover:text-zinc-200"
              )}
            >
              {tx("Tất cả", "All")} ({stats.total})
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter("succeeded")}
              className={cn(
                "px-2.5 py-1 rounded-md transition-colors text-[11px] font-medium",
                statusFilter === "succeeded"
                  ? "bg-emerald-50 text-emerald-700 border border-emerald-200 shadow-xs dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800"
                  : "text-gray-600 hover:text-gray-900 dark:text-zinc-400 dark:hover:text-zinc-200"
              )}
            >
              {tx("Thành công", "Success")} ({stats.succeeded})
            </button>
            <button
              type="button"
              onClick={() => setStatusFilter("failed")}
              className={cn(
                "px-2.5 py-1 rounded-md transition-colors text-[11px] font-medium",
                statusFilter === "failed"
                  ? "bg-rose-50 text-rose-700 border border-rose-200 shadow-xs dark:bg-rose-950/60 dark:text-rose-300 dark:border-rose-800"
                  : "text-gray-600 hover:text-gray-900 dark:text-zinc-400 dark:hover:text-zinc-200"
              )}
            >
              {tx("Thất bại", "Failed")} ({stats.failed})
            </button>
          </div>
        </div>

        {/* Right: View toggle and Refresh */}
        <div className="flex items-center justify-between md:justify-end gap-2">
          {/* View mode toggle */}
          <div className="flex items-center bg-gray-100 dark:bg-zinc-900 p-0.5 rounded-lg border border-gray-200/80 dark:border-zinc-800">
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              className={cn(
                "p-1.5 rounded-md transition-colors",
                viewMode === "grid"
                  ? "bg-white text-gray-900 shadow-xs dark:bg-zinc-800 dark:text-white"
                  : "text-gray-500 hover:text-gray-900 dark:text-zinc-400 dark:hover:text-zinc-200"
              )}
              title={tx("Chế độ thẻ lưới", "Grid view")}
            >
              <LayoutGrid className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setViewMode("list")}
              className={cn(
                "p-1.5 rounded-md transition-colors",
                viewMode === "list"
                  ? "bg-white text-gray-900 shadow-xs dark:bg-zinc-800 dark:text-white"
                  : "text-gray-500 hover:text-gray-900 dark:text-zinc-400 dark:hover:text-zinc-200"
              )}
              title={tx("Chế độ danh sách", "List view")}
            >
              <List className="h-3.5 w-3.5" />
            </button>
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => runsQuery.refetch()}
            disabled={runsQuery.isFetching}
            className="h-9 w-9 p-0 bg-white dark:bg-zinc-900 border-gray-200 dark:border-zinc-800 text-gray-600 dark:text-zinc-400 hover:text-gray-900 dark:hover:text-white"
            title={tx("Làm mới danh sách", "Refresh")}
          >
            <RotateCw className={cn("h-3.5 w-3.5", runsQuery.isFetching && "animate-spin text-indigo-600")} />
          </Button>
        </div>
      </div>

      {/* Main Content Area */}
      {runsQuery.isLoading ? (
        <LoadingSkeleton variant="grid" />
      ) : runsQuery.isError ? (
        <ErrorState onRetry={() => runsQuery.refetch()} />
      ) : runs.length === 0 ? (
        <EmptyState
          icon={FileText}
          title={tx("Chưa có báo cáo nào", "No reports yet")}
          description={tx(
            "Kết quả các lần chạy workflow sẽ xuất hiện tại đây khi được thực thi.",
            "Workflow run results will show up here once executed."
          )}
        />
      ) : filteredRuns.length === 0 ? (
        <div className="py-16 text-center space-y-3 bg-white dark:bg-card rounded-2xl border border-dashed border-gray-300 dark:border-zinc-800">
          <Search className="h-8 w-8 text-gray-400 dark:text-zinc-500 mx-auto" />
          <p className="text-sm text-gray-600 dark:text-zinc-400">
            {tx("Không tìm thấy báo cáo nào khớp với bộ lọc.", "No reports match the current filters.")}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setSearchQuery("");
              setWorkflowId("");
              setStatusFilter("all");
            }}
            className="text-xs bg-white dark:bg-zinc-900 border-gray-200 dark:border-zinc-800 text-gray-700 dark:text-zinc-300"
          >
            {tx("Xóa bộ lọc", "Clear filters")}
          </Button>
        </div>
      ) : viewMode === "grid" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 sm:gap-5">
          {filteredRuns.map((run) => (
            <ReportCard key={run.id} run={run} onSelectReport={(r) => setSelectedRun(r)} />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200/90 dark:border-border bg-white dark:bg-card overflow-hidden shadow-xs">
          {filteredRuns.map((run) => (
            <ReportRow key={run.id} run={run} onSelectReport={(r) => setSelectedRun(r)} />
          ))}
        </div>
      )}

      {/* Detail Inspection Modal Dialog */}
      <ReportDetailDialog
        run={selectedRun}
        open={Boolean(selectedRun)}
        onOpenChange={(open) => {
          if (!open) setSelectedRun(null);
        }}
      />
    </div>
  );
}
