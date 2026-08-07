import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors shadow-inner-edge [&_svg]:h-3 [&_svg]:w-3",
  {
    variants: {
      variant: {
        default: "border-primary/20 bg-primary/15 text-primary",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        outline: "border-border bg-card/40 text-foreground",
        destructive: "border-destructive/20 bg-destructive/15 text-destructive",
        success: "border-success/20 bg-success/15 text-success",
        warning: "border-warning/20 bg-warning/15 text-warning",
        info: "border-info/20 bg-info/15 text-info",
        "success-outline": "border-success/30 bg-success/10 text-success",
        "warning-outline": "border-warning/30 bg-warning/10 text-warning",
        "info-outline": "border-info/30 bg-info/10 text-info",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
