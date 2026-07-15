"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  Agent,
  AgentToolInfo,
  McpServer,
  Message,
  Model,
  Provider,
  Session,
  UsageSummary,
  Workflow,
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}
export function useSessionMessages(sessionId: string | null) {
  return useQuery({
    queryKey: ["messages", sessionId],
    enabled: !!sessionId,
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
