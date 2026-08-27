import { api } from "@/lib/api";
import { createIdempotencyKey } from "@/lib/email-intelligence/idempotency";

export type WorkflowCatalogItem = {
  key: string;
  version: number;
  name: string;
  description: string;
  outcome: string;
  category: string;
  icon: string;
  required_integrations: string[];
  optional_integrations: string[];
  default_schedule_label: string;
  cost_tier: "low" | "medium" | "high" | string;
  estimated_cost_usd: { per_run_max?: string };
  side_effect_policy: "none" | "approval_required" | "trusted_rule_eligible" | string;
  recommendation: { recommended: boolean; reason_code: string | null; params: Record<string, unknown> };
  installed: boolean;
  capabilities: { can_view: boolean; can_install: boolean };
  blocked_reasons: Record<string, string[]>;
};

export type WorkflowCatalogResponse = {
  data: WorkflowCatalogItem[];
  meta: { server_time: string; next_cursor: string | null };
};

export type WorkflowInstallation = {
  id: string;
  template_key: string;
  template_version: number;
  workflow_id: string;
  name: string;
  status: "enabled" | "paused" | string;
  timezone: string;
  schedule: { kind: string; time?: string | null; interval_hours?: number | null; weekday?: number | null };
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  capabilities: { can_view: boolean; can_pause: boolean; can_resume: boolean; can_delete: boolean; can_run_now: boolean };
  blocked_reasons: Record<string, string[]>;
};

export type WorkflowActivityItem = {
  id: string;
  installation_id: string;
  template_key: string;
  name: string;
  scheduled_for: string;
  status: string;
  output: Record<string, unknown>;
  error: string | null;
  created_at: string;
};

export function getWorkflowCatalog(params: { query?: string; category?: string } = {}) {
  const search = new URLSearchParams();
  if (params.query?.trim()) search.set("query", params.query.trim());
  if (params.category) search.set("category", params.category);
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return api.get<WorkflowCatalogResponse>(`/api/workflow-catalog/templates${suffix}`);
}

export function getWorkflowInstallations() {
  return api.get<WorkflowInstallation[]>("/api/workflow-catalog/installations");
}

export function getWorkflowActivity() {
  return api.get<{ items: WorkflowActivityItem[]; meta: { server_time: string } }>("/api/workflow-catalog/activity");
}

export function installWorkflowTemplate(body: { template_key: string; name?: string; timezone: string; schedule: WorkflowInstallation["schedule"]; settings?: Record<string, unknown> }) {
  return api.post<WorkflowInstallation>("/api/workflow-catalog/installations", body, { headers: { "Idempotency-Key": createIdempotencyKey() } });
}

export function pauseWorkflowInstallation(id: string) {
  return api.post<WorkflowInstallation>(`/api/workflow-catalog/installations/${id}/pause`);
}

export function resumeWorkflowInstallation(id: string) {
  return api.post<WorkflowInstallation>(`/api/workflow-catalog/installations/${id}/resume`);
}

export function runWorkflowInstallation(id: string) {
  return api.post<WorkflowInstallation>(`/api/workflow-catalog/installations/${id}/run`);
}

export function deleteWorkflowInstallation(id: string) {
  return api.delete<void>(`/api/workflow-catalog/installations/${id}`);
}

export function publishWorkflowToCatalog(body: {
  workflow_id: string;
  category?: string;
  description?: string;
  outcome?: string;
  icon?: string;
}) {
  return api.post<WorkflowCatalogItem>("/api/workflow-catalog/publish", body);
}

export function unpublishWorkflowFromCatalog(key: string) {
  return api.delete<{ ok: boolean }>(`/api/workflow-catalog/templates/${key}`);
}
