"use client";

import "./globals.css";
import "katex/dist/katex.min.css";
import * as React from "react";
import { QueryClient, QueryClientProvider, type QueryKey } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  Agent,
  AgentToolInfo,
  McpServer,
  Model,
  Provider,
  Session,
  UploadedFile,
  UsageSummary,
  Workflow as WorkflowT,
} from "@/types";
import { Toaster } from "sonner";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Fira_Sans, Fira_Code } from "next/font/google";
import {
  LayoutDashboard,
  Server,
  Cpu,
  Bot,
  Plug,
  Workflow,
  MessageSquare,
  FileUp,
  Bug,
  FlaskConical,
  Gauge,
  ShieldCheck,
  Users,
  User as UserIcon,
  Menu,
  PanelLeftClose,
  PanelLeft,
  X,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserNav } from "@/components/user-nav";
import { Button } from "@/components/ui/button";
import { getAccessToken, refreshAccessToken, subscribeAuth } from "@/lib/auth";
import { useApprovals } from "@/hooks";

const sans = Fira_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});
const mono = Fira_Code({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

const navGroups: NavGroup[] = [
  {
    title: "Overview",
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard },
      { href: "/chat", label: "Chat", icon: MessageSquare },
    ],
  },
  {
    title: "AI Infrastructure",
    items: [
      { href: "/agents", label: "Agents", icon: Bot },
      { href: "/workflows", label: "Workflows", icon: Workflow },
      { href: "/mcp", label: "MCP Servers", icon: Plug },
      { href: "/models", label: "Models", icon: Cpu },
      { href: "/providers", label: "Providers", icon: Server },
      { href: "/files", label: "Files", icon: FileUp },
    ],
  },
  {
    title: "Governance & Ops",
    items: [
      { href: "/approvals", label: "Approvals", icon: ShieldCheck },
      { href: "/evaluations", label: "Evaluations", icon: FlaskConical },
      { href: "/settings/quotas", label: "Quotas", icon: Gauge },
      { href: "/settings/members", label: "Members", icon: Users },
      { href: "/debug", label: "Debug", icon: Bug },
    ],
  },
];

const allNavItems = navGroups.flatMap((g) => g.items);

// Warm a tab's data before the user clicks it (on hover/focus) so the first
// visit also renders instantly instead of waiting on the network.
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
  "/chat": [{ queryKey: ["sessions"], queryFn: () => api.get<Session[]>("/api/sessions") }],
  "/debug": [
    { queryKey: ["debug-sessions"], queryFn: () => api.get<Session[]>("/api/debug/sessions") },
    { queryKey: ["usage"], queryFn: () => api.get<UsageSummary[]>("/api/debug/usage") },
  ],
  "/files": [{ queryKey: ["files"], queryFn: () => api.get<UploadedFile[]>("/api/files") }],
};

function prefetchTab(qc: QueryClient, href: string) {
  tabQueries[href]?.forEach((spec) =>
    qc.prefetchQuery({ queryKey: spec.queryKey, queryFn: spec.queryFn as () => Promise<unknown> }),
  );
}

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}

