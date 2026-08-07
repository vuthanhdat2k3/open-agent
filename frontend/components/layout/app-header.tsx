"use client";

import { Menu } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";

export function AppHeader({ title, onMenuClick }: { title: string; onMenuClick: () => void }) {
  return (
    <header className="sticky top-0 z-30 flex min-h-14 items-center gap-2 border-b border-border/80 bg-background/85 px-4 backdrop-blur-md lg:px-8">
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={onMenuClick} aria-label="Open navigation"><Menu className="h-5 w-5" aria-hidden="true" /></Button>
      <h1 className="min-w-0 flex-1 truncate text-sm font-semibold tracking-tight text-foreground">{title}</h1>
      <ThemeToggle />
    </header>
  );
}
