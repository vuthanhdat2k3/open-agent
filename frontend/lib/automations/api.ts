import { api } from "@/lib/api";

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

export function getWorkflowCatalog(params: { query?: string; category?: string } = {}) {
  const search = new URLSearchParams();
  if (params.query?.trim()) search.set("query", params.query.trim());
  if (params.category) search.set("category", params.category);
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return api.get<WorkflowCatalogResponse>(`/api/workflow-catalog/templates${suffix}`);
}
