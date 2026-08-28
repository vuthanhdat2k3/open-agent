"use client";

import { ThemeToggle } from "@/components/theme-toggle";
import { LanguageToggle } from "@/components/language-toggle";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { useTranslation } from "@/lib/i18n";
import { ApprovalBell } from "./approval-bell";

export function AppHeader({ title }: { title: string }) {
  const { tx } = useTranslation();
  return (
    <header className="sticky top-0 z-30 flex min-h-14 items-center gap-2 border-b border-border/80 bg-background/85 px-4 backdrop-blur-md lg:px-8">
      <SidebarTrigger aria-label={tx("Bật/tắt điều hướng", "Toggle navigation")} />
      <h1 className="min-w-0 flex-1 truncate text-sm font-semibold tracking-tight text-foreground">{title}</h1>
      <ApprovalBell />
      <LanguageToggle />
      <ThemeToggle />
    </header>
  );
}
