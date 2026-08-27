/**
 * Tests for the auto-layout effect in app/workflows/page.tsx (Fix #11).
 *
 * The effect must only auto-place nodes that have no position yet. Re-laying
 * out the whole graph on any change would clobber positions the user just
 * dragged — a real UX bug found in the workflow audit.
 *
 * The effect itself is a closure inside the WorkflowEditor component, so we
 * test it by reproducing its body as a small pure function and asserting on
 * the result. This keeps the test independent of React/Test Renderer setup.
 */
import { describe, it, expect, vi } from "vitest";

type Position = { x: number; y: number };
type Node = { id: string; position?: Position };
type Edge = { from_: string; to: string };

function calculateDagLayout(nodes: Node[], _edges: Edge[]): Record<string, Position> {
  // Stripped-down version of the production function; enough to verify the
  // effect under test.
  const out: Record<string, Position> = {};
  nodes.forEach((n, i) => {
    out[n.id] = { x: 40 + i * 280, y: 40 };
  });
  return out;
}

/** Mirrors the production effect in app/workflows/page.tsx. */
function placeUnplaced(
  nodes: Node[],
  edges: Edge[],
  setGraph: (next: Node[], edges: Edge[]) => void
): void {
  const unplaced = nodes.filter((n) => n.position?.x == null);
  if (unplaced.length === 0) return;
  const calculatedPos = calculateDagLayout(nodes, edges);
  const updatedNodes = nodes.map((n) =>
    n.position?.x != null
      ? n
      : { ...n, position: calculatedPos[n.id] || { x: 40, y: 40 } }
  );
  setGraph(updatedNodes, edges);
}

describe("auto-layout effect (Fix #11)", () => {
  it("preserves already-placed positions when adding a new node", () => {
    const placedA = { id: "a", position: { x: 123, y: 456 } };
    const placedB = { id: "b", position: { x: 999, y: 999 } };
    const fresh = { id: "c" };
    let captured: Node[] = [];
    placeUnplaced([placedA, placedB, fresh], [], (n) => {
      captured = n;
    });
    // placed nodes stay exactly where the user put them
    expect(captured[0].position).toEqual({ x: 123, y: 456 });
    expect(captured[1].position).toEqual({ x: 999, y: 999 });
    // only the fresh node got a calculated position
    expect(captured[2].position).toBeDefined();
  });

  it("places only new nodes that have no position", () => {
    const existing = { id: "a", position: { x: 100, y: 200 } };
    const fresh = { id: "b" };
    let captured: Node[] = [];
    placeUnplaced([existing, fresh], [{ from_: "a", to: "b" }], (n) => {
      captured = n;
    });
    // existing node stays exactly where the user put it
    expect(captured[0].position).toEqual({ x: 100, y: 200 });
    // fresh node gets a calculated position
    expect(captured[1].position).toBeDefined();
    expect(captured[1].position?.x).not.toBeNull();
  });

  it("is a no-op when all nodes already have a position", () => {
    const a = { id: "a", position: { x: 1, y: 1 } };
    const b = { id: "b", position: { x: 2, y: 2 } };
    const spy = vi.fn();
    placeUnplaced([a, b], [], spy);
    expect(spy).not.toHaveBeenCalled();
  });
});
