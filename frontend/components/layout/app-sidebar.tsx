"use client";

import Link from "next/link";
import { Bot, PanelLeftClose, PanelLeft } from "lucide-react";
import { usePathname } from "next/navigation";
import type { QueryClient } from "@tanstack/react-query";
import { useApprovals } from "@/hooks";
import { OrgSwitcher } from "@/components/org-switcher";
import { UserNav } from "@/components/user-nav";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { isActive, navGroups, prefetchTab } from "./navigation";

export function Brand({ collapsed }: { collapsed: boolean }) {
  return (
    <div className="space-y-3 p-3">
      <div className={cn("flex items-center gap-3", collapsed && "justify-center")}> 
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-primary/30 bg-primary text-primary-foreground shadow-card">
          <Bot className="h-5 w-5" aria-hidden="true" />
        </div>
        {!collapsed && <div className="min-w-0"><div className="truncate text-base font-bold tracking-tight text-foreground">OpenAgent</div><div className="truncate text-xs text-muted-foreground">Agent Platform</div></div>}
      </div>
      <OrgSwitcher collapsed={collapsed} />
    </div>
  );
}

export function SidebarNav({ collapsed, onNavigate, queryClient }: { collapsed: boolean; onNavigate?: () => void; queryClient: QueryClient }) {
  const pathname = usePathname();
  const approvals = useApprovals(true);
  const pending = approvals.data?.length ?? 0;
  return (
    <nav aria-label="Primary navigation" className="flex flex-1 flex-col gap-5 overflow-y-auto px-3 py-3">
      {navGroups.map((group) => (
        <div key={group.title} className="space-y-1">
          {!collapsed && <div className="px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">{group.title}</div>}
          {group.items.map((item) => {
            const Icon = item.icon;
            const active = isActive(pathname, item.href);
            return (
              <Link key={item.href} href={item.href} onClick={onNavigate} onMouseEnter={() => prefetchTab(queryClient, item.href)} onFocus={() => prefetchTab(queryClient, item.href)} aria-current={active ? "page" : undefined} title={collapsed ? item.label : undefined} className={cn("group relative flex min-h-10 items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", collapsed && "justify-center px-0", active ? "border border-primary/20 bg-primary/10 font-semibold text-primary" : "text-muted-foreground hover:bg-accent hover:text-foreground")}>
                <Icon className="h-[18px] w-[18px] shrink-0" aria-hidden="true" />
                {!collapsed && <span className="truncate">{item.label}</span>}
                {!collapsed && item.href === "/approvals" && pending > 0 && <span className="ml-auto rounded-full bg-destructive px-1.5 py-0.5 text-[10px] font-bold text-destructive-foreground" aria-label={`${pending} pending approvals`}>{pending}</span>}
                {active && <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-primary" aria-hidden="true" />}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

export function SidebarFooter({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return (
    <div className="space-y-2 border-t border-border/70 p-2">
      <UserNav collapsed={collapsed} />
      <div className="flex items-center justify-between px-2 pt-1">
        {!collapsed && <span className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">v0.1.0</span>}
        <Button variant="ghost" size="icon" className={cn("h-9 w-9 text-muted-foreground hover:text-foreground", collapsed && "mx-auto")} onClick={onToggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {collapsed ? <PanelLeft className="h-4 w-4" aria-hidden="true" /> : <PanelLeftClose className="h-4 w-4" aria-hidden="true" />}
        </Button>
      </div>
    </div>
  );
}

export function AppSidebar({ collapsed, queryClient }: { collapsed: boolean; queryClient: QueryClient }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Brand collapsed={collapsed} />
      <SidebarNav collapsed={collapsed} queryClient={queryClient} />
    </div>
  );
}

