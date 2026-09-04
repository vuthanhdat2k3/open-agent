"use client";

import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { getAccessToken, getActiveOrgId, getCsrfToken, setActiveOrgId } from "@/lib/auth";
import type {
  Agent,
  AgentRelease,
  AgentToolInfo,
  ApiKey,
  ApiKeyCreateResponse,
  ApprovalRequest,
  EvaluationCase,
  EvaluationCaseInput,
  EvaluationRun,
  EvaluationRunInput,
  EvaluationSuite,
  EvaluationSuiteInput,
  IngestResult,
  McpServer,
  Message,
  Model,
  ModelTestResult,
  OrgModelTierMatrixResponse,
  OrgModelTierMatrixUpdate,
  OrganizationQuota,
  Organization,
  OrgMember,
  Provider,
  ProviderTemplate,
  QuotaUsage,
  SandboxExecution,
  Session,
  TaskTree,
  UploadedFile,
  UsageSummary,
  Workflow,
  ChatRunDetail,
  ExecutionPolicy,
  WorkflowRunDetail,
  WorkspaceArtifact,
  UserProfile,
  CustomerIntelligenceCase,
  CustomerIntelligenceCaseDetail,
  CustomerIntelligenceConnection,
  CustomerIntelligenceNotification,
  CustomerIntelligenceSchedule,
  CustomerIntelligenceNotificationPage,
  EmailIntelligenceNavigationSummary,
  NodeDefinition,
  NodeOption,
  ChannelConnection,
  ChannelMessage,
} from "@/types";

import { emailIntelligenceQueryKeys } from "@/lib/email-intelligence/query-keys";
import { createIdempotencyKey } from "@/lib/email-intelligence/idempotency";

export function useCustomerIntelligenceCases(filters: { category?: "briefings" | "review"; query?: string; limit?: number; offset?: number } = {}) {
  const orgId = getActiveOrgId();
  const params = new URLSearchParams({
    category: filters.category ?? "briefings",
    limit: String(filters.limit ?? 25),
    offset: String(filters.offset ?? 0),
  });
  if (filters.query?.trim()) params.set("q", filters.query.trim());
  return useQuery({
    queryKey: emailIntelligenceQueryKeys(orgId).cases(filters),
    queryFn: () => api.get<CustomerIntelligenceCase[]>(`/api/customer-intelligence/cases?${params}`),
    refetchInterval: 10_000,
  });
}

export function useCiConnections() {
  const orgId = getActiveOrgId();
  return useQuery({
    queryKey: ["customer-intelligence", orgId, "connections"],
    queryFn: () => api.get<CustomerIntelligenceConnection[]>("/api/customer-intelligence/connections"),
  });
}

export function useCiSchedules() {
  const orgId = getActiveOrgId();
  return useQuery({
    queryKey: ["customer-intelligence", orgId, "schedules"],
    queryFn: () => api.get<CustomerIntelligenceSchedule[]>("/api/customer-intelligence/schedules"),
    refetchInterval: 30_000,
  });
}

export function useCreateCiSchedule() {
  const qc = useQueryClient();
  const orgId = getActiveOrgId();
  return useMutation({
    mutationFn: (body: { connection_id: string; run_time: string; timezone: string; enabled: boolean }) =>
      api.post<CustomerIntelligenceSchedule>("/api/customer-intelligence/schedules", body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["customer-intelligence", orgId, "schedules"] }),
  });
}

export function useUpdateCiSchedule() {
  const qc = useQueryClient();
  const orgId = getActiveOrgId();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { run_time?: string; timezone?: string; enabled?: boolean } }) =>
      api.patch<CustomerIntelligenceSchedule>(`/api/customer-intelligence/schedules/${id}`, body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["customer-intelligence", orgId, "schedules"] }),
  });
}

