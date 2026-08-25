import type { QueryClient, QueryKey } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Agent, AgentToolInfo, McpServer, Model, Provider, Session, SandboxExecution, UploadedFile, UsageSummary, Workflow as WorkflowT, WorkspaceArtifact } from "@/types";
import {
  Bell, Bot, Bug, CalendarDays, Cpu, FileUp, FlaskConical, FolderKanban,
  Gauge, LayoutDashboard, MessageSquare, PlayCircle, Plug, Search, Server, SlidersHorizontal, ShieldCheck, Users, Workflow, Zap,
  type LucideIcon,
} from "lucide-react";

export type UserRole = "platform_admin" | "admin" | "org_admin" | "operator" | "user";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  permission?: string;
  platformOnly?: boolean;
  roles?: UserRole[];
}

export interface NavGroup {
  title: string;
  roles?: UserRole[];
  items: NavItem[];
}

// Tailored navigation per role persona:
// - platform_admin: Multi-tenant Platform & Infra Ops (Organizations, Global Providers, Audit)
// - org_admin (admin): Tenant Administration (Members, Providers, Models, Quotas, Email Ops, Debug)
// - operator: AI Studio & Builder (Agents, Workflows, MCP, Workspace, Evaluations, Approvals)
// - user: End-user Consumer (Chat, Run Workflow, Smart Inbox, Automations, Files, Personal Quota)
export const navGroups: NavGroup[] = [
  // --- Platform Admin ---
  {
    title: "Platform Infrastructure",
    roles: ["platform_admin"],
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard, roles: ["platform_admin"] },
      { href: "/organizations", label: "Organizations", icon: Users, roles: ["platform_admin"], platformOnly: true },
      { href: "/providers", label: "Global Providers", icon: Server, roles: ["platform_admin"], permission: "providers:read" },
      { href: "/debug", label: "System Debug & Logs", icon: Bug, roles: ["platform_admin"], permission: "orgs:manage" },
    ],
  },

  // --- Organization Admin ---
  {
    title: "Organization Management",
    roles: ["admin", "org_admin"],
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard, roles: ["admin", "org_admin"] },
      { href: "/settings/members", label: "Members & Access", icon: Users, roles: ["admin", "org_admin"], permission: "orgs:manage" },
      { href: "/providers", label: "AI Providers", icon: Server, roles: ["admin", "org_admin"], permission: "providers:read" },
      { href: "/models", label: "Models Configuration", icon: Cpu, roles: ["admin", "org_admin"], permission: "models:read" },
      { href: "/settings/quotas", label: "Quotas & Budgets", icon: Gauge, roles: ["admin", "org_admin"], permission: "quota:usage" },
      { href: "/admin/email-intelligence", label: "Email Operations", icon: SlidersHorizontal, roles: ["admin", "org_admin"], permission: "admin:email-intelligence" },
      { href: "/debug", label: "Org Debug & Logs", icon: Bug, roles: ["admin", "org_admin"], permission: "orgs:manage" },
    ],
  },

  // --- Operator (AI Engineer / Builder) ---
  {
    title: "AI Studio & Builder",
    roles: ["operator"],
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard, roles: ["operator"] },
      { href: "/agents", label: "Agents", icon: Bot, roles: ["operator"], permission: "agents:read" },
      { href: "/workflows", label: "Workflows", icon: Workflow, roles: ["operator"], permission: "workflows:read" },
      { href: "/mcp", label: "MCP Servers", icon: Plug, roles: ["operator"], permission: "mcp:read" },
    ],
  },
  {
    title: "Testing & Governance",
    roles: ["operator"],
    items: [
      { href: "/workspace", label: "Workspace", icon: FolderKanban, roles: ["operator"], permission: "files:read" },
      { href: "/evaluations", label: "Evaluations", icon: FlaskConical, roles: ["operator"], permission: "evaluations:read" },
      { href: "/approvals", label: "Technical Approvals", icon: ShieldCheck, roles: ["operator"], permission: "approvals:read" },
      { href: "/models", label: "Models Explorer", icon: Cpu, roles: ["operator"], permission: "models:read" },
    ],
  },

  // --- User (Business Consumer / End-User) ---
  {
    title: "AI Assistant & Work",
    roles: ["user"],
    items: [
      { href: "/chat", label: "Chat", icon: MessageSquare, roles: ["user"] },
      { href: "/run-workflow", label: "Run Workflow", icon: PlayCircle, roles: ["user"], permission: "workflows:run" },
      { href: "/email-intelligence", label: "Smart Inbox", icon: Bell, roles: ["user"], permission: "ci:personal:manage" },
      { href: "/automations", label: "Automations", icon: Zap, roles: ["user"], permission: "workflows:read" },
      { href: "/email-intelligence/rules", label: "Automation Rules", icon: SlidersHorizontal, roles: ["user"], permission: "ci:personal:manage" },
      { href: "/customer-intelligence", label: "Research Cases", icon: Search, roles: ["user"], permission: "ci:read" },
    ],
  },
  {
    title: "Personal Workspace",
    roles: ["user"],
    items: [
      { href: "/integrations", label: "Integrations", icon: CalendarDays, roles: ["user"], permission: "ci:personal:manage" },
      { href: "/files", label: "Files", icon: FileUp, roles: ["user"], permission: "files:read" },
      { href: "/approvals", label: "My Approvals", icon: ShieldCheck, roles: ["user"], permission: "approvals:read" },
      { href: "/settings/quotas", label: "My Quota", icon: Gauge, roles: ["user"], permission: "quota:usage" },
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
