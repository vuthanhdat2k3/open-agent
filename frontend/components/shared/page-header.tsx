import * as React from "react";
import { type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function PageHeader({ icon: Icon, title, description, actions, className }: { icon: LucideIcon; title: string; description?: string; actions?: React.ReactNode; className?: string }) {
  return (
    <header className={cn("flex flex-col gap-4 border-b border-border/70 pb-6 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div className="flex min-w-0 items-center gap-3.5">
        <div className="grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary shadow-inner-edge">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="min-w-0 space-y-1">
          <h1 className="text-2xl font-bold tracking-tight text-foreground text-balance">{title}</h1>
          {description && <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