export function useRunCiScheduleNow() {
  const qc = useQueryClient();
  const orgId = getActiveOrgId();
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/customer-intelligence/schedules/${id}/run`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["customer-intelligence", orgId, "schedules"] });
      void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).cases() });
    },
  });
}

export function useDeleteCiSchedule() {
  const qc = useQueryClient();
  const orgId = getActiveOrgId();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/api/customer-intelligence/schedules/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["customer-intelligence", orgId, "schedules"] }),
  });
}

export function useCustomerIntelligenceCase(id: string | null) {
  const orgId = getActiveOrgId();
  return useQuery({
    queryKey: emailIntelligenceQueryKeys(orgId).case(id),
    queryFn: () => api.get<CustomerIntelligenceCaseDetail>(`/api/customer-intelligence/cases/${id}`),
    enabled: Boolean(id),
  });
}

export function useResearchCustomerIntelligenceCase() {
  const qc = useQueryClient();
  const orgId = getActiveOrgId();
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/customer-intelligence/cases/${id}/research`, {}, { headers: { "Idempotency-Key": createIdempotencyKey() } }),
    onSuccess: (_data, id) => {
      void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).cases() });
      void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).case(id) });
    },
  });
}

export function useRetryCustomerIntelligenceCase() {
  const qc = useQueryClient();
  const orgId = getActiveOrgId();
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/customer-intelligence/cases/${id}/retry`, {}, { headers: { "Idempotency-Key": createIdempotencyKey() } }),
    onSuccess: (_data, id) => {
      void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).cases() });
      void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).case(id) });
    },
  });
}

export function useDeleteCustomerIntelligenceCase() {
  const qc = useQueryClient();
  const orgId = getActiveOrgId();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/api/customer-intelligence/cases/${id}`),
    onSuccess: (_data, id) => {
      void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).cases() });
      void qc.removeQueries({ queryKey: emailIntelligenceQueryKeys(orgId).case(id) });
    },
  });
}

export function useCreateManualCustomerIntelligenceCase() {
  const qc = useQueryClient();
  const orgId = getActiveOrgId();
  return useMutation({
    mutationFn: (body: { company_name: string; company_domain?: string; question?: string }) =>
      api.post<CustomerIntelligenceCase>("/api/customer-intelligence/cases/manual", body, { headers: { "Idempotency-Key": createIdempotencyKey() } }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).cases() }),
  });
}

export interface CustomerIntelligenceNotificationFilters {
  unreadOnly?: boolean;
  cursor?: string | null;
  limit?: number;
  query?: string;
  receivedAfter?: string;
  receivedBefore?: string;
  notificationType?: string;
}

export function useCustomerIntelligenceNotifications(filters: CustomerIntelligenceNotificationFilters = {}) {
  const orgId = getActiveOrgId();
  const limitStr = filters.limit ? String(filters.limit) : "8";
  const params = new URLSearchParams({ limit: limitStr });
  if (filters.unreadOnly) params.set("unread_only", "true");
  if (filters.cursor) params.set("cursor", filters.cursor);
  if (filters.query) params.set("q", filters.query);
  if (filters.receivedAfter) params.set("received_after", filters.receivedAfter);
  if (filters.receivedBefore) params.set("received_before", filters.receivedBefore);
  if (filters.notificationType) params.set("notification_type", filters.notificationType);
  return useQuery({
    queryKey: [
      ...emailIntelligenceQueryKeys(orgId).notifications(filters.cursor ?? null),
      filters.unreadOnly ?? false,
      limitStr,
      filters.query ?? "",
      filters.receivedAfter ?? "",
      filters.receivedBefore ?? "",
      filters.notificationType ?? "",
    ],
    queryFn: () => api.get<CustomerIntelligenceNotificationPage>(`/api/customer-intelligence/notifications?${params.toString()}`),
    refetchInterval: 30_000,
  });
}

export function useMarkCustomerIntelligenceNotificationRead() {
  const qc = useQueryClient();
  const orgId = getActiveOrgId();
  return useMutation({
    mutationFn: (id: string) => api.post(`/api/customer-intelligence/notifications/${id}/read`, undefined, { headers: { "Idempotency-Key": createIdempotencyKey() } }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).notifications() });
      void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).navigation });
    },
  });
}

export function useEmailIntelligenceNavigationSummary() {
  const orgId = getActiveOrgId();
  return useQuery({
    queryKey: emailIntelligenceQueryKeys(orgId).navigation,
    queryFn: () => api.get<EmailIntelligenceNavigationSummary>("/api/customer-intelligence/navigation-summary"),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useProviderTemplates(enabled: boolean = true) {
  return useQuery({
    queryKey: ["provider-templates"],
    queryFn: () => api.get<ProviderTemplate[]>("/api/providers/templates"),
    enabled,
  });
}

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: () => api.get<{ runtime: string }>("/api/health") });
}

