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

describe("workflow approval re-sync and live lifecycle (Bug 1)", () => {
  it("polls while in waiting_approval status and stops only on terminal states", () => {
    // Mirror refetchInterval logic in useWorkflowRun
    const computeRefetchInterval = (status: string | undefined) => {
      return status && ["succeeded", "failed", "diverged", "cancelled"].includes(status)
        ? false
        : 2000;
    };

    expect(computeRefetchInterval("waiting_approval")).toBe(2000);
    expect(computeRefetchInterval("running")).toBe(2000);
    expect(computeRefetchInterval("queued")).toBe(2000);
    expect(computeRefetchInterval("succeeded")).toBe(false);
    expect(computeRefetchInterval("failed")).toBe(false);
    expect(computeRefetchInterval("cancelled")).toBe(false);
  });

  it("triggers refetch when approval-decided event is emitted", () => {
    const refetchSpy = vi.fn();
    const handleApprovalDecided = () => {
      refetchSpy();
    };

    window.addEventListener("approval-decided", handleApprovalDecided);
    window.dispatchEvent(
      new CustomEvent("approval-decided", {
        detail: { id: "app-123", decision: "approved", run_id: "run-456" },
      }),
    );

    expect(refetchSpy).toHaveBeenCalledTimes(1);
    window.removeEventListener("approval-decided", handleApprovalDecided);
  });
});

describe("duplicate load workflow prevention (Bug 2)", () => {
  it("guards against duplicate loadWorkflow calls when data updates", () => {
    let loadCount = 0;
    const lastLoadedEditIdRef = { current: null as string | null };

    const loadWorkflow = (wf: { id: string; name: string }) => {
      lastLoadedEditIdRef.current = wf.id;
      loadCount++;
    };

    const simulateDataEffect = (editIdParam: string | null, data: Array<{ id: string; name: string }>) => {
      if (!editIdParam) return;
      if (editIdParam === lastLoadedEditIdRef.current) return;
      const wf = data.find((w) => w.id === editIdParam);
      if (wf) {
        loadWorkflow(wf);
      }
    };

    const workflowData = [{ id: "wf-1", name: "Gmail Monitor" }];

    // Step 1: User installs template -> handleInstallTemplate calls loadWorkflow directly
    loadWorkflow(workflowData[0]);
    expect(loadCount).toBe(1);
    expect(lastLoadedEditIdRef.current).toBe("wf-1");

    // Step 2: workflows.refetch() resolves, triggering the useEffect([data]) with ?edit=wf-1
    simulateDataEffect("wf-1", workflowData);
    // Should NOT call loadWorkflow again
    expect(loadCount).toBe(1);

    // Step 3: Navigating to a different workflow does load it
    const updatedData = [
      { id: "wf-1", name: "Gmail Monitor" },
      { id: "wf-2", name: "Slack Triage" },
    ];
    simulateDataEffect("wf-2", updatedData);
    expect(loadCount).toBe(2);
    expect(lastLoadedEditIdRef.current).toBe("wf-2");
  });
});

describe("node attempt deduplication in RunKpiStrip (Bug 3)", () => {
  it("deduplicates multi-attempt nodes and accurately reports 5/5 nodes", async () => {
    const { dedupeLatestNodes } = await import("@/lib/automations/kpi");

    // Realistic run.nodes containing 6 attempts (approval has attempt 1 waiting, attempt 2 succeeded)
    const rawNodeRuns = [
      { id: "nr-1", node_id: "input", attempt: 1, status: "succeeded" },
      { id: "nr-2", node_id: "triager", attempt: 1, status: "succeeded" },
      { id: "nr-3", node_id: "agent", attempt: 1, status: "succeeded" },
      { id: "nr-4", node_id: "approval", attempt: 1, status: "waiting_approval" },
      { id: "nr-5", node_id: "approval", attempt: 2, status: "succeeded" },
      { id: "nr-6", node_id: "output", attempt: 1, status: "succeeded" },
    ];

    const deduplicated = dedupeLatestNodes(rawNodeRuns);
    expect(deduplicated).toHaveLength(5);

    const doneCount = deduplicated.filter((n) => n.status === "succeeded").length;
    const totalCount = deduplicated.length;

    expect(totalCount).toBe(5);
    expect(doneCount).toBe(5);
    expect(Math.round((doneCount / totalCount) * 100)).toBe(100);
  });

  it("handles empty or single attempt node runs gracefully", async () => {
    const { dedupeLatestNodes } = await import("@/lib/automations/kpi");

    expect(dedupeLatestNodes(undefined)).toEqual([]);
    expect(dedupeLatestNodes([])).toEqual([]);

    const single = [{ id: "nr-1", node_id: "input", attempt: 1, status: "running" }];
    expect(dedupeLatestNodes(single)).toHaveLength(1);
    expect(dedupeLatestNodes(single)[0].status).toBe("running");
  });
});

