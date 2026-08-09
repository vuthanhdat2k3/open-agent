import type { QueryClient, QueryKey } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Agent, AgentToolInfo, McpServer, Model, Provider, Session, SandboxExecution, UploadedFile, UsageSummary, Workflow as WorkflowT, WorkspaceArtifact } from "@/types";
import {
  Activity, Bot, Bug, CalendarDays, Cpu, FileUp, FlaskConical, FolderKanban,
  Gauge, LayoutDashboard, MessageSquare, Plug, Server, ShieldCheck, Users, Workflow,
  type LucideIcon,
} from "lucide-react";

export interface NavItem { href: string; label: string; icon: LucideIcon; adminOnly?: boolean; }
export interface NavGroup { title: string; items: NavItem[]; }

// adminOnly items configure/operate the product (agents, workflows authoring,
// providers, models, MCP, integrations, evaluations, members, debug) - a
// plain "user" only ever consumes it (Chat, Dashboard, and their own
// Workspace/Files/Approvals/Quotas data). See the RBAC design spec.
export const navGroups: NavGroup[] = [
  { title: "Overview", items: [
    { href: "/", label: "Dashboard", icon: LayoutDashboard },
    { href: "/chat", label: "Chat", icon: MessageSquare },
  ] },
  { title: "AI Infrastructure", items: [
    { href: "/agents", label: "Agents", icon: Bot, adminOnly: true },
    { href: "/workflows", label: "Workflows", icon: Workflow, adminOnly: true },
    { href: "/workspace", label: "Workspace", icon: FolderKanban },
    { href: "/mcp", label: "MCP Servers", icon: Plug, adminOnly: true },
    { href: "/integrations", label: "Integrations", icon: CalendarDays, adminOnly: true },
    { href: "/models", label: "Models", icon: Cpu, adminOnly: true },
    { href: "/providers", label: "Providers", icon: Server, adminOnly: true },
    { href: "/files", label: "Files", icon: FileUp },
  ] },
  { title: "Governance & Ops", items: [
    { href: "/approvals", label: "Approvals", icon: ShieldCheck },
    { href: "/evaluations", label: "Evaluations", icon: FlaskConical, adminOnly: true },
    { href: "/settings/quotas", label: "Quotas", icon: Gauge },
    { href: "/settings/members", label: "Members", icon: Users, adminOnly: true },
    { href: "/debug", label: "Debug", icon: Bug, adminOnly: true },
  ] },
];

export const allNavItems = navGroups.flatMap((group) => group.items);
export function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

type PrefetchSpec = { queryKey: QueryKey; queryFn: () => Promise<unknown> };
const tabQueries: Record<string, PrefetchSpec[]> = {
  "/": [
    { queryKey: ["usage"], queryFn: () => api.get<UsageSummary[]>("/api/debug/usage") },
    { queryKey: ["providers"], queryFn: () => api.get<Provider[]>("/api/providers") },
    { queryKey: ["models"], queryFn: () => api.get<Model[]>("/api/models") },
    { queryKey: ["agents"], queryFn: () => api.get<Agent[]>("/api/agents") },
    { queryKey: ["workflows"], queryFn: () => api.get<WorkflowT[]>("/api/workflows") },
    { queryKey: ["mcp"], queryFn: () => api.get<McpServer[]>("/api/mcp/servers") },
  ],
  "/providers": [{ queryKey: ["providers"], queryFn: () => api.get<Provider[]>("/api/providers") }],
  "/models": [{ queryKey: ["models"], queryFn: () => api.get<Model[]>("/api/models") }],
  "/agents": [
    { queryKey: ["agents"], queryFn: () => api.get<Agent[]>("/api/agents") },
    { queryKey: ["models"], queryFn: () => api.get<Model[]>("/api/models") },
    { queryKey: ["agent-tools"], queryFn: () => api.get<AgentToolInfo[]>("/api/agents/tools") },
  ],
  "/mcp": [{ queryKey: ["mcp"], queryFn: () => api.get<McpServer[]>("/api/mcp/servers") }],
  "/workflows": [{ queryKey: ["workflows"], queryFn: () => api.get<WorkflowT[]>("/api/workflows") }],
  "/workspace": [
    { queryKey: ["workspace-artifacts"], queryFn: () => api.get<WorkspaceArtifact[]>("/api/workspace/artifacts") },
    { queryKey: ["sandbox-executions"], queryFn: () => api.get<SandboxExecution[]>("/api/workspace/executions") },
  ],
  "/chat": [{ queryKey: ["sessions"], queryFn: () => api.get<Session[]>("/api/sessions") }],
  "/debug": [
    { queryKey: ["debug-sessions"], queryFn: () => api.get<Session[]>("/api/debug/sessions") },
    { queryKey: ["usage"], queryFn: () => api.get<UsageSummary[]>("/api/debug/usage") },
  ],
  "/files": [{ queryKey: ["files"], queryFn: () => api.get<UploadedFile[]>("/api/files") }],
};

export function prefetchTab(queryClient: QueryClient, href: string) {
  tabQueries[href]?.forEach((spec) => queryClient.prefetchQuery({ queryKey: spec.queryKey, queryFn: spec.queryFn }));
}
