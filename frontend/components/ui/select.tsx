import * as React from "react";
import { cn } from "@/lib/utils";

// Lightweight styled native select with 3D depth and ring focus
export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "flex h-10 w-full rounded-lg border border-border bg-background px-3.5 py-2 text-sm text-foreground shadow-inner-edge ring-offset-background transition-all duration-200 hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer",
      className,
    )}
    {...props}
  >
    {children}
  </select>
));
Select.displayName = "Select";

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: string[];
  active: string;
  onChange: (t: string) => void;
}) {
  return (
    <div
      role="tablist"
      className="inline-flex h-10 items-center justify-center rounded-lg bg-muted/80 p-1 text-muted-foreground shadow-inner-edge"
    >
      {tabs.map((t) => (
        <button
          key={t}
          role="tab"
          aria-selected={active === t}
          onClick={() => onChange(t)}
          className={cn(
            "inline-flex items-center justify-center whitespace-nowrap rounded-md px-3.5 py-1.5 text-sm font-medium transition-all duration-200 ease-out-expo",
            active === t && "bg-card text-foreground shadow-3d-card font-semibold",
          )}
        >
          {t}
        </button>
      ))}
    </div>
  );
}

export function Slider({
  value,
  min = 0,
  max = 2,
  step = 0.1,
  onChange,
}: {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (v: number) => void;
}) {
  return (
    <input
      type="range"
      min={min}
      max={max}
      step={step}
      value={value}
      onChange={(e) => onChange(parseFloat(e.target.value))}
      className="w-full cursor-pointer accent-primary h-2 rounded-lg bg-muted shadow-inner-edge transition-all"
      aria-label="Value"
    />
  );
}
