"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { QueryClient } from "@tanstack/react-query";
import { hasUiPermission, useCurrentPermissions, useCurrentRole, useEmailIntelligenceNavigationSummary } from "@/hooks";
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
import { useTranslation } from "@/lib/i18n";
import { isActive, navGroups, prefetchTab, type UserRole } from "./navigation";

export function AppSidebar({ queryClient }: { queryClient: QueryClient }) {
  const pathname = usePathname();
  const { t, locale } = useTranslation();
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const summary = useEmailIntelligenceNavigationSummary();
  const pending = summary.data?.user_workspace.approvals.pending ?? 0;
  const urgent = summary.data?.user_workspace.approvals.urgent ?? 0;
  const role = useCurrentRole();
  const permissions = useCurrentPermissions();

  const isRoleAllowed = (allowedRoles?: UserRole[]) => {
    if (!allowedRoles || allowedRoles.length === 0) return true;
    if (allowedRoles.includes(role as UserRole)) return true;
    if (role === "admin" && (allowedRoles.includes("org_admin") || allowedRoles.includes("admin"))) return true;
    return false;
  };

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="gap-3">
        <div className="flex items-center gap-3 px-1 py-1 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0 group-data-[collapsible=icon]:gap-0">
          <div className="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-xl bg-primary text-primary-foreground shadow-card">
            <Image
              src="/openagent-icon.png"
              alt="OpenAgent"
              width={36}
              height={36}
              className="h-full w-full object-cover"
              priority
            />
          </div>
          <div className="min-w-0 group-data-[collapsible=icon]:hidden">
            <div className="truncate text-base font-bold tracking-tight text-foreground">{locale === "vi" ? "OpenAgent" : "OpenAgent"}</div>
            <div className="truncate text-xs text-muted-foreground">{locale === "vi" ? "Agent Platform" : "Agent Platform"}</div>
          </div>
        </div>
        <div className="group-data-[collapsible=icon]:hidden">
          <OrgSwitcher collapsed={false} />
        </div>
      </SidebarHeader>

      <SidebarContent>
        {navGroups
          .filter((group) => isRoleAllowed(group.roles))
          .map((group) => {
            const items = group.items.filter((item) => {
              const hasPerm = !item.permission || hasUiPermission(permissions, item.permission);
              const passPlatform = !item.platformOnly || role === "platform_admin";
              const passRole = isRoleAllowed(item.roles);
              return hasPerm && passPlatform && passRole;
            });
            if (items.length === 0) return null;
            const groupTitle = group.i18nKey ? t(group.i18nKey, group.title) : group.title;
            return (
          <SidebarGroup key={group.title}>
            <SidebarGroupLabel>{groupTitle}</SidebarGroupLabel>
            <SidebarMenu>
              {items.map((item) => {
                const Icon = item.icon;
                const active = isActive(pathname, item.href);
                const itemLabel = item.i18nKey ? t(item.i18nKey, item.label) : item.label;
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={active}
                      tooltip={itemLabel}
                      onMouseEnter={() => prefetchTab(queryClient, item.href)}
                      onFocus={() => prefetchTab(queryClient, item.href)}
                    >
                      <Link href={item.href} aria-current={active ? "page" : undefined}>
                        <Icon aria-hidden="true" />
                        <span>{itemLabel}</span>
                      </Link>
                    </SidebarMenuButton>
                    {item.href === "/approvals" && pending > 0 && (
                      <SidebarMenuBadge aria-label={`${pending} pending approvals${urgent ? `, ${urgent} urgent` : ""}`}>
                        <span>{pending}</span>{urgent > 0 && <span className="ml-1 text-[9px] text-destructive">· {urgent} {locale === "vi" ? "urgent" : "urgent"}</span>}
                      </SidebarMenuBadge>
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
