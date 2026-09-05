import { describe, it, expect, vi } from "vitest";
import { filterCommands, getCommand, SLASH_COMMANDS } from "./commands/registry";
import type { SlashCommandContext } from "./commands/types";
import type { Model, Agent, ExecutionPolicy, UsageSummary } from "@/types";

describe("Slash Commands Registry & Handlers", () => {
  const mockModels: Model[] = [
    { id: "gpt-4o", name: "gpt-4o", display_name: "GPT-4o", active: true, tier: "frontier", supports_vision: true },
    { id: "claude-3-5-sonnet", name: "claude-3-5-sonnet", display_name: "Claude 3.5 Sonnet", active: true, tier: "frontier" },
    { id: "inactive-model", name: "inactive", display_name: "Inactive", active: false },
  ];

  const mockAgents: Agent[] = [
    { id: "agent-1", name: "Orchestrator Agent", kind: "orchestrator" },
    { id: "agent-2", name: "Code Worker", kind: "worker" },
  ];

  const mockUsage: UsageSummary[] = [
    {
      agent_name: "Code Worker",
      model_name: "gpt-4o",
      calls: 5,
      cost_usd: 0.125,
      input_tokens: 15000,
      output_tokens: 2500,
    },
  ];

  const createMockContext = (overrides?: Partial<SlashCommandContext>): SlashCommandContext => ({
    draft: "/test",
    models: mockModels,
    effectiveModel: mockModels[0],
    executionPolicy: "manual",
    agents: mockAgents,
    currentAgentId: "agent-1",
    sessionId: "sess-12345",
    usage: mockUsage,
    onModelChange: vi.fn(),
    onExecutionPolicyChange: vi.fn(),
    onClear: vi.fn(),
    onReset: vi.fn(),
    onAgentChange: vi.fn(),
    onSend: vi.fn(),
    onDraftChange: vi.fn(),
    openDialog: vi.fn(),
    notify: vi.fn(),
    tx: (vi: string, en: string) => vi,
    ...overrides,
  });

  describe("filterCommands & discovery", () => {
    it("returns all commands when query is empty", () => {
      const all = filterCommands("");
      expect(all.length).toBe(10);
      expect(all.map((c) => c.name)).toEqual([
        "model",
        "select-model",
        "policy",
        "agents",
        "compact",
        "context",
        "usage",
        "clear",
        "reset",
        "help",
      ]);
    });

    it("filters commands by prefix", () => {
      const result = filterCommands("mod");
      expect(result.some((c) => c.name === "model")).toBe(true);
    });

    it("filters commands by description when no prefix matches", () => {
      const result = filterCommands("ngữ cảnh");
      expect(result.some((c) => c.name === "context")).toBe(true);
    });

    it("finds command by exact name with getCommand", () => {
      const cmd = getCommand("context");
      expect(cmd).toBeDefined();
      expect(cmd?.name).toBe("context");
      expect(cmd?.icon).toBe("info");
    });
  });

  describe("Command Execution Behavior", () => {
    it("/context opens rich info dialog", () => {
      const ctx = createMockContext();
      const cmd = getCommand("context");
      expect(cmd).toBeDefined();
      const result = cmd?.execute("", ctx);
      expect(result).toBe(true);
      expect(ctx.openDialog).toHaveBeenCalledWith("context");
    });

    it("/usage opens rich info dialog", () => {
      const ctx = createMockContext();
      const cmd = getCommand("usage");
      expect(cmd).toBeDefined();
      const result = cmd?.execute("", ctx);
      expect(result).toBe(true);
      expect(ctx.openDialog).toHaveBeenCalledWith("usage");
    });

    it("/help opens rich info dialog", () => {
      const ctx = createMockContext();
      const cmd = getCommand("help");
      expect(cmd).toBeDefined();
      const result = cmd?.execute("", ctx);
      expect(result).toBe(true);
      expect(ctx.openDialog).toHaveBeenCalledWith("help");
    });

    it("/model switches model when matched and notifies success", () => {
      const ctx = createMockContext();
      const cmd = getCommand("model");
      expect(cmd).toBeDefined();
      const result = cmd?.execute("Claude", ctx);
      expect(result).toBe(true);
      expect(ctx.onModelChange).toHaveBeenCalledWith("claude-3-5-sonnet");
      expect(ctx.notify).toHaveBeenCalledWith(expect.stringContaining("Claude 3.5 Sonnet"), "success");
    });

    it("/model notifies error when model not found", () => {
      const ctx = createMockContext();
      const cmd = getCommand("model");
      const result = cmd?.execute("non-existent-model", ctx);
      expect(result).toBe(false);
      expect(ctx.onModelChange).not.toHaveBeenCalled();
      expect(ctx.notify).toHaveBeenCalledWith(expect.any(String), "error");
    });

    it("/policy switches execution policy when valid", () => {
      const ctx = createMockContext();
      const cmd = getCommand("policy");
      const result = cmd?.execute("full-access", ctx);
      expect(result).toBe(true);
      expect(ctx.onExecutionPolicyChange).toHaveBeenCalledWith("full-access");
      expect(ctx.notify).toHaveBeenCalledWith(expect.stringContaining("Toàn quyền"), "success");
    });

    it("/policy rejects invalid policy", () => {
      const ctx = createMockContext();
      const cmd = getCommand("policy");
      const result = cmd?.execute("invalid-policy", ctx);
      expect(result).toBe(false);
      expect(ctx.onExecutionPolicyChange).not.toHaveBeenCalled();
      expect(ctx.notify).toHaveBeenCalledWith(expect.any(String), "error");
    });

    it("/agents switches agent when matched", () => {
      const ctx = createMockContext();
      const cmd = getCommand("agents");
      const result = cmd?.execute("Code", ctx);
      expect(result).toBe(true);
      expect(ctx.onAgentChange).toHaveBeenCalledWith("agent-2");
      expect(ctx.notify).toHaveBeenCalledWith(expect.stringContaining("Code Worker"), "success");
    });

    it("/compact resets draft and sends prompt to agent", () => {
      const ctx = createMockContext();
      const cmd = getCommand("compact");
      const result = cmd?.execute("", ctx);
      expect(result).toBe(true);
      expect(ctx.onDraftChange).toHaveBeenCalledWith("");
      expect(ctx.onSend).toHaveBeenCalledWith(expect.stringContaining("tóm tắt ngắn gọn"));
    });

    it("/clear clears conversation history and notifies", () => {
      const ctx = createMockContext();
      const cmd = getCommand("clear");
      const result = cmd?.execute("", ctx);
      expect(result).toBe(true);
      expect(ctx.onDraftChange).toHaveBeenCalledWith("");
      expect(ctx.onClear).toHaveBeenCalled();
      expect(ctx.notify).toHaveBeenCalledWith(expect.any(String), "success");
    });

    it("/reset starts a new conversation", () => {
      const ctx = createMockContext();
      const cmd = getCommand("reset");
      const result = cmd?.execute("", ctx);
      expect(result).toBe(true);
      expect(ctx.onDraftChange).toHaveBeenCalledWith("");
      expect(ctx.onReset).toHaveBeenCalled();
    });
  });
});
