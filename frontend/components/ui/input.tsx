import * as React from "react";
import { cn } from "@/lib/utils";
export { Label } from "@/components/ui/label";
export { Textarea } from "@/components/ui/textarea";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn("flex h-10 w-full rounded-lg border border-border bg-background px-3.5 py-2 text-sm text-foreground shadow-inner-edge ring-offset-background transition-colors placeholder:text-muted-foreground/70 hover:border-primary/40 focus-visible:border-primary/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50", className)} {...props} />
));
Input.displayName = "Input";
