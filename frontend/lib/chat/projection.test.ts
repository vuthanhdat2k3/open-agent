import { describe, expect, it } from "vitest";
import {
  applyChatEvent,
  createRunProjection,
  looksFailed,
  messagesFromPersisted,
  type AssistantMessage,
  type ChatEvent,
  type ChatMessage,
} from "./projection";

function reduce(seq: Array<[string, Record<string, unknown>]>) {
  let state = createRunProjection("a-run");
  const sides = [];
  for (const [event, data] of seq) {
    const r = applyChatEvent(state, { event, data } as ChatEvent);
    state = r.state;
    sides.push(r.side);
  }
  return { state, sides };
}

const assistantOf = (state: ReturnType<typeof createRunProjection>) =>
  state.messages.find((m) => m.role === "assistant") as AssistantMessage;

describe("applyChatEvent", () => {
  it("accumulates consecutive tokens into one streaming text block", () => {
    const { state } = reduce([
      ["token", { content: "Hello" }],
      ["token", { content: " world" }],
    ]);
    const a = assistantOf(state);
    expect(a.blocks).toHaveLength(1);
    expect(a.blocks[0]).toMatchObject({ kind: "text", content: "Hello world", streaming: true });
  });

  it("streams into the run's own assistant message, not the first historical one", () => {
    const history: ChatMessage[] = [
      { role: "user", id: "u-old", content: "old question" },
      {
        role: "assistant",
        id: "a-old",
        blocks: [{ kind: "text", id: "a-old-b0", content: "old answer", streaming: false }],
      },
      { role: "user", id: "u-new", content: "new question" },
      { role: "assistant", id: "a-run", blocks: [] },
    ];
    let state = createRunProjection("a-run", history);
    for (const ev of [
      { event: "reasoning", data: { content: "thinking..." } },
      { event: "token", data: { delta: "new answer" } },
    ] as ChatEvent[]) {
      state = applyChatEvent(state, ev).state;
    }
    const oldMsg = state.messages.find((m) => m.id === "a-old") as AssistantMessage;
    const runMsg = state.messages.find((m) => m.id === "a-run") as AssistantMessage;
    expect(oldMsg.blocks[0]).toMatchObject({ content: "old answer", streaming: false });
    expect(runMsg.blocks).toHaveLength(2);
    expect(runMsg.blocks[0]).toMatchObject({ kind: "reasoning", content: "thinking..." });
    expect(runMsg.blocks[1]).toMatchObject({ kind: "text", content: "new answer" });
    expect(state.messages[state.messages.length - 1].id).toBe("a-run");
  });

  it("keeps true arrival order around a tool round", () => {
    const { state } = reduce([
      ["message_start", {}],
      ["reasoning", { content: "think" }],
      ["token", { content: "Let me check." }],
      ["tool_call", { index: 0, name: "web_fetch", args: { url: "https://x" } }],
      ["tool_result", { index: 0, name: "web_fetch", result: "page body" }],
      ["token", { content: "Done." }],
      ["message_done", { usage: { input_tokens: 10, output_tokens: 5 }, latency_ms: 1200 }],
    ]);
    const kinds = assistantOf(state).blocks.map((b) => b.kind);
    expect(kinds).toEqual(["reasoning", "text", "tool_call", "text", "stats"]);
    const tool = assistantOf(state).blocks[2];
    expect(tool).toMatchObject({
      kind: "tool_call",
      name: "web_fetch",
      status: "done",
      result: "page body",
      argsText: JSON.stringify({ url: "https://x" }, null, 2),
    });
    const stats = assistantOf(state).blocks[4] as any;
    expect(stats).toMatchObject({ kind: "stats", tokensIn: 10, tokensOut: 5, latencyMs: 1200 });
  });

  it("streams args via tool_call_delta then upgrades on tool_call", () => {
    const { state } = reduce([
      ["tool_call_delta", { index: 0, name: "run_code", arguments: '{"co' }],
      ["tool_call_delta", { index: 0, arguments: 'de": "1+1"}' }],
      ["tool_call", { index: 0, name: "run_code", args: { code: "1+1" } }],
    ]);
    const blocks = assistantOf(state).blocks;
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toMatchObject({
      kind: "tool_call",
      name: "run_code",
      argsText: JSON.stringify({ code: "1+1" }, null, 2),
      status: "running",
    });
  });

  it("matches out-of-order results across parallel call indexes", () => {
    const { state } = reduce([
      ["tool_call_delta", { index: 0, name: "a_tool", arguments: "{}" }],
      ["tool_call_delta", { index: 1, name: "b_tool", arguments: "{}" }],
      ["tool_result", { index: 1, name: "b_tool", output: "B ok" }],
      ["tool_result", { index: 0, name: "a_tool", result: "A error occurred" }],
    ]);
    const tools = assistantOf(state).blocks.filter((b) => b.kind === "tool_call");
    expect(tools[0]).toMatchObject({ name: "a_tool", result: "A error occurred", status: "error" });
    expect(tools[1]).toMatchObject({ name: "b_tool", result: "B ok", status: "done" });
  });

  it("attaches progress lines to the running card", () => {
    const { state } = reduce([
      ["tool_call", { index: 0, name: "run_shell", args: { cmd: "ls" } }],
      ["tool_progress", { index: 0, line: "file.txt\n" }],
      ["tool_progress", { index: 0, line: "dir/\n" }],
    ]);
    expect(assistantOf(state).blocks[0]).toMatchObject({ progress: "file.txt\ndir/\n", status: "running" });
  });

  it("attaches subagent thinking, tokens, and tools to the tool block", () => {
    const { state } = reduce([
      ["tool_call", { index: 0, name: "call_agent", args: { target_agent_id: "researcher", instruction: "Search news" } }],
      ["tool_progress", { index: 0, stage: "subagent_start", agent_name: "Researcher" }],
      ["tool_progress", { index: 0, stage: "subagent_reasoning", agent_name: "Researcher", content: "I should search for news." }],
      ["tool_progress", { index: 0, stage: "subagent_tool_call", agent_name: "Researcher", tool_name: "web_search" }],
      ["tool_progress", { index: 0, stage: "subagent_tool_result", agent_name: "Researcher", tool_name: "web_search" }],
      ["tool_progress", { index: 0, stage: "subagent_token", agent_name: "Researcher", content: "Here are the top headlines:" }],
    ]);
    const block = assistantOf(state).blocks[0] as any;
    expect(block.subagent).toMatchObject({
      agentName: "Researcher",
      thinking: "I should search for news.",
      response: "Here are the top headlines:",
      tools: [{ name: "web_search", status: "done" }],
    });
  });

  it("marks noAnswer and keeps an empty anchor when done without content", () => {
    const { state } = reduce([["message_done", { cost_usd: 0.01 }]]);
    const a = assistantOf(state);
    const stats = a.blocks.find((b) => b.kind === "stats") as any;
    expect(stats.noAnswer).toBe(true);
    expect(a.blocks.some((b) => b.kind === "text")).toBe(true);
  });

  it("upserts stats on duplicate terminal events instead of duplicating", () => {
    const { state } = reduce([
      ["message_done", { usage: { input_tokens: 1 }, cost_usd: 0.1 }],
      ["message_done", { usage: { input_tokens: 9 }, cost_usd: 0.2 }],
    ]);
    const statsBlocks = assistantOf(state).blocks.filter((b) => b.kind === "stats");
    expect(statsBlocks).toHaveLength(1);
    expect(statsBlocks[0]).toMatchObject({ tokensIn: 9, costUsd: 0.2 });
  });

  it("pushes only one error bubble for repeated error events", () => {
    const { state } = reduce([
      ["error", { message: "boom" }],
      ["error", { message: "boom" }],
    ]);
    expect(state.messages.filter((m) => m.role === "error")).toHaveLength(1);
  });

  it("tracks approval lifecycle", () => {
    const { state } = reduce([
      ["approval_required", { approval_id: "ap1", tool_name: "run_shell", args_snapshot: {} }],
      ["approval_rejected", { approval_id: "ap1" }],
    ]);
    const approval = state.messages.find((m) => m.role === "approval") as any;
    expect(approval.status).toBe("rejected");
  });

  it("returns identical state reference for unknown events", () => {
    const base = createRunProjection("a-run");
    const r = applyChatEvent(base, { event: "something_new", data: {} });
    expect(r.state).toBe(base);
    expect(r.side).toEqual({});
  });

  it("is deterministic: same event sequence -> equal state (live == replay)", () => {
    const seq: Array<[string, Record<string, unknown>]> = [
      ["message_start", {}],
      ["reasoning", { content: "hmm " }],
      ["reasoning", { content: "ok" }],
      ["token", { content: "Answer:" }],
      ["tool_call_delta", { index: 0, name: "t", arguments: '{"x"' }],
      ["tool_call_delta", { index: 0, arguments: ":1}" }],
      ["tool_call", { index: 0, name: "t", args: { x: 1 } }],
      ["tool_progress", { index: 0, line: "..." }],
      ["tool_result", { index: 0, name: "t", result: "ok" }],
      ["token", { content: " final" }],
      [
        "message_done",
        { usage: { input_tokens: 3, output_tokens: 4 }, cost_usd: 0.5, latency_ms: 42, model: "gpt-x", tools: [{ name: "t" }] },
      ],
    ];
    const a = reduce(seq).state;
    const b = reduce(seq).state;
    expect(JSON.stringify(a)).toEqual(JSON.stringify(b));
  });

  it("exposes phase/session/terminal through side effects only", () => {
    const { sides } = reduce([
      ["message_start", {}],
      ["token", { content: "hi" }],
      ["message_done", { session_id: "s1" }],
    ]);
    expect(sides[0].phase).toBe("thinking");
    expect(sides[1].phase).toBeNull();
    expect(sides[2]).toMatchObject({ terminal: true, sessionId: "s1", phase: null });
  });
});

