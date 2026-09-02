// Pure event -> view-node reducer for chat runs (projection layer).
//
// Both the live SSE path and the persisted-transcript hydration path produce
// the same ChatMessage[] shape through this module, so rendering is identical
// regardless of where state came from. Block ids come from a counter (never
// Date.now), which keeps live and replay states structurally comparable — see
// projection.test.ts.
//
// Side effects (toasts, session switches, refetches) are returned as data in
// ProjectionSide instead of being performed here: no React, no network.

export type ToolCallStatus = "running" | "done" | "error";

export interface ReasoningBlock {
  kind: "reasoning";
  id: string;
  content: string;
  streaming: boolean;
}

export interface TextBlock {
  kind: "text";
  id: string;
  content: string;
  streaming: boolean;
}

export interface SubagentToolCall {
  name: string;
  status: "running" | "done" | "error";
  args?: string;
  result?: string;
}

export interface SubagentActivity {
  agentName?: string;
  agentId?: string;
  stage?: string;
  thinking?: string;
  response?: string;
  tools?: SubagentToolCall[];
}

export interface ToolCallBlock {
  kind: "tool_call";
  id: string;
  callIndex: number;
  name: string;
  argsText: string;
  result?: string;
  progress?: string;
  status: ToolCallStatus;
  subagent?: SubagentActivity;
}

export interface StatsBlock {
  kind: "stats";
  id: string;
  tokensIn?: number;
  tokensOut?: number;
  costUsd?: number;
  latencyMs?: number;
  model?: string;
  toolCount?: number;
  finalization?: string;
  /** Run ended without any assistant text/reasoning — render as a failure. */
  noAnswer?: boolean;
}

export type AssistantBlock = ReasoningBlock | TextBlock | ToolCallBlock | StatsBlock;

export interface UserMessage {
  role: "user";
  id: string;
  content: string;
}

export interface AssistantMessage {
  role: "assistant";
  id: string;
  blocks: AssistantBlock[];
}

export interface ApprovalMessage {
  role: "approval";
  id: string;
  approvalId: string;
  toolName?: string;
  argsSnapshot?: unknown;
  status: "pending" | "approved" | "rejected" | "expired";
}

export interface ErrorMessage {
  role: "error";
  id: string;
  content: string;
}

export type ChatMessage = UserMessage | AssistantMessage | ApprovalMessage | ErrorMessage;

/** Effects the page layer performs after reducing an event. */
export interface ProjectionSide {
  /** Set/clear the thread status phase. */
  phase?: string | null;
  sessionId?: string;
  /** message_done seen — run reached its natural end. */
  terminal?: boolean;
  errorMessage?: string;
  budgetReason?: string;
  diverged?: boolean;
}

export interface RunProjectionState {
  messages: ChatMessage[];
  assistantId: string;
  nextId: number;
}

export interface ChatEvent {
  event: string;
  data?: Record<string, unknown>;
}

const KNOWN_EVENTS = new Set([
  "message_start",
  "reasoning",
  "token",
  "tool_call_delta",
  "tool_call",
  "tool_progress",
  "tool_result",
  "message_done",
  "error",
  "approval_required",
  "approval_rejected",
  "budget_exceeded",
  "replay_diverged",
]);

export function createRunProjection(
  assistantId: string,
  messages: ChatMessage[] = [],
): RunProjectionState {
  return { messages, assistantId, nextId: 0 };
}

/**
 * Marks all in-flight streaming blocks (text, reasoning) as non-streaming
 * without dropping any partial content. Used when user cancels or stops.
 */
export function stopProjectionStreaming(state: RunProjectionState): RunProjectionState {
  const messages = state.messages.map((m) => {
    if (m.role !== "assistant") return m;
    const hasStreaming = m.blocks.some(
      (b) => (b.kind === "text" || b.kind === "reasoning") && b.streaming,
    );
    if (!hasStreaming) return m;
    return {
      ...m,
      blocks: m.blocks.map((b) => {
        if (b.kind === "text" || b.kind === "reasoning") {
          return { ...b, streaming: false };
        }
        return b;
      }),
    };
  });
  return { ...state, messages };
}

/**
 * Reduce one chat stream event into view nodes. Returns a new state object;
 * sibling messages keep their references so React.memo stays effective.
 * Unknown events return the SAME state reference (cheap bail-out).
 */
