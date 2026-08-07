"use client";

import type { QueryClient } from "@tanstack/react-query";
import { UserNav } from "@/components/user-nav";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Brand, SidebarNav } from "./app-sidebar";

export function MobileNav({ open, onOpenChange, queryClient }: { open: boolean; onOpenChange: (open: boolean) => void; queryClient: QueryClient }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="left" className="flex w-[min(88vw,20rem)] flex-col p-0">
        <SheetHeader className="sr-only"><SheetTitle>Navigation</SheetTitle><SheetDescription>OpenAgent primary navigation</SheetDescription></SheetHeader>
        <Brand collapsed={false} />
        <SidebarNav collapsed={false} onNavigate={() => onOpenChange(false)} queryClient={queryClient} />
        <div className="border-t border-border/70 p-3"><UserNav /></div>
      </SheetContent>
    </Sheet>
  );
}
