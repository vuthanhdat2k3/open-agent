import { describe, expect, it } from "vitest";
import {
  inferLanguage,
  tryAutoOpenCanvasFromTool,
  tryAutoOpenCanvasFromArtifact,
} from "@/lib/chat/canvas-utils";
import { useCanvasStore } from "@/stores";

describe("inferLanguage", () => {
  it("infers language from common extensions", () => {
    expect(inferLanguage("main.py")).toBe("python");
    expect(inferLanguage("index.html")).toBe("html");
    expect(inferLanguage("icon.svg")).toBe("html");
    expect(inferLanguage("app.ts")).toBe("typescript");
    expect(inferLanguage("component.tsx")).toBe("typescript");
    expect(inferLanguage("script.js")).toBe("javascript");
    expect(inferLanguage("deploy.sh")).toBe("bash");
    expect(inferLanguage("data.json")).toBe("json");
    expect(inferLanguage("query.sql")).toBe("sql");
  });

  it("handles unknown or missing extensions gracefully", () => {
    expect(inferLanguage("README")).toBe("plaintext");
    expect(inferLanguage("file.xyz")).toBe("xyz");
  });
});

describe("useCanvasStore", () => {
  it("initializes with closed state", () => {
    const state = useCanvasStore.getState();
    expect(state.isOpen).toBe(false);
    expect(state.activeItem).toBeNull();
  });

  it("opens canvas with provided item", () => {
    useCanvasStore.getState().openCanvas({
      title: "test.py",
      code: "print('hello')",
      language: "python",
    });

    const state = useCanvasStore.getState();
    expect(state.isOpen).toBe(true);
    expect(state.activeItem?.title).toBe("test.py");
    expect(state.activeItem?.code).toBe("print('hello')");

    useCanvasStore.getState().closeCanvas();
    expect(useCanvasStore.getState().isOpen).toBe(false);
    expect(useCanvasStore.getState().activeItem).toBeNull();
  });
it("manages panel width percentage with clamping between 25 and 75", () => {
    expect(useCanvasStore.getState().panelWidthPercentage).toBe(50);

    useCanvasStore.getState().setPanelWidthPercentage(60);
    expect(useCanvasStore.getState().panelWidthPercentage).toBe(60);

    // Below min clamp
    useCanvasStore.getState().setPanelWidthPercentage(10);
    expect(useCanvasStore.getState().panelWidthPercentage).toBe(25);

    // Above max clamp
    useCanvasStore.getState().setPanelWidthPercentage(90);
    expect(useCanvasStore.getState().panelWidthPercentage).toBe(75);

    // Reset back to 50
    useCanvasStore.getState().setPanelWidthPercentage(50);
    expect(useCanvasStore.getState().panelWidthPercentage).toBe(50);
  });

  it("toggles fullscreen state", () => {
    expect(useCanvasStore.getState().isFullscreen).toBe(false);
    useCanvasStore.getState().toggleFullscreen();
    expect(useCanvasStore.getState().isFullscreen).toBe(true);
    useCanvasStore.getState().toggleFullscreen();
    expect(useCanvasStore.getState().isFullscreen).toBe(false);
  });

  it("opens canvas with workflow item including nodes and edges graph", () => {
    useCanvasStore.getState().openCanvas({
      type: "workflow",
      title: "Data Processing Pipeline",
      workflowId: "wf-123",
      workflowName: "Data Processing Pipeline",
      workflowRunId: "run-456",
      workflowGraph: {
        nodes: [
          { id: "node-1", kind: "input", label: "Input", config: {} },
          { id: "node-2", kind: "agent", label: "Agent Summary", config: {} },
        ],
        edges: [
          { from_: "node-1", to: "node-2" },
        ],
      },
      code: '{"nodes": [], "edges": []}',
      language: "json",
    });

    const state = useCanvasStore.getState();
    expect(state.isOpen).toBe(true);
    expect(state.activeItem?.type).toBe("workflow");
    expect(state.activeItem?.workflowId).toBe("wf-123");
    expect(state.activeItem?.workflowRunId).toBe("run-456");
    expect(state.activeItem?.workflowGraph?.nodes).toHaveLength(2);
    expect(state.activeItem?.workflowGraph?.edges).toHaveLength(1);
  });
});

