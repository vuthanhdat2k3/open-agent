import type { GraphEdge, GraphNode } from "@/types";

/**
 * calculateDagLayout: Automatically calculates hierarchical layer coordinates
 * for DAG nodes so they align gracefully from entry roots down to outputs.
 */
export function calculateDagLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options?: {
    nodeWidth?: number;
    nodeGapX?: number;
    rankGapY?: number;
    centerX?: number;
  },
): Record<string, { x: number; y: number }> {
  if (nodes.length === 0) return {};
  const adj: Record<string, string[]> = {};
  const inDegree: Record<string, number> = {};
  nodes.forEach((n) => {
    adj[n.id] = [];
    inDegree[n.id] = 0;
  });
  edges.forEach((e: any) => {
    const fromId = e.from_ || e.from || e.source;
    const toId = e.to || e.target;
    if (fromId && toId) {
      if (!adj[fromId]) adj[fromId] = [];
      adj[fromId].push(toId);
      inDegree[toId] = (inDegree[toId] || 0) + 1;
    }
  });

  const roots = nodes.filter(
    (n) => inDegree[n.id] === 0 || ["input", "scheduler", "integration"].includes(n.kind),
  );
  const queue: { id: string; layer: number }[] = (roots.length > 0 ? roots : [nodes[0]]).map(
    (n) => ({ id: n.id, layer: 0 }),
  );

  const layer: Record<string, number> = {};
  queue.forEach((q) => (layer[q.id] = 0));
  const visited = new Set<string>(queue.map((q) => q.id));

  while (queue.length > 0) {
    const { id: cur, layer: curL } = queue.shift()!;
    (adj[cur] || []).forEach((nxt) => {
      const nextL = curL + 1;
      if (!layer[nxt] || nextL > layer[nxt]) {
        layer[nxt] = nextL;
      }
      if (!visited.has(nxt)) {
        visited.add(nxt);
        queue.push({ id: nxt, layer: nextL });
      }
    });
  }

  nodes.forEach((n) => {
    if (layer[n.id] == null) layer[n.id] = 0;
  });

  const perLayer: Record<number, GraphNode[]> = {};
  nodes.forEach((n) => {
    const l = layer[n.id] ?? 0;
    (perLayer[l] = perLayer[l] || []).push(n);
  });

  const nodeWidth = options?.nodeWidth ?? 214;
  const nodeGapX = options?.nodeGapX ?? 66;
  const rankGapY = options?.rankGapY ?? 170;
  const centerX = options?.centerX ?? 460;

  const pos: Record<string, { x: number; y: number }> = {};
  Object.entries(perLayer).forEach(([lStr, ns]) => {
    const l = parseInt(lStr, 10);
    const rowWidth = ns.length * nodeWidth + (ns.length - 1) * nodeGapX;
    const startX = Math.max(40, centerX - rowWidth / 2);
    ns.forEach((n, i) => {
      pos[n.id] = {
        x: Math.round(startX + i * (nodeWidth + nodeGapX)),
        y: Math.round(40 + l * rankGapY),
      };
    });
  });

  return pos;
}