export function useCreateProviderFromTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { template_key: string; api_key: string; base_url?: string; is_default?: boolean }) =>
      api.post<Provider>("/api/providers/from-template", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["providers"] });
      qc.invalidateQueries({ queryKey: ["models"] });
    },
  });
}

export function useProviders(enabled: boolean = true) {
  return useQuery({ queryKey: ["providers"], queryFn: () => api.get<Provider[]>("/api/providers"), enabled });
}
export function useCreateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: any) => api.post<Provider>("/api/providers", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}
export function useDeleteProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/providers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}
export function useUpdateProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: any) => api.put<Provider>(`/api/providers/${id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["providers"] });
      qc.invalidateQueries({ queryKey: ["models"] });
    },
  });
}

export function useTestProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<any>(`/api/providers/${id}/test`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["providers"] });
      qc.invalidateQueries({ queryKey: ["models"] });
    },
  });
}

export function useModels(
  enabled: boolean = true,
  options: {
    withInactive?: boolean;
    active?: boolean;
    provider?: string;
    providerId?: string;
    q?: string;
  } = {},
) {
  const params = new URLSearchParams();
  if (options.withInactive) params.set("with_inactive", "true");
  if (options.active !== undefined) params.set("active", String(options.active));
  const prov = options.provider || options.providerId;
  if (prov?.trim()) params.set("provider", prov.trim());
  if (options.q?.trim()) params.set("q", options.q.trim());
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return useQuery({
    queryKey: [
      "models",
      options.withInactive ?? false,
      options.active ?? "all",
      prov ?? "all",
      options.q ?? "",
    ],
    queryFn: () => api.get<Model[]>(`/api/models${suffix}`),
    enabled,
  });
}
export function useCreateModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: any) => api.post<Model>("/api/models", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
  });
}
export function useDeleteModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/models/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
  });
}

export function useUpdateModel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: any) => api.put<Model>(`/api/models/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["models"] }),
  });
}

export function useTestModel() {
  return useMutation({
    mutationFn: (id: string) => api.post<ModelTestResult>(`/api/models/${id}/test`),
  });
}

export function useModelTierMatrix(enabled: boolean = true) {
  return useQuery({
    queryKey: ["model-tier-matrix"],
    queryFn: () => api.get<OrgModelTierMatrixResponse>("/api/models/tier-matrix"),
    enabled,
  });
}

export function useUpdateModelTierMatrix() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: OrgModelTierMatrixUpdate) => api.put<OrgModelTierMatrixResponse>("/api/models/tier-matrix", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["model-tier-matrix"] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}


