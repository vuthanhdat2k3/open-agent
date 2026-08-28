"use client";

import * as React from "react";
import type { QueryClient } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { AppHeader } from "./app-header";
import { AppSidebar } from "./app-sidebar";
import { allNavItems, isActive } from "./navigation";
import { Companion3D } from "@/components/operator";
import { useCurrentRole } from "@/hooks";

export function AppShell({ children, queryClient }: { children: React.ReactNode; queryClient: QueryClient }) {
  const pathname = usePathname();
  const { t, locale, tx } = useTranslation();
  const role = useCurrentRole();
  const isEndUser = role === "user";
  const matched = [...allNavItems].sort((a, b) => b.href.length - a.href.length).find((item) => isActive(pathname, item.href));
  const title = matched ? (matched.i18nKey ? t(matched.i18nKey, matched.label) : matched.label) : "OpenAgent";
  // The chat page is a full-bleed, edge-to-edge surface (moon-chat aesthetic)
  // instead of the standard centered max-w-7xl content column other pages use.
  const fullBleed = pathname === "/chat";

  return (
    <SidebarProvider>
      <a href="#main-content" className="sr-only z-[100] rounded-md bg-background px-4 py-2 text-sm font-semibold text-foreground focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:ring-2 focus:ring-ring">{tx("Bỏ qua để đến nội dung chính", "Skip to main content")}</a>
      <AppSidebar queryClient={queryClient} />
      <SidebarInset
        id="main-content"
        tabIndex={-1}
        className={cn(
          "min-w-0 overflow-x-hidden",
          fullBleed && "h-svh overflow-y-hidden",
        )}
      >
        <AppHeader title={title} />
        <div
          key={pathname}
          className={cn(
            "flex min-h-0 flex-1 flex-col animate-fade-in",
            !fullBleed && "mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8",
          )}
        >
          {children}
        </div>
        {!fullBleed && isEndUser && <Companion3D />}
      </SidebarInset>
    </SidebarProvider>
  );
}