function SidebarNav({
  collapsed,
  onNavigate,
  queryClient,
}: {
  collapsed: boolean;
  onNavigate?: () => void;
  queryClient: QueryClient;
}) {
  const pathname = usePathname();
  const publicRoute = pathname === "/login" || pathname === "/register" || pathname.startsWith("/oauth/");
  const approvals = useApprovals(!publicRoute);
  const pending = approvals.data?.length ?? 0;
  return (
    <nav className="flex flex-1 flex-col gap-5 overflow-y-auto px-3 py-3">
      {navGroups.map((group, groupIdx) => (
        <div key={groupIdx} className="space-y-1">
          {!collapsed && (
            <div className="px-3 text-[11px] font-bold uppercase tracking-wider text-muted-foreground/60">
              {group.title}
            </div>
          )}
          {group.items.map((item) => {
            const Icon = item.icon;
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onNavigate}
                onMouseEnter={() => prefetchTab(queryClient, item.href)}
                onFocus={() => prefetchTab(queryClient, item.href)}
                aria-current={active ? "page" : undefined}
                title={collapsed ? item.label : undefined}
                className={cn(
                  "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200 ease-out-expo",
                  collapsed && "justify-center px-0",
                  active
                    ? "bg-primary/10 text-primary shadow-inner-edge font-semibold"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                <Icon
                  className={cn(
                    "h-[18px] w-[18px] shrink-0 transition-transform duration-200 ease-out-expo group-hover:scale-110",
                    active && "scale-105 text-primary",
                  )}
                />
                {!collapsed && <span className="truncate">{item.label}</span>}
                {!collapsed && item.href === "/approvals" && pending > 0 && (
                  <span className="ml-auto rounded-full bg-destructive px-1.5 py-0.5 text-[10px] font-bold text-destructive-foreground">
                    {pending}
                  </span>
                )}
                {active && (
                  <span
                    className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-primary"
                    aria-hidden="true"
                  />
                )}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [ready, setReady] = React.useState(false);
  const publicRoute = pathname === "/login" || pathname === "/register" || pathname.startsWith("/oauth/");

  React.useEffect(() => {
    const unsub = subscribeAuth(() => setReady(true));
    if (getAccessToken()) {
      setReady(true);
      return unsub;
    }
    if (publicRoute) {
      setReady(true);
      return unsub;
    }
    setReady(false);
    refreshAccessToken().finally(() => setReady(true));
    return unsub;
  }, [publicRoute, pathname]);

  React.useEffect(() => {
    if (ready && !publicRoute && !getAccessToken()) {
      window.location.replace("/login");
    }
  }, [ready, publicRoute, pathname]);

  if (!ready && !publicRoute) {
    return <div className="p-6 text-sm text-muted-foreground">Preparing session...</div>;
  }
  return <>{children}</>;
}

import { OrgSwitcher } from "@/components/org-switcher";

function Brand({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="space-y-2 p-3">
      <div className={cn("flex items-center gap-3", collapsed && "justify-center px-0")}>
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary to-primary/60 shadow-diffuse">
          <Bot className="h-5 w-5 text-primary-foreground" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="truncate text-base font-bold tracking-tight">OpenAgent</div>
            <div className="truncate text-xs text-muted-foreground">Agent Platform</div>
          </div>
        )}
      </div>
      <OrgSwitcher collapsed={collapsed} />
    </div>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(() =>
    new QueryClient({
      defaultOptions: {
        queries: {
          retry: 1,
          refetchOnWindowFocus: false,
          // Without staleTime the cache is considered stale immediately, so navigating
          // to a tab (which remounts the page in the App Router) refetches every time
          // and shows a loading spinner. Keeping data fresh for a minute means a tab
          // you just left renders instantly from cache on return.
          staleTime: 30_000,
          // Keep cached data around longer so background refetches stay rare.
          gcTime: 10 * 60_000,
        },
      },
    }),
  );
  const pathname = usePathname();
  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileOpen, setMobileOpen] = React.useState(false);

  const title = allNavItems.find((n) => isActive(pathname, n.href))?.label ?? "OpenAgent";

  const isPublic = pathname === "/login" || pathname === "/register" || pathname.startsWith("/oauth/");

  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} dark`}>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <QueryClientProvider client={client}>
          <AuthGate>
            {isPublic ? (
              <main className="min-h-screen">{children}</main>
            ) : (
              <div className="relative z-10 flex min-h-screen">
                {/* Desktop sidebar */}
                <aside
                  className={cn(
                    "sticky top-0 hidden h-screen shrink-0 flex-col border-r border-border bg-card/40 backdrop-blur-xl transition-[width] duration-300 ease-out-expo lg:flex",
                    collapsed ? "w-[76px]" : "w-64",
                  )}
                >
                  <Brand collapsed={collapsed} />
                  <SidebarNav collapsed={collapsed} queryClient={client} />
                  
                  {/* User Profile Avatar Footer */}
                  <div className="border-t border-border/60 p-2 space-y-2">
                    <UserNav collapsed={collapsed} />
                    <div className="flex items-center justify-between px-2 pt-1">
                      {!collapsed && (
                        <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/50">
                          v0.1.0
                        </span>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className={cn("h-7 w-7 text-muted-foreground hover:text-foreground", collapsed && "mx-auto")}
                        onClick={() => setCollapsed((c) => !c)}
                        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                      >
                        {collapsed ? <PanelLeft className="h-3.5 w-3.5" /> : <PanelLeftClose className="h-3.5 w-3.5" />}
                      </Button>
                    </div>
                  </div>
                </aside>

                {/* Mobile drawer */}
                {mobileOpen && (
                  <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
                    <div
                      className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                      onClick={() => setMobileOpen(false)}
                    />
                    <aside className="absolute left-0 top-0 flex h-full w-64 flex-col border-r border-border bg-card">
                      <div className="flex items-center justify-between pr-3">
                        <Brand collapsed={false} />
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-muted-foreground"
                          onClick={() => setMobileOpen(false)}
                          aria-label="Close navigation"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                      <SidebarNav
                        collapsed={false}
                        onNavigate={() => setMobileOpen(false)}
                        queryClient={client}
                      />
                      <div className="border-t border-border/60 p-3 mt-auto">
                        <UserNav collapsed={false} />
                      </div>
                    </aside>
                  </div>
                )}

                <div className="flex min-w-0 flex-1 flex-col">
                  <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-border bg-background/80 px-4 backdrop-blur lg:px-6">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="lg:hidden"
                      onClick={() => setMobileOpen(true)}
                      aria-label="Open navigation"
                    >
                      <Menu className="h-5 w-5" />
                    </Button>
                    <h1 className="min-w-0 flex-1 truncate text-sm font-semibold tracking-tight">{title}</h1>
                    <ThemeToggle />
                  </header>

                  <main className="flex-1 overflow-x-hidden">
                    {/* key=pathname replays the entrance animation on every navigation */}
                    <div
                      key={pathname}
                      className="mx-auto w-full max-w-7xl animate-fade-in px-4 py-6 lg:px-8 lg:py-8"
                    >
                      {children}
                    </div>
                  </main>
                </div>
              </div>
            )}
          </AuthGate>
          <Toaster richColors closeButton />
        </QueryClientProvider>
      </body>
    </html>
  );
}
