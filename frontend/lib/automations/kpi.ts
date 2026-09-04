/**
 * KPI and node execution utilities for workflow runs.
 */

export interface NodeRunLike {
  node_id: string;
  attempt?: number;
  status: string;
}

/**
 * Deduplicate workflow node run attempts by node_id, keeping the latest attempt.
 *
 * When a workflow pauses (e.g. at an approval gate) and resumes, the engine
 * creates a new node run record with incremented `attempt` (e.g. attempt 1:
 * "waiting_approval", attempt 2: "succeeded").
 *
 * This helper ensures progress counting and node statistics reflect unique DAG
 * nodes rather than inflating the count with prior superseded attempts.
 */
export function dedupeLatestNodes<T extends NodeRunLike>(nodes: T[] | undefined): T[] {
  if (!nodes || nodes.length === 0) return [];
  const map = new Map<string, T>();
  for (const n of nodes) {
    const existing = map.get(n.node_id);
    if (!existing || (n.attempt ?? 1) >= (existing.attempt ?? 1)) {
      map.set(n.node_id, n);
    }
  }
  return Array.from(map.values());
}