export function useAgents() {
  return useQuery({ queryKey: ["agents"], queryFn: () => api.get<Agent[]>("/api/agents") });
}
export function useAgentTools(enabled: boolean = true) {
  return useQuery({ queryKey: ["agent-tools"], queryFn: () => api.get<AgentToolInfo[]>("/api/agents/tools"), enabled });
}
export function useCreateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: any) => api.post<Agent>("/api/agents", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}
export function useDeleteAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/agents/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}
export function useUpdateAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: any) => api.put<Agent>(`/api/agents/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agents"] }),
  });
}

export function useAgentReleases(agentId: string | null) {
  return useQuery({
    queryKey: ["agent-releases", agentId],
    enabled: !!agentId,
    queryFn: () => api.get<AgentRelease[]>(`/api/agents/${agentId}/releases`),
  });
}

export function useCreateAgentRelease() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, ...body }: { agentId: string; [key: string]: any }) =>
      api.post<AgentRelease>(`/api/agents/${agentId}/releases`, body),
    onSuccess: (release) => {
      qc.invalidateQueries({ queryKey: ["agent-releases", release.agent_id] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function usePublishAgentRelease() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, version }: { agentId: string; version: number }) =>
      api.post<AgentRelease>(`/api/agents/${agentId}/releases/${version}/publish`),
    onSuccess: (release) => {
      qc.invalidateQueries({ queryKey: ["agent-releases", release.agent_id] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function useRollbackAgentRelease() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, version }: { agentId: string; version: number }) =>
      api.post<AgentRelease>(`/api/agents/${agentId}/releases/${version}/rollback`),
    onSuccess: (release) => {
      qc.invalidateQueries({ queryKey: ["agent-releases", release.agent_id] });
      qc.invalidateQueries({ queryKey: ["agents"] });
    },
  });
}

export function useEvaluationSuites() {
  return useQuery({
    queryKey: ["evaluation-suites"],
    queryFn: () => api.get<EvaluationSuite[]>("/api/evaluations/suites"),
  });
}

export function useCreateEvaluationSuite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EvaluationSuiteInput) =>
      api.post<EvaluationSuite>("/api/evaluations/suites", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["evaluation-suites"] }),
  });
}

export function useAddEvaluationCase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ suiteId, ...body }: EvaluationCaseInput & { suiteId: string }) =>
      api.post<EvaluationCase>(`/api/evaluations/suites/${suiteId}/cases`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["evaluation-suites"] }),
  });
}

export function useEvaluationRuns(suiteId: string | null) {
  return useQuery({
    queryKey: ["evaluation-runs", suiteId],
    enabled: !!suiteId,
    queryFn: () =>
      api.get<EvaluationRun[]>(`/api/evaluations/suites/${suiteId}/runs`),
  });
}

export function useCreateEvaluationRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ suiteId, ...body }: EvaluationRunInput & { suiteId: string }) =>
      api.post<EvaluationRun>(`/api/evaluations/suites/${suiteId}/runs`, body),
    onSuccess: (run) => {
      qc.invalidateQueries({ queryKey: ["evaluation-runs", run.suite_id] });
      qc.invalidateQueries({ queryKey: ["evaluation-suites"] });
    },
  });
}

// Channel hooks
export function useChannelConnections(enabled: boolean = true) {
  return useQuery({ queryKey: ["channels"], queryFn: () => api.get<ChannelConnection[]>("/api/channels"), enabled });
}
export function useCreateChannelConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { provider: "telegram" | "discord"; bot_token: string; bot_username?: string; config?: Record<string, any> }) =>
      api.post<ChannelConnection>("/api/channels", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["channels"] }),
  });
}
export function useDeleteChannelConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/api/channels/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["channels"] }),
  });
}
export function useUpdateChannelConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; bot_token?: string; bot_username?: string; config?: Record<string, any>; status?: string }) =>
      api.patch<ChannelConnection>(`/api/channels/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["channels"] }),
  });
}
export function useTestChannelConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<{ ok: boolean; message: string }>(`/api/channels/${id}/test`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["channels"] }),
  });
}

export function useMcpServers(enabled: boolean = true) {
  return useQuery({ queryKey: ["mcp"], queryFn: () => api.get<McpServer[]>("/api/mcp/servers"), enabled });
}
export function useCreateMcp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: any) => api.post<McpServer>("/api/mcp/servers", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mcp"] }),
  });
}
export function useDeleteMcp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/mcp/servers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mcp"] }),
  });
}
export function useUpdateMcp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: any) => api.put<McpServer>(`/api/mcp/servers/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mcp"] }),
  });
}

export function useConnectMcp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<any>(`/api/mcp/servers/${id}/connect`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mcp"] }),
  });
}
export function useDisconnectMcp() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<any>(`/api/mcp/servers/${id}/disconnect`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mcp"] }),
  });
}

export function useWorkflows() {
  return useQuery({ queryKey: ["workflows"], queryFn: () => api.get<Workflow[]>("/api/workflows") });
}
export function useCreateWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: any) => api.post<Workflow>("/api/workflows", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  });
}
export function useUpdateWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => api.put<Workflow>(`/api/workflows/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  });
}
export function useGenerateWorkflow() {
  return useMutation({
    mutationFn: (body: { prompt: string; model_id: string }) =>
      api.post<{ name: string; description: string; graph: any }>("/api/workflows/generate", body),
  });
}
export function useDeleteWorkflow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/workflows/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  });
}
export function useResetWorkflowTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Workflow>(`/api/workflows/${id}/reset-template`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workflows"] }),
  });
}

