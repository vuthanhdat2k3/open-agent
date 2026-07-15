import * as React from "react";
import { cn } from "@/lib/utils";
import { type LucideIcon } from "lucide-react";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-4 rounded-2xl border border-dashed border-border bg-card/25 px-6 py-16 text-center backdrop-blur-md animate-scale-in",
        className,
      )}
    >
      {Icon && (
        <div className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-primary/15 to-primary/5 text-primary shadow-inner-edge">
          <Icon className="h-5 w-5" />
        </div>
      )}
      <div className="space-y-1">
        <p className="text-sm font-semibold tracking-tight text-foreground">{title}</p>
        {description && (
          <p className="mx-auto max-w-sm text-xs text-muted-foreground/80 leading-relaxed">{description}</p>
        )}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