export function applyChatEvent(
  state: RunProjectionState,
  ev: ChatEvent,
): { state: RunProjectionState; side: ProjectionSide } {
  const side: ProjectionSide = {};
  if (!KNOWN_EVENTS.has(ev.event)) return { state, side };

  const d = (ev.data ?? {}) as Record<string, any>;
  const messages = [...state.messages];
  let nextId = state.nextId;
  const genId = () => `${state.assistantId}-b${nextId++}`;

  const ai = messages.findIndex(
    (m) => m.role === "assistant" && m.id === state.assistantId,
  );
  let msg: AssistantMessage | null =
    ai >= 0
      ? { ...(messages[ai] as AssistantMessage), blocks: [...(messages[ai] as AssistantMessage).blocks] }
      : null;

  const ensureMsg = (): AssistantMessage => {
    if (!msg) msg = { role: "assistant", id: state.assistantId, blocks: [] };
    return msg;
  };

  const replaceBlock = (id: string, updated: AssistantBlock): void => {
    if (!msg) return;
    const i = msg.blocks.findIndex((b) => b.id === id);
    if (i >= 0) msg.blocks[i] = updated;
  };

  // Append-or-open semantics: tokens/reasoning continue the trailing block of
  // their kind; anything else in between starts a fresh block, which is what
  // preserves the true arrival order around tool rounds.
  const appendToKind = (kind: "text" | "reasoning", text: string): void => {
    const m = ensureMsg();
    const last = m.blocks.length > 0 ? m.blocks[m.blocks.length - 1] : undefined;
    if (last && last.kind === kind) {
      replaceBlock(last.id, { ...last, content: last.content + text } as AssistantBlock);
    } else if (kind === "text") {
      m.blocks.push({ kind: "text", id: genId(), content: text, streaming: true });
    } else {
      m.blocks.push({ kind: "reasoning", id: genId(), content: text, streaming: true });
    }
  };

  // Provider call index -> card. Prefer the open card; else the most recent
  // one sharing the index that has not been closed by a result yet.
  const findTool = (idx: number, openOnly: boolean): ToolCallBlock | undefined => {
    if (!msg) return undefined;
    for (let i = msg.blocks.length - 1; i >= 0; i -= 1) {
      const b = msg.blocks[i];
      if (b.kind !== "tool_call" || b.callIndex !== idx) continue;
      if (openOnly && b.status !== "running") continue;
      return b;
    }
    return undefined;
  };

  const resolvePriorApprovals = () => {
    for (let i = 0; i < messages.length; i++) {
      const m = messages[i];
      if (m.role === "approval" && m.status === "pending") {
        messages[i] = { ...m, status: "approved" };
      }
    }
  };

  switch (ev.event) {
    case "message_start": {
      ensureMsg();
      side.phase = "thinking";
      break;
    }

    case "reasoning": {
      resolvePriorApprovals();
      appendToKind("reasoning", String(d.content ?? ""));
      side.phase = "thinking";
      break;
    }

    case "token": {
      resolvePriorApprovals();
      appendToKind("text", String(d.delta ?? d.content ?? ""));
      side.phase = null;
      break;
    }

    case "tool_call_delta": {
      resolvePriorApprovals();
      ensureMsg();
      const idx = typeof d.index === "number" ? d.index : 0;
      const existing = findTool(idx, true);
      if (existing) {
        replaceBlock(existing.id, {
          ...existing,
          name: String(d.name || existing.name),
          argsText: existing.argsText + String(d.arguments ?? ""),
        });
      } else {
        msg!.blocks.push({
          kind: "tool_call",
          id: genId(),
          callIndex: idx,
          name: String(d.name || "tool"),
          argsText: String(d.arguments ?? ""),
          status: "running",
        });
      }
      break;
    }

    case "tool_call": {
      resolvePriorApprovals();
      ensureMsg();
      const idx = typeof d.index === "number" ? d.index : 0;
      const name = String(d.name || "tool");
      const argsRaw = d.args ?? d.arguments ?? {};
      const argsText =
        typeof argsRaw === "string" ? prettyJsonOrRaw(argsRaw) : JSON.stringify(argsRaw, null, 2);
      const existing = findTool(idx, true);
      if (existing) {
        replaceBlock(existing.id, { ...existing, name, argsText });
      } else {
        msg!.blocks.push({ kind: "tool_call", id: genId(), callIndex: idx, name, argsText, status: "running" });
      }
      side.phase = `tool:${name}`;
      break;
    }

    case "tool_progress": {
      resolvePriorApprovals();
      const idx = typeof d.index === "number" ? d.index : 0;
      const target = findTool(idx, true) ?? findTool(idx, false);
      if (target) {
        let subagent = target.subagent;
        const stage = typeof d.stage === "string" ? d.stage : undefined;
        const agentName = typeof d.agent_name === "string" ? d.agent_name : undefined;
        const agentId = typeof d.agent_id === "string" ? d.agent_id : undefined;

        if (stage?.startsWith("subagent_") || agentName) {
          subagent = { ...(subagent ?? {}) };
          if (agentName) subagent.agentName = agentName;
          if (agentId) subagent.agentId = agentId;
          if (stage) subagent.stage = stage;

          if (stage === "subagent_reasoning" && d.content) {
            subagent.thinking = (subagent.thinking ?? "") + String(d.content);
          } else if (stage === "subagent_token" && d.content) {
            subagent.response = (subagent.response ?? "") + String(d.content);
          } else if (stage === "subagent_tool_call" && d.tool_name) {
            const currentTools = subagent.tools ?? [];
            const argsStr = d.arguments ? (typeof d.arguments === "string" ? d.arguments : JSON.stringify(d.arguments, null, 2)) : undefined;
            subagent.tools = [...currentTools, { name: String(d.tool_name), status: "running", args: argsStr }];
          } else if (stage === "subagent_tool_result" && d.tool_name) {
            const resultStr = d.result != null ? (typeof d.result === "string" ? d.result : JSON.stringify(d.result, null, 2)) : undefined;
            const currentTools = (subagent.tools ?? []).map((t) =>
              t.name === d.tool_name && t.status === "running" ? { ...t, status: "done" as const, result: resultStr } : t,
            );
            subagent.tools = currentTools;
          }
        }

        const line = d.line != null ? String(d.line) : d.message != null ? String(d.message) : "";
        const progress = (target.progress ?? "") + line;
        replaceBlock(target.id, { ...target, progress, subagent });
      }
      if (d.name) side.phase = `tool:${String(d.name)}`;
      break;
    }

    case "tool_result": {
      resolvePriorApprovals();
      const idx = typeof d.index === "number" ? d.index : 0;
      const result = String(d.result ?? d.output ?? "");
      const target = findTool(idx, true) ?? findTool(idx, false);
      if (target) {
        replaceBlock(target.id, { ...target, result, status: looksFailed(result) ? "error" : "done" });
      }
      side.phase = "result";
      break;
    }

    case "message_done": {
      resolvePriorApprovals();
      // A run can die before emitting any content (crash after bootstrap);
      // still materialize the assistant so stats/noAnswer render.
      const assistant = ensureMsg();
      // Finalize every transient flag — the run is over, nothing streams.
      assistant.blocks = assistant.blocks.map((b): AssistantBlock => {
        if (b.kind === "text" || b.kind === "reasoning") return { ...b, streaming: false };
        if (b.kind === "tool_call" && b.status === "running") return { ...b, status: "done" };
        return b;
      });
      const usage = (d.usage ?? {}) as Record<string, any>;
      const liveToolCount = assistant.blocks.filter((b) => b.kind === "tool_call").length;
      const toolCount = Array.isArray(d.tools) ? d.tools.length : liveToolCount;
      const hasText = assistant.blocks.some((b) => b.kind === "text" && b.content.trim().length > 0);
      const hasReasoning = assistant.blocks.some((b) => b.kind === "reasoning" && b.content.trim().length > 0);
      if (!hasText) {
        // Explicit empty anchor so the bubble position stays visible; the
        // stats line carries the "no answer" hint for the renderer.
        assistant.blocks.push({ kind: "text", id: genId(), content: "", streaming: false });
      }
      const stats: StatsBlock = {
        kind: "stats",
        id: genId(),
        tokensIn: numOrUndef(usage.input_tokens),
        tokensOut: numOrUndef(usage.output_tokens),
        costUsd: numOrUndef(d.cost_usd),
        latencyMs: numOrUndef(d.latency_ms),
        model: strOrUndef(d.model),
        toolCount: toolCount > 0 ? toolCount : undefined,
        finalization: strOrUndef(d.finalization),
        noAnswer: !hasText && !hasReasoning,
      };
      const statsIdx = assistant.blocks.findIndex((b) => b.kind === "stats");
      if (statsIdx >= 0) assistant.blocks[statsIdx] = { ...stats, id: (assistant.blocks[statsIdx] as StatsBlock).id };
      else assistant.blocks.push(stats);
      side.terminal = true;
      side.phase = null;
      const sid = strOrUndef(d.session_id);
      if (sid) side.sessionId = sid;
      break;
    }

    case "error": {
      const message = String(d.message ?? "Stream error");
      if (!messages.some((m) => m.role === "error")) {
        messages.push({ role: "error", id: `${state.assistantId}-err`, content: message });
      }
      if (msg) {
        msg.blocks = msg.blocks.map((b) =>
          b.kind === "text" || b.kind === "reasoning" ? { ...b, streaming: false } : b,
        );
      }
      side.errorMessage = message;
      side.phase = null;
      break;
    }

    case "approval_required": {
      const approvalId = String(d.approval_id ?? "");
      if (approvalId && !messages.some((m) => m.role === "approval" && m.approvalId === approvalId)) {
        messages.push({
          role: "approval",
          id: `approval-${approvalId}`,
          approvalId,
          toolName: strOrUndef(d.tool_name),
          argsSnapshot: d.args_snapshot ?? {},
          status: "pending",
        });
      }
      side.phase = "approval";
      break;
    }

    case "approval_rejected": {
      const approvalId = String(d.approval_id ?? "");
      const idx2 = messages.findIndex((m) => m.role === "approval" && m.approvalId === approvalId);
      if (idx2 >= 0) {
        const a = messages[idx2] as ApprovalMessage;
        messages[idx2] = { ...a, status: "rejected" };
      }
      side.phase = null;
      break;
    }

    case "budget_exceeded":
      side.budgetReason = String(d.reason ?? "Run budget exceeded");
      side.phase = null;
      break;

    case "replay_diverged":
      side.diverged = true;
      side.phase = null;
      break;
  }

  if (msg) {
    if (ai >= 0) messages[ai] = msg;
    else messages.push(msg);
  }
  return { state: { messages, assistantId: state.assistantId, nextId }, side };
}

