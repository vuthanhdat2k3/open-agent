"use client";

import * as React from "react";
import type { QueryClient } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { AppHeader } from "./app-header";
import { AppSidebar, SidebarFooter } from "./app-sidebar";
import { MobileNav } from "./mobile-nav";
import { allNavItems, isActive } from "./navigation";

export function AppShell({ children, queryClient }: { children: React.ReactNode; queryClient: QueryClient }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const title = allNavItems.find((item) => isActive(pathname, item.href))?.label ?? "OpenAgent";

  return (
    <div className="relative z-10 flex min-h-dvh">
      <a href="#main-content" className="sr-only z-[100] rounded-md bg-background px-4 py-2 text-sm font-semibold text-foreground focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:ring-2 focus:ring-ring">Skip to main content</a>
      <aside className={`sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-border/80 bg-card/45 backdrop-blur-xl transition-[width] duration-300 ease-out-expo lg:flex ${collapsed ? "w-[76px]" : "w-64"}`}>
        <AppSidebar collapsed={collapsed} queryClient={queryClient} />
        <SidebarFooter collapsed={collapsed} onToggle={() => setCollapsed((value) => !value)} />
      </aside>
      <MobileNav open={mobileOpen} onOpenChange={setMobileOpen} queryClient={queryClient} />
      <div className="flex min-w-0 flex-1 flex-col">
        <AppHeader title={title} onMenuClick={() => setMobileOpen(true)} />
        <main id="main-content" tabIndex={-1} className="flex-1 overflow-x-hidden">
          <div key={pathname} className="mx-auto w-full max-w-7xl animate-fade-in px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
