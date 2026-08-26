"use client";

import * as React from "react";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  MiniMap,
  Controls,
  Panel,
  useReactFlow,
  type Node,
  type Edge,
  type OnNodesChange,
  type OnEdgesChange,
  type Connection,
  type NodeChange,
  type EdgeChange,
  applyNodeChanges,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Map as MapIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { GraphEdge, GraphNode } from "@/types";
import { workflowNodeTypes, type NodeStatus, type WorkflowNodeData } from "./workflow-node-types";
import { workflowEdgeTypes, type WorkflowEdgeData } from "./workflow-custom-edge";
import { WORKFLOW_DND_MIME } from "./workflow-node-palette";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useTranslation } from "@/lib/i18n";

interface WorkflowCanvasProps {
  graphNodes: GraphNode[];
  graphEdges: GraphEdge[];
  nodeStatus: Record<string, string>;
  selectedNodeId: string | null;
  className?: string;
  onGraphChange: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  onSelectNode: (id: string | null) => void;
  onCreateNode: (kind: GraphNode["kind"], position: { x: number; y: number }) => void;
  onEditEdgeCondition?: (edgeId: string) => void;
}

function toFlowStatus(status: string | undefined): NodeStatus {
  if (status === "running") return "running";
  if (status === "done") return "done";
  if (status === "error") return "error";
  return "idle";
}

function toFlowNodes(
  nodes: GraphNode[],
  nodeStatus: Record<string, string>,
  onDelete: (id: string) => void,
): Node<WorkflowNodeData>[] {
  return nodes.map((n) => ({
    id: n.id,
    type: n.kind,
    position: n.position || { x: 0, y: 0 },
    data: { label: n.label, kind: n.kind, status: toFlowStatus(nodeStatus[n.id]), onDelete },
  }));
}

function toFlowEdges(
  edges: GraphEdge[],
  nodeStatus: Record<string, string>,
  onDelete: (edgeId: string) => void,
  onEditCondition?: (edgeId: string) => void,
): Edge<WorkflowEdgeData>[] {
  return edges.map((e, i) => ({
    id: `${e.from_}->${e.to}#${i}`,
    source: e.from_,
    target: e.to,
    type: "custom",
    label: e.condition || undefined,
    data: { sourceStatus: toFlowStatus(nodeStatus[e.from_]), onDelete, onEditCondition },
  }));
}

function edgeIdToGraphEdge(edgeId: string): { from_: string; to: string } {
  const [from_, rest] = edgeId.split("->");
  const to = rest?.split("#")[0] ?? "";
  return { from_, to };
}

type PendingDelete =
  | { kind: "node"; id: string; label: string }
  | { kind: "edge"; from_: string; to: string };

