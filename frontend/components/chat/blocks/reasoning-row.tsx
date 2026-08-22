"use client";

import * as React from "react";
import { ChevronDown, Sparkles } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

interface ReasoningRowProps {
  content: string;
  streaming?: boolean;
}

function firstLine(text: string): string {
  const newline = text.indexOf("\n");
  return newline === -1 ? text : text.slice(0, newline);
}

function latestLine(text: string): string {
  const visible = text.trimEnd();
  const newline = visible.lastIndexOf("\n");
  return newline === -1 ? visible : visible.slice(newline + 1);
}

export function ReasoningRow({ content, streaming }: ReasoningRowProps) {
  const [open, setOpen] = React.useState(streaming || !content);
  const summaryRef = React.useRef<HTMLSpanElement>(null);

  React.useEffect(() => {
    if (streaming) {
      setOpen(true);
    }
  }, [streaming]);

  React.useEffect(() => {
    if (streaming && summaryRef.current) {
      summaryRef.current.scrollLeft = summaryRef.current.scrollWidth;
    }
  }, [content, streaming]);

  if (!content && !streaming) return null;

  const summary = streaming ? latestLine(content) : firstLine(content);

  return (
    <div className="w-full" data-variant="think" data-state={streaming ? "running" : "ok"}>
      <Collapsible open={open} onOpenChange={setOpen} className="w-full">
        <div className={cn(
          "relative overflow-hidden rounded-lg px-2.5 py-1.5 transition-colors select-none",
          streaming ? "bg-muted/20" : "hover:bg-muted/15"
        )}>
          {streaming && (
            <div
              className="pointer-events-none absolute inset-y-0 left-0 w-[300px] opacity-40"
              style={{
                background: "linear-gradient(90deg, transparent 0%, hsl(var(--foreground) / 0.15) 50%, transparent 100%)",
                animation: "dsh-reasoning-row-sweep 2.6s ease-out infinite"
              }}
            />
          )}

          <CollapsibleTrigger className="group flex w-full cursor-pointer items-center text-xs font-normal text-muted-foreground focus-visible:outline-none">
            <div className="flex shrink-0 items-center gap-1.5 font-medium text-foreground/80">
              <Sparkles className="h-3.5 w-3.5 text-primary/80" aria-hidden="true" />
              <span>Think</span>
            </div>

            <div className="mx-2 h-1 w-1 shrink-0 rounded-full bg-muted-foreground/40" />

            <span
              ref={summaryRef}
              className="flex-1 truncate text-left text-xs font-normal text-muted-foreground/80"
            >
              {summary || "Thinking…"}
            </span>

            <ChevronDown
              className="ml-2 h-3.5 w-3.5 shrink-0 text-muted-foreground/60 transition-transform duration-200 group-data-[state=closed]:-rotate-90"
              aria-hidden="true"
            />
          </CollapsibleTrigger>

          <CollapsibleContent className="mt-2 border-t border-border/40 pt-2">
            <div className="whitespace-pre-wrap break-words pl-5 font-mono text-xs leading-relaxed text-muted-foreground">
              {content || "Thinking…"}
            </div>
          </CollapsibleContent>
        </div>
      </Collapsible>
    </div>
  );
}
