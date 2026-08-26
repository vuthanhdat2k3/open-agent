"use client";

import * as React from "react";
import {
  Activity,
  Bot,
  CheckCircle2,
  Coins,
  Database,
  Gauge,
  HardDrive,
  Lock,
  Save,
  ShieldAlert,
  ShieldCheck,
  Workflow,
  Zap,
} from "lucide-react";
import { toast } from "sonner";
import {
  useMe,
  useCurrentRole,
  useOrganizationQuota,
  useQuotaUsage,
  useUpdateOrganizationQuota,
} from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { ErrorState, LoadingSkeleton } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getActiveOrgId } from "@/lib/auth";

type FormState = {
  requests_per_minute: string;
  agent_runs_per_minute: string;
  max_concurrent_runs: string;
  monthly_cost_usd: string;
  max_agents: string;
  max_workflows: string;
  max_storage_mb: string;
  enforcement_mode: "enforce" | "observe";
};

const EMPTY_FORM: FormState = {
  requests_per_minute: "",
  agent_runs_per_minute: "",
  max_concurrent_runs: "",
  monthly_cost_usd: "",
  max_agents: "",
  max_workflows: "",
  max_storage_mb: "",
  enforcement_mode: "enforce",
};

function optionalNumber(value: string) {
  return value === "" ? null : Number(value);
}

