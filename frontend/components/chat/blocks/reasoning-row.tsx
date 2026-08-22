"use client";

import * as React from "react";
import { ChevronDown, Sparkles } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

interface ReasoningRowProps {
  content: string;
  streaming?: boolean;
}

export function ReasoningRow({ content, streaming }: ReasoningRowProps) {
  const [open, setOpen] = React.useState(streaming || !content);

  // Keep open while streaming if the user hasn't explicitly toggled it
  React.useEffect(() => {
    if (streaming) {
      setOpen(true);
    }
  }, [streaming]);

  if (!content && !streaming) return null;

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="w-full">
      <div className="rounded-xl border border-dashed border-border/70 bg-muted/15 px-3 py-2 transition-colors hover:bg-muted/20">
        <CollapsibleTrigger className="group flex w-full cursor-pointer items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-muted-foreground select-none focus-visible:outline-none">
          <div className="flex items-center gap-1.5">
            <Sparkles className="h-3 w-3 text-primary/70" aria-hidden="true" />
            <span>Reasoning</span>
            {streaming && (
              <span className="inline-flex gap-0.5 ml-1">
                <span className="h-1 w-1 rounded-full bg-primary animate-pulse" />
                <span className="h-1 w-1 rounded-full bg-primary animate-pulse [animation-delay:150ms]" />
                <span className="h-1 w-1 rounded-full bg-primary animate-pulse [animation-delay:300ms]" />
              </span>
            )}
          </div>
          <ChevronDown
            className="h-3 w-3 shrink-0 transition-transform duration-200 group-data-[state=closed]:-rotate-90 text-muted-foreground/70"
            aria-hidden="true"
          />
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-2 border-t border-dashed border-border/50 pt-2">
          <p className="whitespace-pre-wrap break-words font-mono text-[11px] italic leading-relaxed text-muted-foreground">
            {content || "Thinking…"}
          </p>
        </CollapsibleContent>
      </div>
    </Collapsible>
  );
}