export function useSessions() {
  return useQuery({ queryKey: ["sessions"], queryFn: () => api.get<Session[]>("/api/sessions") });
}
export function useUpdateSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string; execution_policy?: ExecutionPolicy; title?: string }) =>
      api.patch<Session>(`/api/sessions/${id}`, data),
    onSuccess: (updated) => {
      qc.setQueriesData<Session[]>({ queryKey: ["sessions"] }, (old) =>
        old ? old.map((s) => (s.id === updated.id ? { ...s, ...updated } : s)) : [updated],
      );
    },
  });
}
export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/sessions/${id}`),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: ["sessions"] });
      const previous = qc.getQueryData<Session[]>(["sessions"]);
      qc.setQueryData<Session[]>(["sessions"], (sessions) =>
        sessions?.filter((session) => session.id !== id),
      );
      qc.removeQueries({ queryKey: ["messages", id], exact: true });
      return { previous };
    },
    onError: (_error, _id, context) => {
      if (context?.previous) qc.setQueryData(["sessions"], context.previous);
    },
    // The successful DELETE response is authoritative. Avoid a second full
    // sessions request just to redraw an item already removed optimistically.
  });
}
export function useSessionMessages(sessionId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["messages", sessionId],
    enabled: enabled && !!sessionId,
    queryFn: () => api.get<Message[]>(`/api/sessions/${sessionId}/messages`),
  });
}

export function useUsageSummary(enabled: boolean = true) {
  return useQuery({ queryKey: ["usage"], queryFn: () => api.get<UsageSummary[]>("/api/debug/usage"), enabled });
}
export function useDebugSessions() {
  return useQuery({ queryKey: ["debug-sessions"], queryFn: () => api.get<Session[]>("/api/debug/sessions") });
}
export function useSessionTree(sessionId: string | null) {
  return useQuery({
    queryKey: ["tree", sessionId],
    enabled: !!sessionId,
    queryFn: () => api.get<any>(`/api/debug/sessions/${sessionId}`),
  });
}

export function useFiles() {
  return useQuery({
    queryKey: ["files"],
    queryFn: () => api.get<UploadedFile[]>("/api/files"),
    refetchInterval: 3000,
  });
}
export function useUploadFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const token = getAccessToken();
      const csrf = getCsrfToken();
      const orgId = getActiveOrgId();
      const res = await fetch("/api/files/upload", {
        method: "POST",
        body: form,
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...(csrf ? { "X-CSRF-Token": csrf } : {}),
          ...(orgId ? { "X-Org-Id": orgId } : {}),
        },
        credentials: "include",
      });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const j = await res.json();
          detail = (j && j.detail) || detail;
        } catch {
          // ignore parse errors
        }
        throw new Error(detail);
      }
      return (await res.json()) as UploadedFile;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["files"] }),
  });
}
export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/files/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["files"] }),
  });
}
export function useIngestFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: any }) =>
      api.post<IngestResult>(`/api/files/${id}/ingest`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["files"] }),
  });
}

export function useWorkspaceArtifacts() {
  return useQuery({
    queryKey: ["workspace-artifacts"],
    queryFn: () => api.get<WorkspaceArtifact[]>("/api/workspace/artifacts"),
  });
}

export function useDeleteWorkspaceArtifact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/workspace/artifacts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workspace-artifacts"] }),
  });
}

export function useRunWorkspaceArtifact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (artifactId: string) =>
      api.post<{ execution_id: string; artifact_id: string; max_seconds: number }>(
        `/api/workspace/artifacts/${artifactId}/run`,
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["sandbox-executions"] });
    },
  });
}

export function useSandboxExecutions() {
  return useQuery({
    queryKey: ["sandbox-executions"],
    queryFn: () => api.get<SandboxExecution[]>("/api/workspace/executions"),
    refetchInterval: 5000,
  });
}

export function useDeleteSandboxExecution() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/workspace/executions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sandbox-executions"] }),
  });
}

export function useMe(enabled: boolean = true) {
  return useQuery({
    queryKey: ["auth-me"],
    queryFn: async () => {
      const data = await api.get<UserProfile>("/api/auth/me");
      if (data.active_org_id) {
        setActiveOrgId(data.active_org_id);
      } else if (data.memberships?.[0]?.org_id && !getActiveOrgId()) {
        setActiveOrgId(data.memberships[0].org_id);
      }
      return data;
    },
    enabled,
  });
}

// Fails closed: an unresolved role (loading, no membership found for the
// active org) is treated as "user" rather than "admin" so admin-only UI
// never flashes open before the real role is known.
import type { Role } from "@/lib/roles";
import { normalizeRole } from "@/lib/roles";

export function useCurrentRole(): Role {
  const me = useMe();
  const orgId = me.data?.active_org_id || getActiveOrgId();
  const membership = me.data?.memberships?.find((m) => m.org_id === orgId) ?? me.data?.memberships?.[0];
  return normalizeRole(membership?.role);
}

export function useCurrentPermissions(): string[] {
  const me = useMe();
  const orgId = me.data?.active_org_id || getActiveOrgId() || me.data?.memberships?.[0]?.org_id;
  return (orgId && me.data?.permissions_by_org?.[orgId]) || [];
}

export function hasUiPermission(permissions: string[], permission: string) {
  return permissions.includes("*") || permissions.includes(permission) || permissions.some((value) => value.endsWith(":*") && permission.startsWith(value.slice(0, -1)));
}

export function useCan(permission: string) {
  return hasUiPermission(useCurrentPermissions(), permission);
}

export function useOrganizations(enabled = true) {
  return useQuery({
    queryKey: ["organizations"],
    enabled,
    queryFn: () => api.get<Organization[]>("/api/orgs"),
  });
}

export function useCreateOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; admin_email?: string; initial_password?: string }) => api.post<Organization>("/api/orgs", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["organizations"] }),
  });
}

export function useRenameOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ orgId, name }: { orgId: string; name: string }) => api.patch<Organization>(`/api/orgs/${orgId}`, { name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["organizations"] }),
  });
}

export function useDeleteOrganization() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (orgId: string) => api.delete(`/api/orgs/${orgId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["organizations"] }),
  });
}

