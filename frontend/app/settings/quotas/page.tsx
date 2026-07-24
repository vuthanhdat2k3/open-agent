"use client";

import * as React from "react";
import { Gauge, Save } from "lucide-react";
import { toast } from "sonner";
import {
  useMe,
  useOrganizationQuota,
  useQuotaUsage,
  useUpdateOrganizationQuota,
} from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

type FormState = {
  requests_per_minute: string;
  agent_runs_per_minute: string;
  max_concurrent_runs: string;
  monthly_cost_usd: string;
  max_agents: string;
  max_workflows: string;
  max_storage_bytes: string;
  enforcement_mode: "enforce" | "observe";
};

const EMPTY_FORM: FormState = {
  requests_per_minute: "",
  agent_runs_per_minute: "",
  max_concurrent_runs: "",
  monthly_cost_usd: "",
  max_agents: "",
  max_workflows: "",
  max_storage_bytes: "",
  enforcement_mode: "enforce",
};

function optionalNumber(value: string) {
  return value === "" ? null : Number(value);
}

export default function QuotasPage() {
  const me = useMe();
  const orgId = me.data?.memberships?.[0]?.org_id;
  const quota = useOrganizationQuota(orgId);
  const usage = useQuotaUsage(orgId);
  const updateQuota = useUpdateOrganizationQuota(orgId);
  const [form, setForm] = React.useState<FormState>(EMPTY_FORM);

  React.useEffect(() => {
    if (!quota.data) return;
    setForm({
      requests_per_minute: String(quota.data.requests_per_minute),
      agent_runs_per_minute: String(quota.data.agent_runs_per_minute),
      max_concurrent_runs: String(quota.data.max_concurrent_runs),
      monthly_cost_usd: String(quota.data.monthly_cost_usd),
      max_agents: quota.data.max_agents?.toString() ?? "",
      max_workflows: quota.data.max_workflows?.toString() ?? "",
      max_storage_bytes: quota.data.max_storage_bytes?.toString() ?? "",
      enforcement_mode: quota.data.enforcement_mode,
    });
  }, [quota.data]);

  const setField = (field: keyof FormState, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
  };

  const save = async () => {
    try {
      await updateQuota.mutateAsync({
        requests_per_minute: Number(form.requests_per_minute),
        agent_runs_per_minute: Number(form.agent_runs_per_minute),
        max_concurrent_runs: Number(form.max_concurrent_runs),
        monthly_cost_usd: Number(form.monthly_cost_usd),
        max_agents: optionalNumber(form.max_agents),
        max_workflows: optionalNumber(form.max_workflows),
        max_storage_bytes: optionalNumber(form.max_storage_bytes),
        enforcement_mode: form.enforcement_mode,
      });
      toast.success("Quota policy saved");
    } catch (error: any) {
      toast.error(error.message);
    }
  };

  if (quota.isLoading || usage.isLoading) {
    return <Skeleton className="h-[520px] w-full" />;
  }

  const usageRows = usage.data
    ? [
        {
          label: "Monthly cost",
          value: `$${usage.data.monthly_cost_usd.toFixed(4)}`,
          limit: `$${usage.data.monthly_cost_limit_usd.toFixed(2)}`,
        },
        {
          label: "Agents",
          value: usage.data.agents.toLocaleString(),
          limit: usage.data.agent_limit?.toLocaleString() ?? "Unlimited",
        },
        {
          label: "Workflows",
          value: usage.data.workflows.toLocaleString(),
          limit: usage.data.workflow_limit?.toLocaleString() ?? "Unlimited",
        },
        {
          label: "Storage",
          value: `${(usage.data.storage_bytes / 1_048_576).toFixed(2)} MB`,
          limit: usage.data.storage_limit_bytes
            ? `${(usage.data.storage_limit_bytes / 1_048_576).toFixed(2)} MB`
            : "Unlimited",
        },
        {
          label: "Active runs",
          value: String(usage.data.active_run_leases),
          limit: String(usage.data.concurrent_run_limit),
        },
      ]
    : [];

  return (
    <div className="space-y-7">
      <PageHeader
        icon={Gauge}
        title="Tenant quotas"
        description={`Admission and spend controls for ${usage.data?.month ?? "current month"}`}
        actions={
          <Button
            className="gap-2"
            onClick={save}
            disabled={updateQuota.isPending}
          >
            <Save className="h-4 w-4" />
            {updateQuota.isPending ? "Saving..." : "Save"}
          </Button>
        }
      />

      <section>
        <h2 className="text-sm font-semibold">Current usage</h2>
        <div className="mt-3 grid border-y border-border/60 sm:grid-cols-2 lg:grid-cols-5">
          {usageRows.map((row) => (
            <div
              key={row.label}
              className="border-b border-border/60 p-4 sm:border-r lg:border-b-0"
            >
              <p className="text-xs text-muted-foreground">{row.label}</p>
              <p className="mt-1 text-lg font-semibold">{row.value}</p>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Limit {row.limit}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold">Admission policy</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              Observe records limit decisions without rejecting requests.
            </p>
          </div>
          <div className="w-40">
            <Label>Mode</Label>
            <Select
              className="mt-1.5"
              value={form.enforcement_mode}
              onChange={(event) =>
                setField("enforcement_mode", event.target.value)
              }
            >
              <option value="enforce">Enforce</option>
              <option value="observe">Observe</option>
            </Select>
          </div>
        </div>

        <div className="mt-5 grid gap-x-6 gap-y-4 border-t border-border/60 pt-5 md:grid-cols-2 xl:grid-cols-3">
          {[
            ["requests_per_minute", "Requests per minute"],
            ["agent_runs_per_minute", "Agent runs per minute"],
            ["max_concurrent_runs", "Concurrent runs"],
            ["monthly_cost_usd", "Monthly cost (USD)"],
            ["max_agents", "Agents"],
            ["max_workflows", "Workflows"],
            ["max_storage_bytes", "Storage (bytes)"],
          ].map(([field, label]) => (
            <div key={field} className="space-y-1.5">
              <Label>{label}</Label>
              <Input
                type="number"
                min="0"
                value={form[field as keyof FormState]}
                placeholder={field.startsWith("max_") ? "Unlimited" : undefined}
                onChange={(event) =>
                  setField(field as keyof FormState, event.target.value)
                }
              />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
