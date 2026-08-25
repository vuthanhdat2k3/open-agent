"use client";

import * as React from "react";
import type { ToolCallBlock } from "@/lib/chat/projection";
import { ToolCallChip } from "@/components/chat/blocks/tool-call-chip";
import { ToolCallCard } from "@/components/chat/blocks/tool-call-card";

interface ToolChipsGroupProps {
  blocks: ToolCallBlock[];
}

export function ToolChipsGroup({ blocks }: ToolChipsGroupProps) {
  const runningBlock = blocks.find((b) => b.status === "running");
  const [selectedId, setSelectedId] = React.useState<string | null>(null);

  const activeBlockId = selectedId ?? (runningBlock ? runningBlock.id : null);
  const activeBlock = blocks.find((b) => b.id === activeBlockId);

  const handleToggle = (id: string) => {
    setSelectedId((prev) => (prev === id ? null : id));
  };

  return (
    <div className="w-full space-y-1.5 my-1">
      <div className="flex flex-wrap items-center gap-1.5">
        {blocks.map((block) => (
          <ToolCallChip
            key={block.id}
            block={block}
            active={activeBlockId === block.id}
            onClick={() => handleToggle(block.id)}
          />
        ))}
      </div>

      {activeBlock && (
        <div className="animate-in fade-in-50 slide-in-from-top-1 duration-200">
          <ToolCallCard block={activeBlock} compact />
        </div>
      )}
    </div>
  );
}
