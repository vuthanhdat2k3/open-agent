"use client";

import * as React from "react";
import { Activity, Clock3, Coins } from "lucide-react";
import { useTranslation } from "@/lib/i18n";
import type { WorkflowRunDetail } from "@/types";

interface RunKpiStripProps {
  run: WorkflowRunDetail | undefined;
}

const STATUS_STYLES: Record<string, { labelKey: string; className: string; pulse?: boolean }> = {
  running: { labelKey: "pages.workflows.statusRunning", className: "border-info/40 bg-info/10 text-info", pulse: true },
  queued: { labelKey: "pages.workflows.statusQueued", className: "border-muted/40 bg-muted/10 text-muted-foreground" },
  succeeded: { labelKey: "pages.workflows.statusSucceeded", className: "border-success/40 bg-success/10 text-success" },
  failed: { labelKey: "pages.workflows.statusFailed", className: "border-destructive/40 bg-destructive/10 text-destructive" },
  waiting_approval: { labelKey: "pages.workflows.statusWaitingApproval", className: "border-warning/40 bg-warning/10 text-warning" },
  diverged: { labelKey: "pages.workflows.statusDiverged", className: "border-warning/40 bg-warning/10 text-warning" },
  cancelled: { labelKey: "pages.workflows.statusCancelled", className: "border-muted/40 bg-muted/10 text-muted-foreground" },
};

// Backend datetimes are naive UTC (no "Z"/offset suffix) - the Date
// constructor would otherwise parse them as local time, throwing this off
// by the browser's UTC offset (e.g. +7h shows as an extra "420m").
function parseUtc(value: string): number {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`).getTime();
}

function fmtDuration(started?: string | null, finished?: string | null) {
  if (!started) return "—";
  const start = parseUtc(started);
  const end = finished ? parseUtc(finished) : Date.now();
  const ms = Math.max(0, end - start);
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60000);
  const s = Math.round((ms % 60000) / 1000);
  return `${m}m ${s}s`;
}

function totalTokens(run: WorkflowRunDetail | undefined) {
  if (!run?.nodes) return 0;
  return run.nodes.reduce((sum, n) => sum + (n.tokens ?? 0), 0);
}

function totalCost(run: WorkflowRunDetail | undefined) {
  if (!run?.nodes) return 0;
  return run.nodes.reduce((sum, n) => sum + (n.cost_usd ?? 0), 0);
}

export function RunKpiStrip({ run }: RunKpiStripProps) {
  const { t } = useTranslation();
  if (!run) return null;
  const style = STATUS_STYLES[run.status] ?? STATUS_STYLES.queued;
  const done = run.nodes?.filter((n) => n.status === "succeeded").length ?? 0;
  const total = run.nodes?.length ?? 0;
  const progress = total ? Math.round((done / total) * 100) : 0;

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-xl border border-border/80 bg-card/50 px-4 py-3 backdrop-blur-xl shadow-3d-card">
      <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${style.className}`}>
        {style.pulse && <span className="h-2 w-2 rounded-full bg-current animate-pulse" />}
        {t(style.labelKey, style.labelKey)}
      </span>
      <div className="flex min-w-[160px] flex-1 items-center gap-2.5">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted/40">
          <div
            className="h-full rounded-full bg-gradient-to-r from-info to-primary transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
          {t("pages.workflows.kpiNodes", "{done}/{total} nodes").replace("{done}", String(done)).replace("{total}", String(total))}
        </span>
      </div>
      <div className="flex items-center gap-5">
        <div className="flex items-center gap-1.5">
          <Clock3 className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          <span className="font-mono text-sm font-semibold tabular-nums">{fmtDuration(run.started_at, run.finished_at)}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Activity className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          <span className="font-mono text-sm font-semibold tabular-nums">
            {(totalTokens(run) / 1000).toFixed(1)}k
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <Coins className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          <span className="font-mono text-sm font-semibold tabular-nums">
            ${totalCost(run).toFixed(4)}
          </span>
        </div>
      </div>
    </div>
  );
}
