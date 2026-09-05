"use client";

import * as React from "react";
import type { QueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { AppHeader } from "./app-header";
import { AppSidebar } from "./app-sidebar";
import { allNavItems, isActive } from "./navigation";
import { Companion3D } from "@/components/operator";
import { useCurrentRole, useMe } from "@/hooks";
import { isEndUser } from "@/lib/roles";
import { KeyRound } from "lucide-react";

const FORCE_CHANGE_PATH = "/settings/profile?force_change=1";

export function AppShell({ children, queryClient }: { children: React.ReactNode; queryClient: QueryClient }) {
  const pathname = usePathname();
  const router = useRouter();
  const { t, locale, tx } = useTranslation();
  const role = useCurrentRole();
  const me = useMe();
  const mustChangePassword = Boolean(me.data?.must_change_password);

  // Admins provision new accounts with a default password; the account
  // stays locked until the user picks their own. Redirect any other page
  // to the profile so they can change the password.
  React.useEffect(() => {
    if (!mustChangePassword) return;
    if (!pathname.startsWith("/settings/profile")) {
      router.replace(FORCE_CHANGE_PATH);
    }
  }, [mustChangePassword, pathname, router]);

  const isEndUserFlag = isEndUser(role);
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
        {mustChangePassword && pathname.startsWith("/settings/profile") ? (
          <div className="mx-auto w-full max-w-3xl px-4 pt-6 sm:px-6 lg:px-8">
            <div role="alert" className="flex items-start gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-amber-700 shadow-sm">
              <KeyRound className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
              <div className="space-y-1">
                <p className="text-sm font-semibold">{t("forceChange.bannerTitle", "Tài khoản của bạn đang dùng mật khẩu tạm")}</p>
                <p className="text-xs leading-relaxed">{t("forceChange.bannerBody", "Vui lòng đổi mật khẩu để tiếp tục sử dụng OpenAgent. Các trang khác sẽ được mở khóa sau khi đổi xong.")}</p>
              </div>
            </div>
          </div>
        ) : null}
        <div
          key={pathname}
          className={cn(
            "flex min-h-0 flex-1 flex-col animate-fade-in",
            !fullBleed && "mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8",
          )}
        >
          {children}
        </div>
        {!fullBleed && isEndUserFlag && <Companion3D />}
      </SidebarInset>
    </SidebarProvider>
  );
}

