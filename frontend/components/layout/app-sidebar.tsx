"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { QueryClient } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import { useApprovals, useCurrentRole } from "@/hooks";
import { OrgSwitcher } from "@/components/org-switcher";
import { UserNav } from "@/components/user-nav";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import { isActive, navGroups, prefetchTab } from "./navigation";

export function AppSidebar({ queryClient }: { queryClient: QueryClient }) {
  const pathname = usePathname();
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const approvals = useApprovals(true);
  const pending = approvals.data?.length ?? 0;
  const role = useCurrentRole();

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="gap-3">
        <div className="flex items-center gap-3 px-1 py-1 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:gap-0">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-primary/20 bg-primary text-primary-foreground shadow-card">
            <Bot className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0 group-data-[collapsible=icon]:hidden">
            <div className="truncate text-base font-bold tracking-tight text-foreground">OpenAgent</div>
            <div className="truncate text-xs text-muted-foreground">Agent Platform</div>
          </div>
        </div>
        <div className="group-data-[collapsible=icon]:hidden">
          <OrgSwitcher collapsed={false} />
        </div>
      </SidebarHeader>

      <SidebarContent>
        {navGroups.map((group) => {
          const items = role === "admin" ? group.items : group.items.filter((item) => !item.adminOnly);
          if (items.length === 0) return null;
          return (
          <SidebarGroup key={group.title}>
            <SidebarGroupLabel>{group.title}</SidebarGroupLabel>
            <SidebarMenu>
              {items.map((item) => {
                const Icon = item.icon;
                const active = isActive(pathname, item.href);
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={active}
                      tooltip={item.label}
                      onMouseEnter={() => prefetchTab(queryClient, item.href)}
                      onFocus={() => prefetchTab(queryClient, item.href)}
                    >
                      <Link href={item.href} aria-current={active ? "page" : undefined}>
                        <Icon aria-hidden="true" />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                    {item.href === "/approvals" && pending > 0 && (
                      <SidebarMenuBadge aria-label={`${pending} pending approvals`}>{pending}</SidebarMenuBadge>
                    )}
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroup>
          );
        })}
      </SidebarContent>

      <SidebarFooter>
        <UserNav collapsed={collapsed} />
      </SidebarFooter>
    </Sidebar>
  );
}