export function useMembers(orgId?: string) {
  return useQuery({
    queryKey: ["members", orgId],
    enabled: !!orgId,
    queryFn: () => api.get<OrgMember[]>(`/api/orgs/${orgId}/members`),
  });
}

export function useInviteMember(orgId?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; role: string; initial_password?: string }) =>
      api.post<OrgMember>(`/api/orgs/${orgId}/members`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members", orgId] }),
  });
}

export function useRemoveMember(orgId?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) => api.delete(`/api/orgs/${orgId}/members/${userId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members", orgId] }),
  });
}

export function useApiKeys(orgId?: string) {
  return useQuery({
    queryKey: ["api-keys", orgId],
    enabled: !!orgId,
    queryFn: () => api.get<ApiKey[]>(`/api/orgs/${orgId}/api-keys`),
  });
}

export function useCreateApiKey(orgId?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; expires_days?: number | null }) =>
      api.post<ApiKeyCreateResponse>(`/api/orgs/${orgId}/api-keys`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys", orgId] }),
  });
}

export function useRevokeApiKey(orgId?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) => api.delete(`/api/orgs/${orgId}/api-keys/${keyId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys", orgId] }),
  });
}

export function useOrganizationQuota(orgId?: string) {
  return useQuery({
    queryKey: ["organization-quota", orgId],
    enabled: !!orgId,
    queryFn: () =>
      api.get<OrganizationQuota>(`/api/orgs/${orgId}/quota`),
  });
}

export function useQuotaUsage(orgId?: string) {
  return useQuery({
    queryKey: ["quota-usage", orgId],
    enabled: !!orgId,
    queryFn: () =>
      api.get<QuotaUsage>(`/api/orgs/${orgId}/quota/usage`),
  });
}

export function useUpdateOrganizationQuota(orgId?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<OrganizationQuota>) =>
      api.put<OrganizationQuota>(`/api/orgs/${orgId}/quota`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["organization-quota", orgId] });
      qc.invalidateQueries({ queryKey: ["quota-usage", orgId] });
    },
  });
}

export function useApprovals(enabled: boolean = true, includeChat: boolean = false, runId?: string | null) {
  const orgId = getActiveOrgId();
  const queryParams = new URLSearchParams();
  if (includeChat) queryParams.set("include_chat", "true");
  if (runId) queryParams.set("run_id", runId);
  const qs = queryParams.toString() ? `?${queryParams.toString()}` : "";

  return useQuery({
    queryKey: [...emailIntelligenceQueryKeys(orgId).approvals(), { includeChat, runId }],
    queryFn: () => api.get<ApprovalRequest[]>(`/api/approvals${qs}`),
    // Poll frequently while approval handling is active so the chat page
    // and approvals dashboard discover new approval gates promptly.
    refetchInterval: enabled ? 5000 : false,
    refetchIntervalInBackground: false,
    enabled,
  });
}

