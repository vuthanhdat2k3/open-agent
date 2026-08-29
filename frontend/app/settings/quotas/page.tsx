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
import { useTranslation } from "@/lib/i18n";
import { ErrorState, LoadingSkeleton } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getActiveOrgId } from "@/lib/auth";
import { isAdminRole } from "@/lib/roles";

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
  const { t, dict, locale, tx } = useTranslation();
  const me = useMe();
  const role = useCurrentRole();
  const isAdmin = isAdminRole(role);
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
      toast.success(tx("Đã lưu chính sách ngân sách & hạn mức thành công", "Quota & budget policy saved successfully"));
    } catch (error: any) {
      toast.error(error.message || (tx("Không thể cập nhật chính sách hạn mức", "Failed to update quota policy")));
    }
  };

  if ((isAdmin && quota.isError) || usage.isError) {
    return (
      <div className="space-y-6">
        <PageHeader
          icon={Gauge}
          title={tx("Hạn mức & Ngân sách", "Quotas & Budgets")}
          description={tx("Kiểm soát truy cập và chi tiêu cho tổ chức hiện tại của bạn.", "Admission and spend controls for your active organization.")}
        />
        <ErrorState
          title={tx("Không thể tải dữ liệu hạn mức", "Unable to load quota data")}
          description={tx("Không thể tải chính sách hạn mức hoặc dữ liệu sử dụng trực tiếp.", "Quota policy or live usage telemetry could not be loaded.")}
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
    : (tx("Không giới hạn", "Unlimited"));

  return (
    <div className="space-y-6">
      {/* 1. Page Header */}
      <PageHeader
        icon={Gauge}
        title={dict.pages.quotas.title}
        description={
          isAdmin
            ? (tx(`Định cấu hình giới hạn ngân sách hàng tháng, giới hạn tốc độ tiếp nhận và theo dõi việc sử dụng cho ${usage.data?.month ?? "chu kỳ hiện tại"}.`, `Configure monthly budget limits, admission rate limits, and track usage for ${usage.data?.month ?? "current cycle"}.`))
            : (tx(`Theo dõi mức tiêu thụ và số liệu hạn mức cho ${usage.data?.month ?? "chu kỳ hiện tại"}.`, `Track consumption and quota metrics for ${usage.data?.month ?? "the current cycle"}.`))
        }
        actions={
          isAdmin ? (
            <Button
              className="gap-2 font-semibold"
              onClick={save}
              loading={updateQuota.isPending}
            >
              <Save className="h-4 w-4" /> {tx("Lưu chính sách", "Save Policy")}
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
                {tx(`Trạng thái chi tiêu hàng tháng (${usage.data?.month || "Chu kỳ hiện tại"})`, `Monthly Spend Status (${usage.data?.month || "Current Cycle"})`)}
              </span>
              <Badge
                variant={spendRatio > 90 ? "destructive" : spendRatio > 70 ? "outline" : "default"}
                className="text-[10px] font-mono"
              >
                {spendRatio > 90 ? (tx("Mức sử dụng nghiêm trọng (>90%)", "Critical Usage (>90%)")) : spendRatio > 70 ? (tx("Cảnh báo (>70%)", "Warning (>70%)")) : (tx("Bình thường (<70%)", "Healthy (<70%)"))}
              </Badge>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-3xl font-bold font-mono text-foreground">${monthlyCost.toFixed(4)}</span>
              <span className="text-sm text-muted-foreground font-mono">/ ${costLimit.toFixed(2)} {tx("USD", "USD")}{tx("Tối đa", "Cap")}</span>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <div className="text-right">
              <p className="text-xs font-medium text-muted-foreground">{tx("Ngân sách đã tiêu thụ", "Budget Consumed")}</p>
              <p className="text-xl font-bold font-mono text-primary">{spendRatio.toFixed(1)}%</p>
            </div>
            <div className="h-10 w-px bg-border/80 hidden sm:block" />
            <div className="text-right">
              <p className="text-xs font-medium text-muted-foreground">{tx("Chế độ thực thi", "Enforcement Mode")}</p>
              <p className="text-sm font-semibold capitalize font-mono text-foreground">
                {form.enforcement_mode === "enforce" ? (tx("Thực thi", "Enforce")) : (tx("Quan sát", "Observe"))}
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
        <h2 className="text-sm font-semibold text-foreground">{tx("Sử dụng tài nguyên", "Resource Utilization")}</h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Card className="shadow-card border-border/80 p-4">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold uppercase tracking-wider">{tx("Chi tiêu hàng tháng", "Monthly Spend")}</span>
              <Coins className="h-4 w-4 text-emerald-500" />
            </div>
            <p className="mt-2 text-xl font-bold font-mono text-foreground">${monthlyCost.toFixed(2)}</p>
            <p className="mt-0.5 text-[11px] font-mono text-muted-foreground">{tx("Giới hạn", "Limit")}: ${costLimit.toFixed(0)}</p>
          </Card>

          <Card className="shadow-card border-border/80 p-4">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold uppercase tracking-wider">{tx("Phiên hoạt động", "Active Leases")}</span>
              <Zap className="h-4 w-4 text-sky-500" />
            </div>
            <p className="mt-2 text-xl font-bold font-mono text-foreground">{usage.data?.active_run_leases || 0}</p>
            <p className="mt-0.5 text-[11px] font-mono text-muted-foreground">
              {tx("Tối đa", "Max")}: {usage.data?.concurrent_run_limit || 5} {tx("đồng thời", "concurrent")}
            </p>
          </Card>

          <Card className="shadow-card border-border/80 p-4">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold uppercase tracking-wider">{tx("Tác nhân", "Agents")}</span>
              <Bot className="h-4 w-4 text-primary" />
            </div>
            <p className="mt-2 text-xl font-bold font-mono text-foreground">{usage.data?.agents || 0}</p>
            <p className="mt-0.5 text-[11px] font-mono text-muted-foreground">
              {tx("Tối đa", "Cap")}: {usage.data?.agent_limit?.toLocaleString() ?? (tx("Không giới hạn", "Unlimited"))}
            </p>
          </Card>

          <Card className="shadow-card border-border/80 p-4">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold uppercase tracking-wider">{tx("Luồng công việc", "Workflows")}</span>
              <Workflow className="h-4 w-4 text-primary" />
            </div>
            <p className="mt-2 text-xl font-bold font-mono text-foreground">{usage.data?.workflows || 0}</p>
            <p className="mt-0.5 text-[11px] font-mono text-muted-foreground">
              {tx("Tối đa", "Cap")}: {usage.data?.workflow_limit?.toLocaleString() ?? (tx("Không giới hạn", "Unlimited"))}
            </p>
          </Card>

          <Card className="shadow-card border-border/80 p-4">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-semibold uppercase tracking-wider">{tx("Lưu trữ kiến thức", "Knowledge Storage")}</span>
              <HardDrive className="h-4 w-4 text-amber-500" />
            </div>
            <p className="mt-2 text-xl font-bold font-mono text-foreground">{storageMB} {tx("MB", "MB")}</p>
            <p className="mt-0.5 text-[11px] font-mono text-muted-foreground">{tx("Tối đa", "Cap")}: {storageLimitMB}</p>
          </Card>
        </div>
      </section>

      {/* 4. Policy Configuration Form for Admins */}
      {isAdmin && (
        <Card className="shadow-card border-border/80 p-6 space-y-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border/60 pb-4">
            <div>
              <h2 className="text-base font-semibold text-foreground flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-primary" /> {tx("Cài đặt chính sách tiếp nhận & chi tiêu", "Admission & Spend Policy Settings")}
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {tx("Thiết lập ngưỡng cho giới hạn số lượng yêu cầu, số luồng chạy đồng thời và hạn mức ngân sách trên toàn bộ thành viên tổ chức.", "Set thresholds for rate limits, runtime concurrency, and budget caps across all organization members.")}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <Label className="text-xs font-semibold text-muted-foreground uppercase">{tx("Chế độ:", "Mode:")}</Label>
              <Select
                className="w-36 text-xs"
                value={form.enforcement_mode}
                onChange={(e) => setField("enforcement_mode", e.target.value as any)}
              >
                <option value="enforce">{tx("Thực thi (Giới hạn cứng)", "Enforce (Hard Cap)")}</option>
                <option value="observe">{tx("Quan sát (Chỉ ghi log)", "Observe (Log Only)")}</option>
              </Select>
            </div>
          </div>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {tx("Yêu cầu mỗi phút", "Requests Per Minute")}
              </Label>
              <Input
                type="number"
                min="1"
                value={form.requests_per_minute}
                onChange={(e) => setField("requests_per_minute", e.target.value)}
                placeholder="60"
                className="text-xs font-mono"
              />
              <p className="text-[11px] text-muted-foreground">{tx("Giới hạn tốc độ tiếp nhận API cho tất cả các yêu cầu của người dùng.", "API admission rate limit for all user requests.")}</p>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {tx("Số lần chạy tác nhân mỗi phút", "Agent Runs Per Minute")}
              </Label>
              <Input
                type="number"
                min="1"
                value={form.agent_runs_per_minute}
                onChange={(e) => setField("agent_runs_per_minute", e.target.value)}
                placeholder="15"
                className="text-xs font-mono"
              />
              <p className="text-[11px] text-muted-foreground">{tx("Số lần gọi tác nhân phụ đồng thời tối đa mỗi phút.", "Maximum concurrent subagent invocations per minute.")}</p>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {tx("Số lần chạy đồng thời tối đa", "Max Concurrent Runs")}
              </Label>
              <Input
                type="number"
                min="1"
                value={form.max_concurrent_runs}
                onChange={(e) => setField("max_concurrent_runs", e.target.value)}
                placeholder="5"
                className="text-xs font-mono"
              />
              <p className="text-[11px] text-muted-foreground">{tx("Số phiên thực thi đồng thời.", "Simultaneous execution worker leases.")}</p>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {tx("Hạn mức chi tiêu hàng tháng (USD $)", "Monthly Spend Cap (USD $)")}
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
              <p className="text-[11px] text-muted-foreground">{tx("Ngưỡng dừng cứng cho lượng token mô hình tiêu thụ.", "Hard stop threshold for model token burn.")}</p>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {tx("Giới hạn lưu trữ kiến thức (MB)", "Knowledge Storage Cap (MB)")}
              </Label>
              <Input
                type="number"
                min="0"
                value={form.max_storage_mb}
                onChange={(e) => setField("max_storage_mb", e.target.value)}
                placeholder={tx("Để trống cho Không giới hạn", "Leave empty for Unlimited")}
                className="text-xs font-mono"
              />
              <p className="text-[11px] text-muted-foreground">{tx("Tổng giới hạn lưu trữ file & vector tính bằng MB.", "Total vector & file storage ceiling in MB.")}</p>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {tx("Số tác nhân đăng ký tối đa", "Max Registered Agents")}
              </Label>
              <Input
                type="number"
                min="0"
                value={form.max_agents}
                onChange={(e) => setField("max_agents", e.target.value)}
                placeholder={tx("Để trống cho Không giới hạn", "Leave empty for Unlimited")}
                className="text-xs font-mono"
              />
              <p className="text-[11px] text-muted-foreground">{tx("Giới hạn tổng số persona tác nhân được định cấu hình trong studio.", "Limit total configured agent personas in studio.")}</p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