/** Heuristic mirrored from the legacy renderer: these markers render failed. */
export function looksFailed(result: string): boolean {
  const lowered = result.toLowerCase();
  return lowered.includes("error") || lowered.includes("exit code: 1");
}

function prettyJsonOrRaw(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

function numOrUndef(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

function strOrUndef(v: unknown): string | undefined {
  const s = typeof v === "string" ? v.trim() : "";
  return s.length > 0 ? s : undefined;
}

// ---------------------------------------------------------------------------
// Persisted-transcript hydration
// ---------------------------------------------------------------------------

export interface PersistedMessageRow {
  id: string;
  role: string;
  content: string;
  meta?: Record<string, unknown> | null;
}

/**
 * Project DB transcript rows into the same shape the live reducer produces so
 * a finished conversation renders exactly like the moment it streamed.
 * Mirrors the legacy ordering: historical tools before the body.
 */
export function messagesFromPersisted(rows: PersistedMessageRow[]): ChatMessage[] {
  return rows.map((row): ChatMessage => {
    if (row.role === "user") {
      return { role: "user", id: row.id, content: row.content };
    }
    const meta = (row.meta ?? {}) as Record<string, any>;
    let n = 0;
    const genId = () => `${row.id}-p${n++}`;
    const reasoning = typeof meta.reasoning === "string" ? meta.reasoning : "";
    const tools: any[] = Array.isArray(meta.tools) ? meta.tools : [];

    const blocks: AssistantBlock[] = [];
    if (reasoning.trim()) {
      blocks.push({ kind: "reasoning", id: genId(), content: reasoning, streaming: false });
    }
    for (const t of tools) {
      const argsRaw = t?.arguments ?? "";
      blocks.push({
        kind: "tool_call",
        id: genId(),
        callIndex: blocks.length,
        name: String(t?.name ?? "tool"),
        argsText:
          typeof argsRaw === "object" && argsRaw !== null
            ? JSON.stringify(argsRaw, null, 2)
            : prettyJsonOrRaw(String(argsRaw)),
        result: t?.result != null ? String(t.result) : undefined,
        status: t?.result != null && looksFailed(String(t.result)) ? "error" : "done",
      });
    }
    blocks.push({
      kind: "text",
      id: genId(),
      content: row.content,
      streaming: false,
    });
    const costUsd = numOrUndef(meta.cost_usd);
    const latencyMs = numOrUndef(meta.latency_ms);
    const model = strOrUndef(meta.model);
    const finalization = strOrUndef(meta.finalization);
    if (costUsd != null || latencyMs != null || numOrUndef(meta.in_tokens) != null || model || finalization) {
      blocks.push({
        kind: "stats",
        id: genId(),
        tokensIn: numOrUndef(meta.in_tokens),
        tokensOut: numOrUndef(meta.out_tokens),
        costUsd,
        latencyMs,
        model,
        toolCount: tools.length > 0 ? tools.length : undefined,
        finalization,
        noAnswer: !row.content?.trim() && !reasoning.trim(),
      });
    }
    return { role: "assistant", id: row.id, blocks };
  });
}
