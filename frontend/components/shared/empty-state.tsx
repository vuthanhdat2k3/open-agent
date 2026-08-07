import * as React from "react";
import { type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function EmptyState({ icon: Icon, title, description, action, className }: { icon?: LucideIcon; title: string; description?: string; action?: React.ReactNode; className?: string }) {
  return (
    <div role="status" className={cn("flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed border-border/80 bg-card/40 px-6 py-14 text-center", className)}>
      {Icon && <div className="grid h-12 w-12 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary"><Icon className="h-6 w-6" aria-hidden="true" /></div>}
      <div className="space-y-1"><p className="text-base font-semibold tracking-tight text-foreground">{title}</p>{description && <p className="mx-auto max-w-prose text-sm leading-relaxed text-muted-foreground">{description}</p>}</div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