export function useDecideApproval() {
  const qc = useQueryClient();
  const orgId = getActiveOrgId();
  return useMutation({
    mutationFn: ({ id, decision, reason = "", idempotencyKey }: { id: string; decision: "approved" | "rejected"; reason?: string; idempotencyKey: string }) =>
      api.post<ApprovalRequest>(`/api/approvals/${id}/decide`, { decision, reason }, { headers: { "Idempotency-Key": idempotencyKey } }),
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: ["approvals"] });
      void qc.invalidateQueries({ queryKey: ["workflow-run"] });
      void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).approvals() });
      void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).navigation });
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("approval-decided", { detail: data }));
      }
    },
  });
}

export function useTaskTree(rootRunId: string | null) {
  return useQuery({
    queryKey: ["task-tree", rootRunId],
    enabled: !!rootRunId,
    queryFn: () => api.get<TaskTree>(`/api/debug/tasks/${rootRunId}`),
  });
}

export function useWorkflowRun(runId: string | null) {
  return useQuery({
    queryKey: ["workflow-run", runId],
    enabled: !!runId,
    queryFn: () => api.get<WorkflowRunDetail>(`/api/workflows/runs/${runId}`),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ["succeeded", "failed", "diverged", "cancelled"].includes(status)
        ? false
        : 2000;
    },
  });
}

export function useNodeDefinitions() {
  return useQuery({
    queryKey: ["workflow-node-definitions"],
    queryFn: () => api.get<Record<string, NodeDefinition>>("/api/workflows/node-definitions"),
    staleTime: 5 * 60 * 1000,
  });
}

export function useNodeOptions(type: string) {
  return useQuery({
    queryKey: ["workflow-node-options", type],
    enabled: !!type,
    queryFn: () => api.get<NodeOption[]>(`/api/workflows/node-options?type=${encodeURIComponent(type)}`),
    staleTime: 60 * 1000,
  });
}

export function useToolOptions() {
  return useQuery({
    queryKey: ["workflow-tool-options"],
    queryFn: () => api.get<NodeOption[]>("/api/workflows/tool-options"),
    staleTime: 60 * 1000,
  });
}

export function useChatRun(runId: string | null) {
  return useQuery({
    queryKey: ["chat-run", runId],
    enabled: !!runId,
    queryFn: () => api.get<ChatRunDetail>(`/api/chat/runs/${runId}`),
    retry: (failureCount, error) => {
      // A missing run is authoritative for stale localStorage state. Retrying
      // it only floods the proxy with the same 404 while the page is already
      // able to clear the stale active run.
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 3;
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Keep polling at a shorter cadence during waiting_approval so the
      // frontend discovers when the root task transitions back to "queued" /
      // "running" after the user decides an approval (whether inline or via
      // the /approvals page). Without this the hook stops polling the moment
      // it first sees waiting_approval and never learns about the resumed run.
      if (status === "waiting_approval") return 3000;
      return status && ["succeeded", "failed", "diverged", "cancelled"].includes(status)
        ? false
        : 2000;
    },
  });
}

export function useProfile(enabled: boolean = true) {
  return useQuery({
    queryKey: ["auth-me"],
    queryFn: () => api.get<UserProfile>("/api/auth/me"),
    enabled,
  });
}

// One searchParam mirrored as component state: reading returns the current
// value, the setter rewrites the query string in place (no history entries).
// Selection params (suite, case, run...) use this so deep links and the
// back/forward buttons behave like navigation.
export function useUrlSearchParam(key: string): [string | null, (value: string | null) => void] {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const value = searchParams.get(key);

  const setValue = React.useCallback(
    (next: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (next) params.set(key, next);
      else params.delete(key);
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [key, pathname, router, searchParams],
  );

  return [value, setValue];
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { display_name?: string; old_password?: string; new_password?: string }) =>
      api.patch<UserProfile>("/api/auth/me", body),
    // useMe and useProfile both share the "auth-me" key; invalidating the
    // previous ("profile") key kept the sidebar / nav stale for up to gcTime.
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auth-me"] }),
  });
}

export function useUpdateMemberRole(orgId?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: "org_admin" | "operator" | "user" }) =>
      api.patch<OrgMember>(`/api/orgs/${orgId}/members/${userId}`, { role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members", orgId] }),
  });
}
