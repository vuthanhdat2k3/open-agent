"use client";

import * as React from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import { X, GitBranch } from "lucide-react";
import { cn } from "@/lib/utils";
import type { NodeStatus } from "./workflow-node-types";

export type WorkflowEdgeData = {
  sourceStatus: NodeStatus;
  onDelete: (edgeId: string) => void;
  onEditCondition?: (edgeId: string) => void;
};

export function WorkflowCustomEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  data,
  label,
}: EdgeProps & { data?: WorkflowEdgeData }) {
  const [hovered, setHovered] = React.useState(false);
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const sourceStatus = data?.sourceStatus ?? "idle";
  const hasCondition = Boolean(label);

  const strokeClass =
    sourceStatus === "running"
      ? "stroke-info [stroke-dasharray:6_4] animate-dash-flow"
      : sourceStatus === "done"
        ? "stroke-success"
        : sourceStatus === "error"
          ? "stroke-destructive"
          : "stroke-border";

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        className={cn("!stroke-2 transition-colors duration-300", hovered && "!stroke-primary", strokeClass)}
      />
      {/* Wider invisible hit area drives hover state (used for the delete
          button below) since the visible stroke is too thin to hover reliably. */}
      <path
        d={edgePath}
        fill="none"
        strokeWidth={16}
        stroke="transparent"
        className="pointer-events-auto"
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      />
      <EdgeLabelRenderer>
        {hasCondition && (
          <span
            className={cn(
              "pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-md border border-primary/30 bg-primary/10 px-1.5 py-0.5 font-mono text-[9px] text-primary transition-opacity duration-150",
              hovered ? "opacity-100" : "opacity-70",
            )}
            style={{ left: labelX, top: labelY + 16 }}
          >
            <GitBranch className="mr-1 inline h-2.5 w-2.5" aria-hidden="true" />
            {String(label).slice(0, 40)}
          </span>
        )}
        <button
          type="button"
          aria-label="Edit condition"
          title="Edit condition"
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          onClick={(e) => {
            e.stopPropagation();
            data?.onEditCondition?.(id);
          }}
          className={cn(
            "pointer-events-auto absolute grid h-5 w-5 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-primary/40 bg-primary text-primary-foreground shadow-3d-card transition-opacity duration-150 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            hovered ? "opacity-100" : "opacity-0",
          )}
          style={{ left: labelX - 14, top: labelY }}
        >
          <GitBranch className="h-3 w-3" />
        </button>
        <button
          type="button"
          aria-label="Delete connection"
          title="Delete connection"
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          onClick={(e) => {
            e.stopPropagation();
            data?.onDelete(id);
          }}
          className={cn(
            "pointer-events-auto absolute grid h-5 w-5 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-destructive/40 bg-destructive text-destructive-foreground shadow-3d-card transition-opacity duration-150 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            hovered ? "opacity-100" : "opacity-0",
          )}
          style={{ left: labelX + 14, top: labelY }}
        >
          <X className="h-3 w-3" />
        </button>
      </EdgeLabelRenderer>
    </>
  );
}

export const workflowEdgeTypes = {
  custom: WorkflowCustomEdge,
};
