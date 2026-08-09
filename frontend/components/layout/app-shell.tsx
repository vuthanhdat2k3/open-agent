"use client";

import * as React from "react";
import type { QueryClient } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";
import { AppHeader } from "./app-header";
import { AppSidebar } from "./app-sidebar";
import { allNavItems, isActive } from "./navigation";

export function AppShell({ children, queryClient }: { children: React.ReactNode; queryClient: QueryClient }) {
  const pathname = usePathname();
  const title = allNavItems.find((item) => isActive(pathname, item.href))?.label ?? "OpenAgent";
  // The chat page is a full-bleed, edge-to-edge surface (moon-chat aesthetic)
  // instead of the standard centered max-w-7xl content column other pages use.
  const fullBleed = pathname === "/chat";

  return (
    <SidebarProvider>
      <a href="#main-content" className="sr-only z-[100] rounded-md bg-background px-4 py-2 text-sm font-semibold text-foreground focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:ring-2 focus:ring-ring">Skip to main content</a>
      <AppSidebar queryClient={queryClient} />
      <SidebarInset
        id="main-content"
        tabIndex={-1}
        className={cn(
          "min-w-0 overflow-x-hidden",
          // Setting only overflow-x makes the browser compute the unset
          // overflow-y as "auto" (CSS overflow spec quirk), turning <main>
          // into a second, invisible-but-active scroll container on top of
          // the chat thread's own role="log" scroller — whichever one
          // actually receives the scroll wins, so the sticky chat header
          // (a sibling of that inner scroller, not a descendant of it)
          // scrolled away with it. Only the full-bleed page needs this
          // fixed; other pages want normal page-level scroll and are
          // unaffected by the same quirk (no separate inner scroller to
          // conflict with there).
          fullBleed && "overflow-y-hidden",
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
      </SidebarInset>
    </SidebarProvider>
  );
}