describe("messagesFromPersisted", () => {
  it("hydrates a finished assistant row into ordered blocks", () => {
    const rows = [
      { id: "u1", role: "user", content: "draw a cat" },
      {
        id: "m1",
        role: "assistant",
        content: "Here you go.",
        meta: {
          reasoning: "planning svg",
          in_tokens: 20,
          out_tokens: 30,
          cost_usd: 0.02,
          latency_ms: 900,
          model: "gpt-x",
          tools: [{ name: "write_file", arguments: { path: "cat.svg" }, result: "<svg>cat</svg>" }],
        },
      },
    ];
    const msgs = messagesFromPersisted(rows);
    expect(msgs[0]).toEqual({ role: "user", id: "u1", content: "draw a cat" });
    const a = msgs[1] as AssistantMessage;
    expect(a.blocks.map((b) => b.kind)).toEqual(["reasoning", "tool_call", "text", "stats"]);
    expect(a.blocks[1]).toMatchObject({ name: "write_file", status: "done", result: "<svg>cat</svg>" });
    expect(a.blocks[3]).toMatchObject({ tokensIn: 20, tokensOut: 30, costUsd: 0.02, model: "gpt-x", toolCount: 1 });
  });
});

describe("looksFailed", () => {
  it("detects legacy failure markers", () => {
    expect(looksFailed("Error: timeout")).toBe(true);
    expect(looksFailed("exit code: 1\ntraceback")).toBe(true);
    expect(looksFailed("all good")).toBe(false);
  });
});
