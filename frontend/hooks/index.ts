"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
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
  OrganizationQuota,
  OrgMember,
  Provider,
  QuotaUsage,
  SandboxExecution,
  Session,
  TaskTree,
  UploadedFile,
  UsageSummary,
  Workflow,
  ChatRunDetail,
  WorkflowRunDetail,
  WorkspaceArtifact,
  UserProfile,
} from "@/types";

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
    onSuccess: () => qc.invalidateQueries({ queryKey: ["providers"] }),
  });
}

export function useTestProvider() {
  return useMutation({ mutationFn: (id: string) => api.post<any>(`/api/providers/${id}/test`) });
}

export function useModels(enabled: boolean = true) {
  return useQuery({ queryKey: ["models"], queryFn: () => api.get<Model[]>("/api/models"), enabled });
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

export function useMcpServers() {
  return useQuery({ queryKey: ["mcp"], queryFn: () => api.get<McpServer[]>("/api/mcp/servers") });
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

export function useSessions() {
  return useQuery({ queryKey: ["sessions"], queryFn: () => api.get<Session[]>("/api/sessions") });
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

export function useUsageSummary() {
  return useQuery({ queryKey: ["usage"], queryFn: () => api.get<UsageSummary[]>("/api/debug/usage") });
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
  });
}
export function useUploadFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const token = getAccessToken();
      const res = await fetch("/api/files/upload", {
        method: "POST",
        body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
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
    queryFn: () =>
      api.get<UserProfile>("/api/auth/me"),
    enabled,
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
    mutationFn: (body: { email: string; role: string }) =>
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

export function useApprovals(enabled: boolean = true) {
  return useQuery({
    queryKey: ["approvals"],
    queryFn: () => api.get<ApprovalRequest[]>("/api/approvals"),
    refetchInterval: enabled ? 60000 : false,
    refetchIntervalInBackground: false,
    enabled,
  });
}

export function useDecideApproval() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, decision, reason = "" }: { id: string; decision: "approved" | "rejected"; reason?: string }) =>
      api.post<ApprovalRequest>(`/api/approvals/${id}/decide`, { decision, reason }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["approvals"] }),
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
      return status && ["succeeded", "failed", "diverged", "cancelled", "waiting_approval"].includes(status)
        ? false
        : 2000;
    },
  });
}

export function useChatRun(runId: string | null) {
  return useQuery({
    queryKey: ["chat-run", runId],
    enabled: !!runId,
    queryFn: () => api.get<ChatRunDetail>(`/api/chat/runs/${runId}`),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ["succeeded", "failed", "diverged", "cancelled", "waiting_approval"].includes(status)
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

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { display_name?: string; old_password?: string; new_password?: string }) =>
      api.patch<UserProfile>("/api/auth/me", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profile"] }),
  });
}
