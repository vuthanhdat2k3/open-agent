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
// - platform_admin: Multi-tenant Platform & Tenant Provisioning (Organizations)
// - org_admin (admin): Tenant Administration (Members, Providers, Quotas, Knowledge Base, Usage Logs, Email Ops)
// - operator: AI Studio & Builder (Agent Studio, Workflow Builder, MCP, Knowledge Base, Workspace, Evaluations, Approvals)
// - user: End-user Consumer (Chat Assistant with 📎 attachments, Run Workflow, Smart Inbox, Automations, Research Cases, My Approvals)
export const navGroups: NavGroup[] = [
  // --- Platform Admin ---
  {
    title: "Platform Administration",
    roles: ["platform_admin"],
    items: [
      { href: "/organizations", label: "Tenant Directory & Organizations", icon: Users, roles: ["platform_admin"], platformOnly: true },
    ],
  },

  // --- Organization Admin (Members, Quotas, System Governance, Email Ops) ---
  {
    title: "Organization & Governance",
    roles: ["admin", "org_admin"],
    items: [
      { href: "/settings/members", label: "Identity & Access Management (IAM)", icon: Users, roles: ["admin", "org_admin"], permission: "orgs:manage" },
      { href: "/settings/quotas", label: "Resource & Budget Governance", icon: Gauge, roles: ["admin", "org_admin"], permission: "quota:usage" },
      { href: "/admin/email-intelligence", label: "Email Gateway & Security Operations", icon: SlidersHorizontal, roles: ["admin", "org_admin"], permission: "admin:email-intelligence" },
      { href: "/debug", label: "Enterprise Audit & Compliance Logs", icon: Bug, roles: ["admin", "org_admin"], permission: "orgs:manage" },
    ],
  },

  // --- Operator (AI Engineer / AI Operations Stack) ---
  {
    title: "AI Studio & Engineering",
    roles: ["operator"],
    items: [
      { href: "/agents", label: "Agent Studio & Persona Catalog", icon: Bot, roles: ["operator"], permission: "agents:read" },
      { href: "/providers", label: "LLM Gateway & Model Benchmarks", icon: Server, roles: ["operator"], permission: "providers:read" },
      { href: "/workflows", label: "Multi-Agent Workflow Orchestrator", icon: Workflow, roles: ["operator"], permission: "workflows:read" },
      { href: "/mcp", label: "Tool Registry & MCP Integrations", icon: Plug, roles: ["operator"], permission: "mcp:read" },
      { href: "/files", label: "Enterprise Knowledge Base (RAG)", icon: FolderKanban, roles: ["operator"], permission: "files:read" },
    ],
  },
  {
    title: "Testing & Observability",
    roles: ["operator"],
    items: [
      { href: "/debug", label: "LLM Observability & Execution Traces", icon: Bug, roles: ["operator"], permission: "usage:read" },
      { href: "/workspace", label: "Code Execution Sandbox", icon: FolderKanban, roles: ["operator"], permission: "files:read" },
      { href: "/evaluations", label: "Model Quality & Agent Evaluations", icon: FlaskConical, roles: ["operator"], permission: "evaluations:read" },
      { href: "/approvals", label: "Technical Action Approvals", icon: ShieldCheck, roles: ["operator"], permission: "approvals:read" },
    ],
  },

  // --- User (Business Consumer / End-User) ---
  {
    title: "AI Workplace",
    roles: ["user"],
    items: [
      { href: "/chat", label: "Executive Copilot & Assistant", icon: MessageSquare, roles: ["user"] },
      { href: "/run-workflow", label: "Workflow Execution Center", icon: PlayCircle, roles: ["user"], permission: "workflows:run" },
      { href: "/integrations", label: "Connected Accounts & OAuth", icon: Plug, roles: ["user"], permission: "ci:personal:manage" },
      { href: "/email-intelligence", label: "Smart Inbox & Email Triage", icon: Bell, roles: ["user"], permission: "ci:personal:manage" },
      { href: "/automations", label: "Automated Routines & Schedules", icon: Zap, roles: ["user"], permission: "workflows:read" },
      { href: "/customer-intelligence", label: "Client Dossiers & Briefings", icon: Building2, roles: ["user"], permission: "ci:read" },
      { href: "/approvals", label: "Action Approvals & Usage Quota", icon: ShieldCheck, roles: ["user"], permission: "approvals:read" },
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