describe("tryAutoOpenCanvasFromTool and tryAutoOpenCanvasFromArtifact", () => {
  it("auto-opens canvas for workflow_create tool call and result", () => {
    const lastKeyRef = { current: null };
    const openedItems: any[] = [];
    const openCanvas = (item: any) => openedItems.push(item);

    const handledCall = tryAutoOpenCanvasFromTool(
      "workflow_create",
      JSON.stringify({ name: "Crawl and Summarize", graph: { nodes: [{ id: "n1" }], edges: [] } }),
      null,
      { openCanvas, lastOpenedKeyRef: lastKeyRef },
    );

    expect(handledCall).toBe(true);
    expect(openedItems).toHaveLength(1);
    expect(openedItems[0].type).toBe("workflow");
    expect(openedItems[0].workflowName).toBe("Crawl and Summarize");

    // Result arrives with ID
    const handledResult = tryAutoOpenCanvasFromTool(
      "workflow_create",
      null,
      JSON.stringify({ status: "created", id: "wf-new-123", name: "Crawl and Summarize" }),
      { openCanvas, lastOpenedKeyRef: lastKeyRef },
    );

    expect(handledResult).toBe(true);
    expect(openedItems).toHaveLength(2);
    expect(openedItems[1].workflowId).toBe("wf-new-123");
  });

  it("auto-opens canvas for workflow_run with runId", () => {
    const lastKeyRef = { current: null };
    const openedItems: any[] = [];
    const openCanvas = (item: any) => openedItems.push(item);

    const handled = tryAutoOpenCanvasFromTool(
      "workflow_run",
      JSON.stringify({ workflow_id: "wf-abc", name: "Daily ETL" }),
      JSON.stringify({ status: "queued", workflow_id: "wf-abc", run_id: "run-xyz-789" }),
      { openCanvas, lastOpenedKeyRef: lastKeyRef },
    );

    expect(handled).toBe(true);
    expect(openedItems).toHaveLength(1);
    expect(openedItems[0].type).toBe("workflow");
    expect(openedItems[0].workflowId).toBe("wf-abc");
    expect(openedItems[0].workflowRunId).toBe("run-xyz-789");
  });

  it("auto-opens canvas for write_file and run_code", () => {
    const lastKeyRef = { current: null };
    const openedItems: any[] = [];
    const openCanvas = (item: any) => openedItems.push(item);

    const fileHandled = tryAutoOpenCanvasFromTool(
      "write_file",
      JSON.stringify({ path: "/workspace/report.html", content: "<h1>Report</h1>" }),
      null,
      { openCanvas, lastOpenedKeyRef: lastKeyRef },
    );
    expect(fileHandled).toBe(true);
    expect(openedItems[0].type).toBe("file");
    expect(openedItems[0].title).toBe("report.html");
    expect(openedItems[0].initialTab).toBe("preview");

    const codeHandled = tryAutoOpenCanvasFromTool(
      "run_code",
      JSON.stringify({ language: "python", code: "print('hello')" }),
      null,
      { openCanvas, lastOpenedKeyRef: lastKeyRef },
    );
    expect(codeHandled).toBe(true);
    expect(openedItems[1].type).toBe("code");
    expect(openedItems[1].language).toBe("python");
  });

  it("auto-opens canvas for artifact items", () => {
    const lastKeyRef = { current: null };
    const openedItems: any[] = [];
    const openCanvas = (item: any) => openedItems.push(item);

    const handled = tryAutoOpenCanvasFromArtifact(
      { id: "art-1", name: "data.csv" },
      { openCanvas, lastOpenedKeyRef: lastKeyRef },
    );
    expect(handled).toBe(true);
    expect(openedItems[0].type).toBe("file");
    expect(openedItems[0].title).toBe("data.csv");

    // Re-calling with same key is debounced/prevented
    const reHandled = tryAutoOpenCanvasFromArtifact(
      { id: "art-1", name: "data.csv" },
      { openCanvas, lastOpenedKeyRef: lastKeyRef },
    );
    expect(reHandled).toBe(false);
  });
});


