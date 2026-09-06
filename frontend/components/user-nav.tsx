"use client";

import * as React from "react";
import Link from "next/link";
import { ChevronUp, Globe, LogOut, User } from "lucide-react";
import { useProfile } from "@/hooks";
import { setAccessToken } from "@/lib/auth";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

export function UserNav({ collapsed }: { collapsed?: boolean }) {
  const profile = useProfile();
  const { t, dict, locale, setLocale, tx } = useTranslation();
  const user = profile.data;
  const displayName = user?.display_name || user?.email?.split("@")[0] || tx("Người dùng", "User");
  const email = user?.email || "";
  const initial = displayName.charAt(0).toUpperCase();

  async function handleLogout() {
    try { await api.post("/api/auth/logout"); } catch { /* local logout still clears the session */ }
    setAccessToken(null);
    try {
      localStorage.removeItem("openagent-workflow-editor");
      localStorage.removeItem("openagent-canvas");
    } catch {}
    window.location.href = "/login";
  }

  const toggleLanguage = () => {
    setLocale(locale === "vi" ? "en" : "vi");
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className={cn("group h-auto min-h-11 w-full justify-start gap-3 rounded-lg p-2 text-left", collapsed && "justify-center px-0")} title={collapsed ? displayName : undefined} aria-label={tx(`Mở menu tài khoản của ${displayName}`, `Open account menu for ${displayName}`)}>
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-primary text-sm font-bold text-primary-foreground shadow-sm ring-1 ring-primary/30" aria-hidden="true">{initial}</span>
          {!collapsed && <><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold leading-tight text-foreground">{displayName}</span><span className="block truncate text-xs text-muted-foreground">{email}</span></span><ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" aria-hidden="true" /></>}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent side={collapsed ? "right" : "top"} align={collapsed ? "end" : "start"} className="w-56">
        <DropdownMenuLabel><span className="block truncate">{displayName}</span><span className="block truncate text-xs font-normal text-muted-foreground">{email}</span></DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild><Link href="/settings/profile"><User className="h-4 w-4" aria-hidden="true" />{dict.nav.profile}</Link></DropdownMenuItem>
        <DropdownMenuItem onSelect={toggleLanguage} className="cursor-pointer">
          <Globe className="h-4 w-4" aria-hidden="true" />
          <span>{tx("Ngôn ngữ: Tiếng Việt 🇻🇳", "Language: English 🇬🇧")}</span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void handleLogout()} className="text-destructive focus:bg-destructive/10 focus:text-destructive"><LogOut className="h-4 w-4" aria-hidden="true" />{tx("Đăng xuất", "Sign Out")}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
