import type { QueryClient, QueryKey } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Agent, AgentToolInfo, McpServer, Model, Provider, Session, SandboxExecution, UploadedFile, UsageSummary, Workflow as WorkflowT, WorkspaceArtifact } from "@/types";
import {
  Bell, Bot, Bug, Building2, CalendarDays, Cpu, FileUp, FlaskConical, FolderKanban,
  Gauge, LayoutDashboard, MessageSquare, PlayCircle, Plug, Search, Server, SlidersHorizontal, ShieldCheck, Users, Workflow, Zap,
  type LucideIcon,
} from "lucide-react";

export type UserRole = "platform_admin" | "admin" | "org_admin" | "operator" | "user";

export interface NavItem {
  href: string;
  label: string;
  i18nKey?: string;
  icon: LucideIcon;
  permission?: string;
  platformOnly?: boolean;
  roles?: UserRole[];
}

export interface NavGroup {
  title: string;
  i18nKey?: string;
  roles?: UserRole[];
  items: NavItem[];
}

export const navGroups: NavGroup[] = [
  // --- Platform Admin ---
  {
    title: "Platform Admin",
    i18nKey: "nav.groups.platformAdmin",
    roles: ["platform_admin"],
    items: [
      { href: "/organizations", label: "Organizations", i18nKey: "nav.organizations", icon: Users, roles: ["platform_admin"], platformOnly: true },
    ],
  },

  // --- Organization Admin (Members, Quotas, System Governance, Email Ops) ---
  {
    title: "Administration",
    i18nKey: "nav.groups.systemSettings",
    roles: ["admin", "org_admin"],
    items: [
      { href: "/settings/members", label: "Members", i18nKey: "nav.members", icon: Users, roles: ["admin", "org_admin"], permission: "orgs:manage" },
      { href: "/settings/quotas", label: "Quotas", i18nKey: "nav.quotas", icon: Gauge, roles: ["admin", "org_admin"], permission: "quota:usage" },
      { href: "/admin/email-intelligence", label: "Email Gateway", i18nKey: "nav.emailGateway", icon: SlidersHorizontal, roles: ["admin", "org_admin"], permission: "admin:email-intelligence" },
      { href: "/debug", label: "Audit Logs", i18nKey: "nav.auditLogs", icon: Bug, roles: ["admin", "org_admin"], permission: "orgs:manage" },
    ],
  },

  // --- Operator (AI Engineer / AI Operations Stack) ---
  {
    title: "AI Studio",
    i18nKey: "nav.groups.agenticWorkflows",
    roles: ["operator"],
    items: [
      { href: "/agents", label: "Agents", i18nKey: "nav.agents", icon: Bot, roles: ["operator"], permission: "agents:read" },
      { href: "/providers", label: "Providers", i18nKey: "nav.providers", icon: Server, roles: ["operator"], permission: "providers:read" },
      { href: "/workflows", label: "Workflows", i18nKey: "nav.workflows", icon: Workflow, roles: ["operator"], permission: "workflows:read" },
      { href: "/mcp", label: "MCP Servers", i18nKey: "nav.mcpServers", icon: Plug, roles: ["operator"], permission: "mcp:read" },
      { href: "/files", label: "Knowledge Base", i18nKey: "nav.knowledgeBase", icon: FolderKanban, roles: ["operator"], permission: "files:read" },
    ],
  },
  {
    title: "Observability",
    i18nKey: "nav.groups.governanceAudit",
    roles: ["operator"],
    items: [
      { href: "/debug", label: "Audit Logs", i18nKey: "nav.auditLogs", icon: Bug, roles: ["operator"], permission: "usage:read" },
      { href: "/workspace", label: "Sandbox", i18nKey: "nav.sandbox", icon: FolderKanban, roles: ["operator"], permission: "files:read" },
      { href: "/evaluations", label: "Evaluations", i18nKey: "nav.evaluations", icon: FlaskConical, roles: ["operator"], permission: "evaluations:read" },
      { href: "/approvals", label: "Approvals", i18nKey: "nav.approvals", icon: ShieldCheck, roles: ["operator"], permission: "approvals:read" },
    ],
  },

  // --- User (Business Consumer / End-User) ---
  {
    title: "Workspace",
    i18nKey: "nav.groups.workspace",
    roles: ["user"],
    items: [
      { href: "/chat", label: "Chat", i18nKey: "nav.chat", icon: MessageSquare, roles: ["user"] },
      { href: "/run-workflow", label: "Run Workflow", i18nKey: "nav.runWorkflow", icon: PlayCircle, roles: ["user"], permission: "workflows:run" },
      { href: "/integrations", label: "Integrations", i18nKey: "nav.integrations", icon: Plug, roles: ["user"], permission: "ci:personal:manage" },
      { href: "/email-intelligence", label: "Email Intelligence", i18nKey: "nav.emailIntelligence", icon: Bell, roles: ["user"], permission: "ci:personal:manage" },
      { href: "/automations", label: "Automations", i18nKey: "nav.automations", icon: Zap, roles: ["user"], permission: "workflows:read" },
      { href: "/customer-intelligence", label: "Customer Intelligence", i18nKey: "nav.customerIntelligence", icon: Building2, roles: ["user"], permission: "ci:read" },
      { href: "/approvals", label: "Approvals", i18nKey: "nav.approvals", icon: ShieldCheck, roles: ["user"], permission: "approvals:read" },
    ],
  },
];

