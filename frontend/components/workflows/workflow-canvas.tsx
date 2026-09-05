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
import { Map as MapIcon, Crosshair, Sparkles, LayoutGrid } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
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
  followRunningNode?: boolean;
  onToggleFollow?: () => void;
  onAutoLayout?: () => void;
  onGraphChange: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  onSelectNode: (id: string | null) => void;
  onCreateNode: (kind: GraphNode["kind"], position: { x: number; y: number }) => void;
  onEditEdgeCondition?: (edgeId: string) => void;
}

function toFlowStatus(status: string | undefined): NodeStatus {
  if (status === "running") return "running";
  if (status === "done") return "done";
  if (status === "error") return "error";
  if (status === "waiting_approval") return "waiting";
  return "idle";
}

function toFlowNodes(
  nodes: GraphNode[],
  nodeStatus: Record<string, string>,
  onDelete: (id: string) => void,
  onInspect: (id: string) => void,
): Node<WorkflowNodeData>[] {
  return nodes.map((n) => ({
    id: n.id,
    type: n.kind,
    position: n.position || { x: 0, y: 0 },
    data: {
      label: n.label,
      kind: n.kind,
      status: toFlowStatus(nodeStatus[n.id]),
      onDelete,
      onInspect,
    },
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
  followRunningNode = true,
  onToggleFollow,
  onAutoLayout,
  onGraphChange,
  onSelectNode,
  onCreateNode,
  onEditEdgeCondition,
}: WorkflowCanvasProps) {
  const { t, locale, tx } = useTranslation();
  const { screenToFlowPosition, setCenter, fitView } = useReactFlow();
  const [showMiniMap, setShowMiniMap] = React.useState(true);
  const [pendingDelete, setPendingDelete] = React.useState<PendingDelete | null>(null);
  const wrapperRef = React.useRef<HTMLDivElement>(null);

  // Auto-follow / Pin running node: center viewport on node when it becomes running
  React.useEffect(() => {
    if (!followRunningNode) return;
    const runningEntry = Object.entries(nodeStatus).find(([_, status]) => status === "running");
    if (runningEntry) {
      const [runningNodeId] = runningEntry;
      const targetNode = graphNodes.find((n) => n.id === runningNodeId);
      if (targetNode?.position) {
        setCenter(targetNode.position.x + 107, targetNode.position.y + 47, {
          zoom: 1.05,
          duration: 700,
        });
      }
    }
  }, [nodeStatus, followRunningNode, graphNodes, setCenter]);

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

  const handleInspectNode = React.useCallback(
    (nodeId: string) => {
      onSelectNode(nodeId);
    },
    [onSelectNode],
  );

  const nodes = React.useMemo(
    () => toFlowNodes(graphNodes, nodeStatus, handleDeleteNode, handleInspectNode),
    [graphNodes, nodeStatus, handleDeleteNode, handleInspectNode],
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

  const onNodeClick = React.useCallback(
    (_: React.MouseEvent, node: Node) => {
      onSelectNode(node.id);
    },
    [onSelectNode],
  );

  const onPaneClick = React.useCallback(() => {
    onSelectNode(null);
  }, [onSelectNode]);

  return (
    <div
      ref={wrapperRef}
      className={cn(
        "relative overflow-hidden rounded-2xl border border-border/80 bg-card/40 shadow-inner-edge",
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
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.2}
        maxZoom={2.0}
        snapToGrid
        snapGrid={[16, 16]}
        defaultEdgeOptions={{ type: "custom" }}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} className="opacity-40" />
        <Controls className="!bg-card/90 !border-border/80 !shadow-3d-card !rounded-xl overflow-hidden [&>button]:!bg-transparent [&>button]:!border-border/60 hover:[&>button]:!bg-muted/50" />
        {showMiniMap && (
          <MiniMap
            zoomable
            pannable
            className="!bg-card/90 !border-border/80 !rounded-xl !shadow-3d-card overflow-hidden"
            nodeStrokeWidth={3}
            nodeColor={(n) => {
              const status = nodeStatus[n.id];
              if (status === "running") return "#38bdf8";
              if (status === "done") return "#10b981";
              if (status === "error") return "#ef4444";
              return "#64748b";
            }}
          />
        )}

        <Panel position="top-right" className="flex items-center gap-1.5 bg-card/90 backdrop-blur-md p-1.5 rounded-xl border border-border/80 shadow-3d-card">
          {onToggleFollow && (
            <Button
              size="sm"
              variant={followRunningNode ? "secondary" : "ghost"}
              className={cn(
                "h-7 text-xs gap-1.5 px-2.5 rounded-lg transition-all",
                followRunningNode && "bg-primary/15 text-primary border border-primary/30 font-semibold shadow-inner-edge",
              )}
              onClick={onToggleFollow}
              title={t("pages.workflows.followRunningNode", "Follow Running Node")}
            >
              <Crosshair className={cn("h-3.5 w-3.5", followRunningNode && "text-primary animate-pulse")} />
              <span className="hidden sm:inline">
                {t("pages.workflows.followRunningNode", "Follow Node")}
              </span>
            </Button>
          )}

          {onAutoLayout && (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs gap-1.5 px-2.5 rounded-lg text-muted-foreground hover:text-foreground"
              onClick={onAutoLayout}
              title={t("pages.workflows.btnAutoLayout", "Auto-layout Graph")}
            >
              <LayoutGrid className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">
                {t("pages.workflows.btnAutoLayout", "Auto Layout")}
              </span>
            </Button>
          )}

          <Button
            size="sm"
            variant="ghost"
            className={cn("h-7 w-7 p-0 rounded-lg", showMiniMap && "text-primary")}
            onClick={() => setShowMiniMap((v) => !v)}
            title={locale === "vi" ? "Bật/tắt MiniMap" : "Toggle MiniMap"}
          >
            <MapIcon className="h-3.5 w-3.5" />
          </Button>
        </Panel>
      </ReactFlow>

      {/* Confirmation modal before deleting node / edge */}
      <AlertDialog open={pendingDelete !== null} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pendingDelete?.kind === "node"
                ? locale === "vi"
                  ? `Xóa Node "${pendingDelete.label}"?`
                  : `Delete node "${pendingDelete.label}"?`
                : locale === "vi"
                  ? "Xóa liên kết này?"
                  : "Delete connection?"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDelete?.kind === "node"
                ? locale === "vi"
                  ? "Node và tất cả các liên kết kết nối đến node này sẽ bị xóa khỏi canvas."
                  : "The node and all incoming/outgoing connections will be removed from the canvas."
                : locale === "vi"
                  ? `Liên kết giữa ${pendingDelete?.from_} và ${pendingDelete?.to} sẽ bị xóa.`
                  : `The connection from ${pendingDelete?.from_} to ${pendingDelete?.to} will be removed.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tx("Hủy", "Cancel")}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => {
                if (!pendingDelete) return;
                if (pendingDelete.kind === "node") {
                  deleteNode(pendingDelete.id);
                } else {
                  deleteEdge(pendingDelete.from_, pendingDelete.to);
                }
                setPendingDelete(null);
              }}
            >
              {tx("Xóa", "Delete")}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export function WorkflowCanvas(props: WorkflowCanvasProps) {
    const { locale, tx } = useTranslation();
  return (
    <ReactFlowProvider>
      <WorkflowCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