export default function QuotasAndBudgetsPage() {
  const me = useMe();
  const role = useCurrentRole();
  const isAdmin = role === "admin" || role === "platform_admin";
  const activeOrgId = getActiveOrgId();
  const orgId = activeOrgId || me.data?.memberships?.[0]?.org_id;
  const quota = useOrganizationQuota(isAdmin ? orgId : undefined);
  const usage = useQuotaUsage(orgId);
  const updateQuota = useUpdateOrganizationQuota(orgId);
  const [form, setForm] = React.useState<FormState>(EMPTY_FORM);

  React.useEffect(() => {
    if (!quota.data) return;
    setForm({
      requests_per_minute: String(quota.data.requests_per_minute ?? 60),
      agent_runs_per_minute: String(quota.data.agent_runs_per_minute ?? 15),
      max_concurrent_runs: String(quota.data.max_concurrent_runs ?? 5),
      monthly_cost_usd: String(quota.data.monthly_cost_usd ?? 100),
      max_agents: quota.data.max_agents?.toString() ?? "",
      max_workflows: quota.data.max_workflows?.toString() ?? "",
      max_storage_mb: quota.data.max_storage_bytes
        ? String(Math.round(quota.data.max_storage_bytes / (1024 * 1024)))
        : "",
      enforcement_mode: quota.data.enforcement_mode ?? "enforce",
    });
  }, [quota.data]);

  const setField = (field: keyof FormState, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const save = async () => {
    try {
      const storageBytes = form.max_storage_mb.trim()
        ? Number(form.max_storage_mb) * 1024 * 1024
        : null;

      await updateQuota.mutateAsync({
        requests_per_minute: Number(form.requests_per_minute),
        agent_runs_per_minute: Number(form.agent_runs_per_minute),
        max_concurrent_runs: Number(form.max_concurrent_runs),
        monthly_cost_usd: Number(form.monthly_cost_usd),
        max_agents: optionalNumber(form.max_agents),
        max_workflows: optionalNumber(form.max_workflows),
        max_storage_bytes: storageBytes,
        enforcement_mode: form.enforcement_mode,
      });
      toast.success("Quota & budget policy saved successfully");
    } catch (error: any) {
      toast.error(error.message || "Failed to update quota policy");
    }
  };

  if ((isAdmin && quota.isError) || usage.isError) {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={Gauge}
          title="Quotas & Budgets"
          description="Admission and spend controls for your active organization."
        />
        <ErrorState
          title="Unable to load quota data"
          description="Quota policy or live usage telemetry could not be loaded."
          onRetry={() => {
            if (isAdmin) void quota.refetch();
            void usage.refetch();
          }}
        />
      </div>
    );
  }

  const monthlyCost = usage.data?.monthly_cost_usd ?? 0;
  const costLimit = usage.data?.monthly_cost_limit_usd ?? 100;
  const spendRatio = costLimit > 0 ? (monthlyCost / costLimit) * 100 : 0;
  const storageMB = ((usage.data?.storage_bytes ?? 0) / (1024 * 1024)).toFixed(1);
  const storageLimitMB = usage.data?.storage_limit_bytes
    ? `${(usage.data.storage_limit_bytes / (1024 * 1024)).toFixed(0)} MB`
    : "Unlimited";

  return (
    <div className="space-y-6">
      {/* 1. Page Header */}
      <PageHeader
        icon={Gauge}
        title="Quotas & Budgets"
        description={
          isAdmin
            ? `Configure monthly spend ceilings, admission rate limits, and track live consumption for ${usage.data?.month ?? "current billing cycle"}.`
            : `Your consumption and monthly quota metrics for ${usage.data?.month ?? "the current billing cycle"}.`
        }
        actions={
          isAdmin ? (
            <Button
              className="gap-2 font-semibold"
              onClick={save}
              loading={updateQuota.isPending}
            >
              <Save className="h-4 w-4" /> Save Policy
            </Button>
          ) : undefined
        }
      />

      {/* 2. Visual Budget Health Hero Banner */}
      <Card className="shadow-card border-border/80 p-5 bg-gradient-to-r from-card via-card to-primary/[0.03]">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Monthly Spend Status ({usage.data?.month || "Current Cycle"})
              </span>
              <Badge
                variant={spendRatio > 90 ? "destructive" : spendRatio > 70 ? "outline" : "default"}
                className="text-[10px] font-mono"
              >
                {spendRatio > 90 ? "Critical Usage (>90%)" : spendRatio > 70 ? "Warning (>70%)" : "Healthy (<70%)"}
              </Badge>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold font-mono text-foreground">${monthlyCost.toFixed(4)}</span>
              <span className="text-sm text-muted-foreground font-mono">/ ${costLimit.toFixed(2)} USD Cap</span>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <div className="text-right">
              <p className="text-xs font-medium text-muted-foreground">Budget Consumed</p>
              <p className="text-xl font-bold font-mono text-primary">{spendRatio.toFixed(1)}%</p>
            </div>
            <div className="h-10 w-px bg-border/80 hidden sm:block" />
            <div className="text-right">
              <p className="text-xs font-medium text-muted-foreground">Enforcement Mode</p>
              <p className="text-sm font-semibold capitalize font-mono text-foreground">
                {form.enforcement_mode}
              </p>
            </div>
          </div>
        </div>

        {/* Visual Progress Bar */}
        <div className="mt-4 h-2.5 w-full rounded-full bg-muted/60 overflow-hidden">
          <div
            className={`h-full transition-all duration-500 rounded-full ${
              spendRatio > 90 ? "bg-destructive" : spendRatio > 70 ? "bg-amber-500" : "bg-emerald-500"
            }`}
            style={{ width: `${Math.min(100, spendRatio)}%` }}
          />
        </div>
      </Card>

      {/* 3. Live Tenant Utilization Cards */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-foreground">Resource Utilization</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Card className="shadow-card border-border/80 p-4">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold uppercase tracking-wider">Monthly Spend</span>
              <Coins className="h-4 w-4 text-emerald-500" />
            </div>
            <p className="mt-2 text-xl font-bold font-mono text-foreground">${monthlyCost.toFixed(2)}</p>
            <p className="mt-0.5 text-[11px] font-mono text-muted-foreground">Limit: ${costLimit.toFixed(0)}</p>
          </Card>

          <Card className="shadow-card border-border/80 p-4">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold uppercase tracking-wider">Active Leases</span>
              <Zap className="h-4 w-4 text-sky-500" />
            </div>
            <p className="mt-2 text-xl font-bold font-mono text-foreground">{usage.data?.active_run_leases || 0}</p>
            <p className="mt-0.5 text-[11px] font-mono text-muted-foreground">
              Max: {usage.data?.concurrent_run_limit || 5} concurrent
            </p>
          </Card>

          <Card className="shadow-card border-border/80 p-4">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold uppercase tracking-wider">Agents</span>
              <Bot className="h-4 w-4 text-primary" />
            </div>
            <p className="mt-2 text-xl font-bold font-mono text-foreground">{usage.data?.agents || 0}</p>
            <p className="mt-0.5 text-[11px] font-mono text-muted-foreground">
              Cap: {usage.data?.agent_limit?.toLocaleString() ?? "Unlimited"}
            </p>
          </Card>

          <Card className="shadow-card border-border/80 p-4">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold uppercase tracking-wider">Workflows</span>
              <Workflow className="h-4 w-4 text-primary" />
            </div>
            <p className="mt-2 text-xl font-bold font-mono text-foreground">{usage.data?.workflows || 0}</p>
            <p className="mt-0.5 text-[11px] font-mono text-muted-foreground">
              Cap: {usage.data?.workflow_limit?.toLocaleString() ?? "Unlimited"}
            </p>
          </Card>

          <Card className="shadow-card border-border/80 p-4">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold uppercase tracking-wider">Knowledge Storage</span>
              <HardDrive className="h-4 w-4 text-amber-500" />
            </div>
            <p className="mt-2 text-xl font-bold font-mono text-foreground">{storageMB} MB</p>
            <p className="mt-0.5 text-[11px] font-mono text-muted-foreground">Cap: {storageLimitMB}</p>
          </Card>
        </div>
      </section>

      {/* 4. Policy Configuration Form for Admins */}
      {isAdmin && (
        <Card className="shadow-card border-border/80 p-6 space-y-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border/60 pb-4">
            <div>
              <h2 className="text-base font-semibold text-foreground flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-primary" /> Admission & Spend Policy Settings
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Set thresholds for rate limits, runtime concurrency, and budget caps across all organization members.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <Label className="text-xs font-semibold text-muted-foreground uppercase">Mode:</Label>
              <Select
                className="w-36 text-xs"
                value={form.enforcement_mode}
                onChange={(e) => setField("enforcement_mode", e.target.value as any)}
              >
                <option value="enforce">Enforce (Hard Cap)</option>
                <option value="observe">Observe (Log Only)</option>
              </Select>
            </div>
          </div>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Requests Per Minute
              </Label>
              <Input
                type="number"
                min="1"
                value={form.requests_per_minute}
                onChange={(e) => setField("requests_per_minute", e.target.value)}
                placeholder="60"
                className="text-xs font-mono"
              />
              <p className="text-[11px] text-muted-foreground">API admission rate limit for all user requests.</p>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Agent Runs Per Minute
              </Label>
              <Input
                type="number"
                min="1"
                value={form.agent_runs_per_minute}
                onChange={(e) => setField("agent_runs_per_minute", e.target.value)}
                placeholder="15"
                className="text-xs font-mono"
              />
              <p className="text-[11px] text-muted-foreground">Maximum concurrent subagent invocations per minute.</p>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Max Concurrent Runs
              </Label>
              <Input
                type="number"
                min="1"
                value={form.max_concurrent_runs}
                onChange={(e) => setField("max_concurrent_runs", e.target.value)}
                placeholder="5"
                className="text-xs font-mono"
              />
              <p className="text-[11px] text-muted-foreground">Simultaneous execution worker leases.</p>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Monthly Spend Cap (USD $)
              </Label>
              <Input
                type="number"
                min="0"
                step="0.01"
                value={form.monthly_cost_usd}
                onChange={(e) => setField("monthly_cost_usd", e.target.value)}
                placeholder="100.00"
                className="text-xs font-mono font-semibold"
              />
              <p className="text-[11px] text-muted-foreground">Hard stop threshold for model token burn.</p>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Knowledge Storage Cap (MB)
              </Label>
              <Input
                type="number"
                min="0"
                value={form.max_storage_mb}
                onChange={(e) => setField("max_storage_mb", e.target.value)}
                placeholder="Leave empty for Unlimited"
                className="text-xs font-mono"
              />
              <p className="text-[11px] text-muted-foreground">Total vector & file storage ceiling in MB.</p>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Max Registered Agents
              </Label>
              <Input
                type="number"
                min="0"
                value={form.max_agents}
                onChange={(e) => setField("max_agents", e.target.value)}
                placeholder="Leave empty for Unlimited"
                className="text-xs font-mono"
              />
              <p className="text-[11px] text-muted-foreground">Limit total configured agent personas in studio.</p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