export const allNavItems = navGroups.flatMap((group) => group.items);
export function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  const active = allNavItems
    .filter((item) => pathname === item.href || pathname.startsWith(`${item.href}/`))
    .sort((a, b) => b.href.length - a.href.length)[0];
  return active?.href === href;
}

type PrefetchSpec = { queryKey: QueryKey; queryFn: () => Promise<unknown> };
const tabQueries: Record<string, PrefetchSpec[]> = {
  "/": [
    { queryKey: ["agents"], queryFn: () => api.get<Agent[]>("/api/agents") },
    { queryKey: ["workflows"], queryFn: () => api.get<WorkflowT[]>("/api/workflows") },
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
  "/run-workflow": [{ queryKey: ["workflows"], queryFn: () => api.get<WorkflowT[]>("/api/workflows") }],
  "/workspace": [
    { queryKey: ["workspace-artifacts"], queryFn: () => api.get<WorkspaceArtifact[]>("/api/workspace/artifacts") },
    { queryKey: ["sandbox-executions"], queryFn: () => api.get<SandboxExecution[]>("/api/workspace/executions") },
  ],
  "/chat": [{ queryKey: ["sessions"], queryFn: () => api.get<Session[]>("/api/sessions") }],
  "/customer-intelligence": [{ queryKey: ["customer-intelligence", "cases"], queryFn: () => api.get("/api/customer-intelligence/cases") }],
  "/email-intelligence": [{ queryKey: ["email-intelligence", "notifications"], queryFn: () => api.get("/api/customer-intelligence/notifications?limit=100") }],
  "/automations": [{ queryKey: ["workflow-catalog"], queryFn: () => api.get("/api/workflow-catalog/templates") }],
  "/debug": [
    { queryKey: ["debug-sessions"], queryFn: () => api.get<Session[]>("/api/debug/sessions") },
    { queryKey: ["usage"], queryFn: () => api.get<UsageSummary[]>("/api/debug/usage") },
  ],
  "/files": [{ queryKey: ["files"], queryFn: () => api.get<UploadedFile[]>("/api/files") }],
};

export function prefetchTab(queryClient: QueryClient, href: string) {
  tabQueries[href]?.forEach((spec) => queryClient.prefetchQuery({ queryKey: spec.queryKey, queryFn: spec.queryFn }));
}
