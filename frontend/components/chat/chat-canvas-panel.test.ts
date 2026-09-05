import { describe, expect, it } from "vitest";
import { inferLanguage } from "@/lib/chat/canvas-utils";
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
});
