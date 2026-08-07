import * as React from "react";
import { cn } from "@/lib/utils";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(({ className, children, ...props }, ref) => (
  <select ref={ref} className={cn("flex h-10 w-full cursor-pointer rounded-lg border border-border bg-background px-3.5 py-2 text-sm text-foreground shadow-inner-edge ring-offset-background transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50", className)} {...props}>{children}</select>
));
Select.displayName = "Select";
