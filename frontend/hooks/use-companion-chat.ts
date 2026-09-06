"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { api, streamSSE, type SseEvent } from "@/lib/api";
import { executeUiAction } from "@/lib/operator/ui-actions";

export interface CompanionMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  streaming?: boolean;
}

export interface CompanionApprovalPrompt {
  approvalId: string;
  toolName: string;
  runId: string;
}

const AGENT_ID = "sys-agent-general";

function genId(): string {
  return Math.random().toString(36).slice(2);
}

/**
 * Minimal chat orchestration for the 3D companion bubble — a smaller sibling
 * of app/chat/page.tsx's reducer, without artifact canvases or session
 * reattach: the companion is an ephemeral quick-operator surface, not a
 * replacement for the full /chat page.
 *
 * Owns the Client Tool Bridge side of the loop: a `ui_action` tool_progress
 * event is executed via the UI Action Registry and its result posted back to
 * `/api/chat/runs/{run_id}/ui-result` so the waiting backend tool call can
 * resume. See docs/companion-operator-agent-v2-spec.md.
 */
export function useCompanionChat() {
  const router = useRouter();
  const [messages, setMessages] = React.useState<CompanionMessage[]>([]);
  const [streaming, setStreaming] = React.useState(false);
  const [pendingApproval, setPendingApproval] = React.useState<CompanionApprovalPrompt | null>(null);
  const activeRunIdRef = React.useRef<string | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  // Defends against a ui_action event being delivered twice (e.g. a
  // reconnect replaying the durable log) re-running a browser side effect —
  // see spec §4.3.
  const executedCallIdsRef = React.useRef<Set<string>>(new Set());

  const appendAssistantDelta = React.useCallback((delta: string) => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.role === "assistant" && last.streaming) {
        return [...prev.slice(0, -1), { ...last, text: last.text + delta }];
      }
      return [...prev, { id: genId(), role: "assistant", text: delta, streaming: true }];
    });
  }, []);

  const finishAssistantMessage = React.useCallback(() => {
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      if (last && last.role === "assistant" && last.streaming) {
        return [...prev.slice(0, -1), { ...last, streaming: false }];
      }
      return prev;
    });
  }, []);

  const handleUiAction = React.useCallback(
    async (runId: string, data: Record<string, any>) => {
      const callId = String(data.call_id ?? "");
      const tool = String(data.tool ?? "");
      if (!callId || !tool) return;
      if (executedCallIdsRef.current.has(callId)) return;
      executedCallIdsRef.current.add(callId);

      const outcome = await executeUiAction(tool, data.args ?? {}, router);
      try {
        await api.post(`/api/chat/runs/${runId}/ui-result`, {
          call_id: callId,
          ok: outcome.ok,
          result: outcome.result ?? null,
          error: outcome.error ?? null,
        });
      } catch {
        // The waiting tool call times out on its own and reports a clear
        // error to the agent; nothing more to do client-side.
      }
    },
    [router],
  );

  const handleEvent = React.useCallback(
    (runId: string, ev: SseEvent) => {
      const d = ev.data || {};
      switch (ev.event) {
        case "token":
          appendAssistantDelta(String(d.delta ?? d.content ?? ""));
          break;
        case "tool_progress":
          if (d.type === "ui_action") void handleUiAction(runId, d);
          break;
        case "approval_required":
          setPendingApproval({ approvalId: d.approval_id, toolName: d.tool_name, runId: d.run_id || runId });
          break;
        case "message_done":
          finishAssistantMessage();
          setStreaming(false);
          break;
        case "error":
          finishAssistantMessage();
          setStreaming(false);
          setMessages((prev) => [...prev, { id: genId(), role: "assistant", text: `⚠️ ${d.message || "Đã xảy ra lỗi"}` }]);
          break;
        default:
          break;
      }
    },
    [appendAssistantDelta, finishAssistantMessage, handleUiAction],
  );

  const send = React.useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || streaming) return;
      setMessages((prev) => [...prev, { id: genId(), role: "user", text: trimmed }]);
      setStreaming(true);
      setPendingApproval(null);

      const runId = genId() + genId();
      activeRunIdRef.current = runId;
      abortRef.current = new AbortController();
      try {
        await streamSSE(
          "/api/chat",
          {
            agent_id: AGENT_ID,
            run_id: runId,
            message: trimmed,
            stream: true,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          },
          (ev) => handleEvent(runId, ev),
          abortRef.current.signal,
        );
      } catch (err: any) {
        if (err?.name !== "AbortError") {
          finishAssistantMessage();
          setMessages((prev) => [...prev, { id: genId(), role: "assistant", text: `⚠️ ${err?.message || "Kết nối bị gián đoạn"}` }]);
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [streaming, handleEvent, finishAssistantMessage],
  );

  const stop = React.useCallback(() => {
    abortRef.current?.abort();
    if (activeRunIdRef.current) {
      void api.post(`/api/chat/runs/${activeRunIdRef.current}/cancel`).catch(() => {});
    }
    setStreaming(false);
  }, []);

  return { messages, streaming, pendingApproval, send, stop, clearApprovalPrompt: () => setPendingApproval(null) };
}