function WorkflowCanvasInner({
  graphNodes,
  graphEdges,
  nodeStatus,
  selectedNodeId,
  className,
  onGraphChange,
  onSelectNode,
  onCreateNode,
  onEditEdgeCondition,
}: WorkflowCanvasProps) {
    const { locale } = useTranslation();
  const { screenToFlowPosition } = useReactFlow();
  const [showMiniMap, setShowMiniMap] = React.useState(true);
  const [pendingDelete, setPendingDelete] = React.useState<PendingDelete | null>(null);
  const wrapperRef = React.useRef<HTMLDivElement>(null);

  const deleteEdge = React.useCallback(
    (from_: string, to: string) => {
      onGraphChange(graphNodes, graphEdges.filter((e) => !(e.from_ === from_ && e.to === to)));
    },
    [graphNodes, graphEdges, onGraphChange],
  );

  const deleteNode = React.useCallback(
    (id: string) => {
      onGraphChange(
        graphNodes.filter((n) => n.id !== id),
        graphEdges.filter((e) => e.from_ !== id && e.to !== id),
      );
      if (selectedNodeId === id) onSelectNode(null);
    },
    [graphNodes, graphEdges, onGraphChange, selectedNodeId, onSelectNode],
  );

  const handleDeleteNode = React.useCallback(
    (nodeId: string) => {
      const target = graphNodes.find((n) => n.id === nodeId);
      setPendingDelete({ kind: "node", id: nodeId, label: target?.label || nodeId });
    },
    [graphNodes],
  );

  const handleDeleteEdge = React.useCallback(
    (edgeId: string) => {
      const { from_, to } = edgeIdToGraphEdge(edgeId);
      setPendingDelete({ kind: "edge", from_, to });
    },
    [],
  );

  const nodes = React.useMemo(
    () => toFlowNodes(graphNodes, nodeStatus, handleDeleteNode),
    [graphNodes, nodeStatus, handleDeleteNode],
  );
  const edges = React.useMemo(
    () => toFlowEdges(graphEdges, nodeStatus, handleDeleteEdge, onEditEdgeCondition),
    [graphEdges, nodeStatus, handleDeleteEdge, onEditEdgeCondition],
  );

  const onNodesChange: OnNodesChange<Node<WorkflowNodeData>> = React.useCallback(
    (changes: NodeChange<Node<WorkflowNodeData>>[]) => {
      const removeChange = changes.find((c) => c.type === "remove");
      if (removeChange) {
        const target = graphNodes.find((n) => n.id === removeChange.id);
        setPendingDelete({ kind: "node", id: removeChange.id, label: target?.label || removeChange.id });
      }

      const nonRemoveChanges = changes.filter((c) => c.type !== "remove");
      if (nonRemoveChanges.length === 0) return;
      const next = applyNodeChanges(nonRemoveChanges, nodes);
      const positionChanged = nonRemoveChanges.some((c) => c.type === "position");
      if (!positionChanged) return;

      const updatedGraphNodes = graphNodes.map((n) => {
        const match = next.find((fn) => fn.id === n.id);
        return match ? { ...n, position: match.position } : n;
      });
      onGraphChange(updatedGraphNodes, graphEdges);
    },
    [nodes, graphNodes, graphEdges, onGraphChange],
  );

  const onEdgesChange: OnEdgesChange<Edge<WorkflowEdgeData>> = React.useCallback(
    (changes: EdgeChange<Edge<WorkflowEdgeData>>[]) => {
      const removed = changes.filter((c) => c.type === "remove");
      if (removed.length === 0) return;
      // Only ever one edge can be "selected + Delete key pressed" at a time
      // in practice; route through the same confirmation as the edge's
      // hover delete button.
      const { from_, to } = edgeIdToGraphEdge(removed[0].id);
      setPendingDelete({ kind: "edge", from_, to });
    },
    [],
  );

  const onConnect = React.useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      if (connection.source === connection.target) return;
      const exists = graphEdges.some(
        (e) => e.from_ === connection.source && e.to === connection.target,
      );
      if (exists) return;
      onGraphChange(graphNodes, [...graphEdges, { from_: connection.source, to: connection.target }]);
    },
    [graphNodes, graphEdges, onGraphChange],
  );

  const isValidConnection = React.useCallback(
    (connection: Connection | Edge) =>
      Boolean(connection.source) &&
      Boolean(connection.target) &&
      connection.source !== connection.target,
    [],
  );

  const onDragOver = React.useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = React.useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const kind = e.dataTransfer.getData(WORKFLOW_DND_MIME) as GraphNode["kind"] | "";
      if (!kind) return;
      const position = screenToFlowPosition({ x: e.clientX, y: e.clientY });
      onCreateNode(kind, position);
    },
    [screenToFlowPosition, onCreateNode],
  );

  return (
    <div
      ref={wrapperRef}
      className={cn(
        "relative overflow-hidden rounded-xl border border-border/80 bg-card/30 shadow-inner-edge",
        className,
      )}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={workflowNodeTypes}
        edgeTypes={workflowEdgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        isValidConnection={isValidConnection}
        onNodeClick={(_e, node) => onSelectNode(node.id)}
        onPaneClick={() => onSelectNode(null)}
        selectionOnDrag={false}
        deleteKeyCode={["Backspace", "Delete"]}
        colorMode="dark"
        proOptions={{ hideAttribution: true }}
        fitView
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.5} className="opacity-60" />
        <Controls className="!border !border-border/60 !bg-card/90 !shadow-3d-card [&_button]:!border-border/40 [&_button]:!bg-transparent [&_button]:!text-foreground [&_button:hover]:!bg-muted" />
        {showMiniMap && (
          <MiniMap
            pannable
            zoomable
            className="!border !border-border/60 !bg-card/90 !shadow-3d-card"
            maskColor="hsl(var(--background) / 0.6)"
            nodeColor="hsl(var(--muted-foreground) / 0.4)"
          />
        )}
        <Panel position="top-right">
          <button
            type="button"
            onClick={() => setShowMiniMap((v) => !v)}
            title={showMiniMap ? "Hide minimap" : "Show minimap"}
            aria-label={showMiniMap ? "Hide minimap" : "Show minimap"}
            aria-pressed={showMiniMap}
            className="grid h-8 w-8 place-items-center rounded-lg border border-border/60 bg-card/90 text-muted-foreground shadow-3d-card transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <MapIcon className="h-4 w-4" />
          </button>
        </Panel>
      </ReactFlow>

      <AlertDialog open={Boolean(pendingDelete)} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pendingDelete?.kind === "node" ? `Delete "${pendingDelete.label}"?` : "Delete this connection?"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDelete?.kind === "node"
                ? "The node and any edges connected to it will be removed from the canvas."
                : "This edge will be removed from the workflow graph."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{locale === "vi" ? "Hủy" : "Cancel"}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (!pendingDelete) return;
                if (pendingDelete.kind === "node") deleteNode(pendingDelete.id);
                else deleteEdge(pendingDelete.from_, pendingDelete.to);
                setPendingDelete(null);
              }}
            >
              {locale === "vi" ? "Xóa" : "Delete"}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export function WorkflowCanvas(props: WorkflowCanvasProps) {
    const { locale } = useTranslation();
  return (
    <ReactFlowProvider>
      <WorkflowCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
