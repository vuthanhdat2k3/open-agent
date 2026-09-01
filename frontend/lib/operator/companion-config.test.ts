import { describe, it, expect, beforeEach } from "vitest";
import {
  DEFAULT_COMPANION_CONFIG,
  COMPANION_SCALE_PRESETS,
  getCompanionConfig,
  saveCompanionConfig,
} from "./companion-config";

const storageMap = new Map<string, string>();
const localStorageMock = {
  getItem: (key: string) => storageMap.get(key) ?? null,
  setItem: (key: string, val: string) => storageMap.set(key, String(val)),
  removeItem: (key: string) => storageMap.delete(key),
  clear: () => storageMap.clear(),
};
Object.defineProperty(window, "localStorage", {
  value: localStorageMock,
  writable: true,
});

describe("companion-config", () => {
  beforeEach(() => {
    localStorageMock.clear();
  });

  it("returns default configuration with balanced avatarScale (85%)", () => {
    const config = getCompanionConfig();
    expect(config).toEqual(DEFAULT_COMPANION_CONFIG);
    expect(config.avatarScale).toBe(85);
  });

  it("provides four distinct scale presets ranging from compact to large", () => {
    expect(COMPANION_SCALE_PRESETS).toHaveLength(4);
    const scales = COMPANION_SCALE_PRESETS.map((p) => p.scale);
    expect(scales).toEqual([70, 85, 100, 115]);
  });

  it("persists updated avatarScale and notifies listeners", () => {
    let notified = false;
    const listener = () => {
      notified = true;
    };
    window.addEventListener("companion-config-updated", listener);

    const saved = saveCompanionConfig({ avatarScale: 70 });
    expect(saved.avatarScale).toBe(70);
    expect(notified).toBe(true);

    const retrieved = getCompanionConfig();
    expect(retrieved.avatarScale).toBe(70);

    window.removeEventListener("companion-config-updated", listener);
  });

  it("falls back to default scale when stored config lacks avatarScale", () => {
    window.localStorage.setItem(
      "openagent_companion_config",
      JSON.stringify({ name: "Custom Operator" })
    );

    const retrieved = getCompanionConfig();
    expect(retrieved.name).toBe("Custom Operator");
    expect(retrieved.avatarScale).toBe(85);
  });
});
