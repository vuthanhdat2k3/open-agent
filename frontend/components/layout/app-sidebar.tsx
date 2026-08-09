"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { QueryClient } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import { useApprovals } from "@/hooks";
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
} from "@/components/ui/sidebar";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { IntegrationsPanel } from "@/components/integrations/integrations-panel";
import { isActive, navGroups, prefetchTab } from "./navigation";

export function AppSidebar({ queryClient }: { queryClient: QueryClient }) {
  const pathname = usePathname();
  const approvals = useApprovals(true);
  const pending = approvals.data?.length ?? 0;
  const [integrationsOpen, setIntegrationsOpen] = React.useState(false);

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="gap-3">
        <div className="flex items-center gap-3 px-1 py-1">
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
        {navGroups.map((group) => (
          <SidebarGroup key={group.title}>
            <SidebarGroupLabel>{group.title}</SidebarGroupLabel>
            <SidebarMenu>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = isActive(pathname, item.href);
                const isIntegrations = item.href === "/integrations";
                return (
                  <SidebarMenuItem key={item.href}>
                    {isIntegrations ? (
                      <SidebarMenuButton isActive={active} tooltip={item.label} onClick={() => setIntegrationsOpen(true)}>
                        <Icon aria-hidden="true" />
                        <span>{item.label}</span>
                      </SidebarMenuButton>
                    ) : (
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
                    )}
                    {item.href === "/approvals" && pending > 0 && (
                      <SidebarMenuBadge aria-label={`${pending} pending approvals`}>{pending}</SidebarMenuBadge>
                    )}
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter>
        <UserNav collapsed={false} />
      </SidebarFooter>

      <Sheet open={integrationsOpen} onOpenChange={setIntegrationsOpen}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>Integrations</SheetTitle>
            <SheetDescription>Manage connected Google Drive, Calendar, and Email accounts without leaving your work.</SheetDescription>
          </SheetHeader>
          <div className="mt-4">
            <IntegrationsPanel withHeader={false} />
          </div>
        </SheetContent>
      </Sheet>
    </Sidebar>
  );
}
