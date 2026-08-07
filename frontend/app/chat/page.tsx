"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { api, ApiError, streamSSE, streamSSEGet } from "@/lib/api";
import { useAgents, useSessions, useSessionMessages, useDeleteSession, useModels, useChatRun, useApprovals, useUpdateAgent } from "@/hooks";
import { useChatStore } from "@/stores";
import { type UIMessage } from "@/components/chat/chat-message-item";
import { ChatSidebar } from "@/components/chat/chat-sidebar";
import { ChatThread } from "@/components/chat/chat-thread";
import { ChatInput } from "@/components/chat/chat-input";
import type { ConnectionState } from "@/components/chat/chat-connection-banner";

export default function ChatPage() {
  const searchParams = useSearchParams();
  const agents = useAgents();
  const models = useModels();
  const {
    agentId,
    sessionId,
    activeRunId,
    hydrated: chatHydrated,
    setAgent,
    setSession,
    setActiveRun,
  } = useChatStore();
  const chatRun = useChatRun(activeRunId);

  // Destructured so the identity stays stable across polls: callbacks that
  // depend on the whole query object would change every 2s and defeat the
  // message-level memoisation in the thread.
  const { refetch: refetchChatRun } = chatRun;
  const approvals = useApprovals(Boolean(activeRunId));
  const sessions = useSessions();
  const delSession = useDeleteSession();
  const updateAgent = useUpdateAgent();
  const [agentReady, setAgentReady] = React.useState(false);
  const selectedSession = sessions.data?.find((s) => s.id === sessionId);
  const [draft, setDraft] = React.useState("");
  const [pendingSessionModelId, setPendingSessionModelId] = React.useState("");
  const [messages, setMessages] = React.useState<UIMessage[]>([]);
  // Live message store mutated during a stream, flushed to React state via
  // requestAnimationFrame so per-token events coalesce into one render per
  // frame instead of an O(n²) re-map for every token.
  const liveRef = React.useRef<UIMessage[]>([]);
  const rafRef = React.useRef<number | null>(null);
  const composeRef = React.useRef<Map<number, string>>(new Map());
  const deltaArgsRef = React.useRef<Map<number, string>>(new Map());
  // Typewriter drip buffer (declared here, used further down) — some
  // providers stream multi-word chunks per delta rather than single tokens;
  // this decouples display speed from provider chunk size. Hoisted above the
  // session/agent reset effects below so they can clear it directly.
  const typewriterRef = React.useRef<
    Map<string, { field: "content" | "reasoning"; full: string; shown: number }>
  >(new Map());
  const typewriterRafRef = React.useRef<number | null>(null);
  const [streaming, setStreamingState] = React.useState(false);
  // Guards the messages-loading effect: while a stream is live we must not let
  // a `refetch` wipe the partially-built UI.
  const streamingRef = React.useRef(false);
  // streamingRef must never lag one tick behind the streaming state: the
  // messages-merge effect below reads streamingRef.current synchronously to
  // decide whether a background refetch may overwrite the live optimistic
  // transcript. Updating it only from a useEffect(() => { ... }, [streaming])
  // means any effect that runs in the same commit before that effect (e.g.
  // right after send() calls setStreaming(true)) still sees the previous
  // value and can wipe out the just-sent user message + assistant
  // placeholder with stale DB data. Setting the ref inline here removes that
  // window entirely.
  const setStreaming = React.useCallback((value: boolean) => {
    streamingRef.current = value;
    setStreamingState(value);
  }, []);
  const [phase, setPhase] = React.useState<string>("");
  const [debug, setDebug] = React.useState(true);
  const [connectionState, setConnectionState] = React.useState<ConnectionState>("connected");
  const bottomRef = React.useRef<HTMLDivElement>(null);
  // Stable id of the in-flight assistant message for the *current* run. `send`
  // seeds it from Date.now(); a reattach seeds it from the run id so a rebuild
  // is deterministic. The shared event reducer reads it.
  const assistantIdRef = React.useRef<string>("");
  // Tracks which run we already (re)attached a follow-stream to, so the
  // reattach effect runs at most once per run.
  const attachedRunRef = React.useRef<string | null>(null);
  const terminalRunRef = React.useRef<string | null>(null);
  const reattachAbortRef = React.useRef<AbortController | null>(null);
  const lastEventSeqRef = React.useRef(0);
  // Tracks whether the user is pinned to the bottom of the thread so we only
  // auto-scroll while they are reading along (no yanking when they scroll up).
  const nearBottomRef = React.useRef(true);
  const scrollHostRef = React.useRef<HTMLDivElement>(null);

  // A newly-created session is announced by the stream before the sessions
  // query has refreshed. Keep the optimistic messages alive during that gap.
  const pendingSession = Boolean(
    agentReady && streaming && (!sessionId || !selectedSession),
  );
  const sessionBelongsToAgent = Boolean(
    agentReady &&
      ((selectedSession && selectedSession.agent_id === agentId) || pendingSession),
  );

  React.useEffect(() => {
    if (!activeRunId || !(chatRun.error instanceof ApiError) || chatRun.error.status !== 404) {
      return;
    }
    // A run can disappear after an API restart, or be an old localStorage
    // value. Stop polling it and let the next send establish a fresh run.
    reattachAbortRef.current?.abort();
    reattachAbortRef.current = null;
    attachedRunRef.current = null;
    terminalRunRef.current = null;
    setStreaming(false);
    setPhase("");
    setActiveRun(null);
  }, [activeRunId, chatRun.error, setActiveRun, setStreaming]);

  const messagesQuery = useSessionMessages(
    sessionId,
    agentReady && sessions.isSuccess && sessionBelongsToAgent,
  );
  const { refetch: refetchMessages } = messagesQuery;
  const { refetch: refetchSessions } = sessions;

  React.useEffect(() => {
    if (!chatHydrated || !agents.data?.length) return;
    const preselect = searchParams.get("agent");
    const resolvedAgentId =
      preselect && agents.data.some((a) => a.id === preselect)
        ? preselect
        : agentId && agents.data.some((a) => a.id === agentId)
          ? agentId
          : agents.data[0].id;
    if (agentId !== resolvedAgentId) setAgent(resolvedAgentId);
    setAgentReady(true);
  }, [agentId, agents.data, chatHydrated, searchParams, setAgent]);

  React.useEffect(() => {
    setPendingSessionModelId("");
  }, [agentId]);

  React.useEffect(() => {
    if (!agentReady || !sessions.isSuccess || !sessionId) return;
    const session = sessions.data?.find((s) => s.id === sessionId);
    // A streamed first message creates its session on the backend. The
    // session list can briefly lag behind the session_start event; do not
    // discard the persisted run while that new session is being indexed.
    if (!session && (activeRunId || pendingSession)) return;
    if (!session || session.agent_id !== agentId) {
      liveRef.current = [];
      typewriterRef.current.clear();
      setMessages([]);
      setSession(null);
      setActiveRun(null);
    }
  }, [activeRunId, agentId, agentReady, pendingSession, sessionId, sessions.data, sessions.isSuccess, setActiveRun, setSession]);

  React.useEffect(() => {
    if (!agentReady || pendingSession) return;
    if (!sessionId || !sessionBelongsToAgent) {
      liveRef.current = [];
      typewriterRef.current.clear();
      setMessages([]);
      composeRef.current.clear();
      deltaArgsRef.current.clear();
      return;
    }
    // While a stream is live (send or reattached follow) the partial UI is
    // authoritative; a background refetch must not overwrite it.
    if (messagesQuery.data) {
      const initial: UIMessage[] = messagesQuery.data.map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        meta: m.meta,
      }));
      const hasApproval = liveRef.current.some((message) => message.role === "approval");
      if (!streamingRef.current && !hasApproval) {
        liveRef.current = initial;
        setMessages(initial);
      } else {
        // Recovery may start before history finishes loading. Merge the
        // persisted transcript behind the already-replayed live events.
        const existing = liveRef.current;
        const merged = [...initial];
        for (const message of existing) {
          const duplicate = merged.some(
            (item) => item.role === message.role && item.content === message.content,
          );
          if (!duplicate) merged.push(message);
        }
        liveRef.current = merged;
        setMessages(merged);
      }
    }
  }, [agentReady, messagesQuery.data, pendingSession, sessionBelongsToAgent, sessionId, streaming]);

  React.useEffect(() => {
    const run = chatRun.data;
    if (!run) return;
    const recoveredSessionId = run.session_id || run.progress?.session_id;
    if (recoveredSessionId && recoveredSessionId !== sessionId) {
      setSession(recoveredSessionId);
    }
    if (run.status === "running" || run.status === "queued") {
      setPhase(run.progress?.phase && run.progress.phase !== "queued" ? run.progress.phase : "thinking");
    }
    if (["succeeded", "failed", "diverged", "cancelled", "waiting_approval"].includes(run.status)) {
      if (terminalRunRef.current === run.id) return;
      terminalRunRef.current = run.id;
      setStreaming(false);
      setPhase(run.status === "waiting_approval" ? "approval" : "");
      void refetchMessages();
      if (run.status !== "succeeded" && run.error) toast.error(run.error);
    } else {
      if (terminalRunRef.current !== run.id) terminalRunRef.current = null;
      setStreaming(true);
    }
  }, [chatRun.data, refetchMessages, sessionId, setSession, setStreaming]);

  // Smooth auto-scroll: follow the bottom only while the user is already
  // reading along, so streaming tokens don't yank them up if they scroll back.
  React.useEffect(() => {
    if (nearBottomRef.current && bottomRef.current) {
      bottomRef.current.scrollIntoView({ block: "end" });
    }
  }, [messages]);

  const onThreadScroll = React.useCallback(() => {
    const el = scrollHostRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    nearBottomRef.current = distance < 80;
  }, []);


  const currentAgent = agents.data?.find((a) => a.id === agentId);
  const currentAgentModel = models.data?.find((m) => m.id === currentAgent?.model_id);
  const effectiveModelId = pendingSessionModelId || currentAgent?.model_id || "";
  const effectiveModel = models.data?.find((m) => m.id === effectiveModelId);
  const statusPhase = phase || (streaming ? "answering" : "");

  const commit = React.useCallback(() => {
    rafRef.current = null;
    setMessages([...liveRef.current]);
  }, []);

  const touch = React.useCallback(() => {
    if (rafRef.current == null) rafRef.current = requestAnimationFrame(commit);
  }, [commit]);

  // Typewriter drip: some providers stream multi-word chunks per delta
  // (observed: 3-5 words/~20 chars every ~90ms) rather than single tokens.
  // Appending each chunk whole makes text visibly jump in clumps. This
  // buffers the *received* text separately per field and reveals it to the
  // DOM a few characters per animation frame, so display speed is decoupled
  // from provider chunk size — a fast provider still looks like smooth
  // character-by-character typing instead of racing ahead in bursts.
  // Characters revealed per frame. At 60fps this is ~900 chars/s, comfortably
  // faster than any real provider's token rate, so the buffer only smooths
  // bursts — it never falls behind and queues up a backlog.
  const TYPEWRITER_CHARS_PER_FRAME = 3;

  const applyTypewriterFrame = React.useCallback(() => {
    typewriterRafRef.current = null;
    let dirty = false;
    for (const [id, buf] of typewriterRef.current) {
      if (buf.shown >= buf.full.length) {
        typewriterRef.current.delete(id);
        continue;
      }
      buf.shown = Math.min(buf.full.length, buf.shown + TYPEWRITER_CHARS_PER_FRAME);
      const i = liveRef.current.findIndex((x) => x.id === id);
      if (i >= 0) {
        const cur = liveRef.current[i];
        const shownText = buf.full.slice(0, buf.shown);
        liveRef.current[i] =
          buf.field === "content"
            ? { ...cur, content: shownText }
            : { ...cur, meta: { ...cur.meta, reasoning: shownText } };
        dirty = true;
      }
    }
    if (dirty) commit();
    if (typewriterRef.current.size > 0) {
      typewriterRafRef.current = requestAnimationFrame(applyTypewriterFrame);
    }
  }, [commit]);

  const feedTypewriter = React.useCallback(
    (id: string, field: "content" | "reasoning", appended: string) => {
      const key = `${id}:${field}`;
      const existing = typewriterRef.current.get(key);
      if (existing) {
        existing.full += appended;
      } else {
        // Start from empty, not from whatever is already committed to
        // `messages` — the caller keeps the full text out of the message
        // object until the drip reveals it, so there is exactly one source
        // of "how much has actually been shown".
        typewriterRef.current.set(key, { field, full: appended, shown: 0 });
      }
      if (typewriterRafRef.current == null) {
        typewriterRafRef.current = requestAnimationFrame(applyTypewriterFrame);
      }
    },
    [applyTypewriterFrame],
  );

  const flushTypewriter = React.useCallback((id?: string) => {
    for (const [key, buf] of typewriterRef.current) {
      if (id && !key.startsWith(`${id}:`)) continue;
      buf.shown = buf.full.length;
      const i = liveRef.current.findIndex((x) => x.id === key.split(":")[0]);
      if (i >= 0) {
        const cur = liveRef.current[i];
        liveRef.current[i] =
          buf.field === "content"
            ? { ...cur, content: buf.full }
            : { ...cur, meta: { ...cur.meta, reasoning: buf.full } };
      }
      typewriterRef.current.delete(key);
    }
  }, []);

  // Shared SSE event reducer for chat runs. Used by both `send` (live POST
  // stream) and the reattach follow-stream, so a reload rebuilds the exact
  // same UI the user would have seen live. `assistantIdRef` carries the id of
  // the in-flight assistant message for the current run.
  const handleChatEvent = React.useCallback(
    (ev: { event: string; data: any }) => {
      const d = ev.data;
      const msgs = liveRef.current;
      const assistantId = assistantIdRef.current;
      const ensureAssistant = () => {
        const i = msgs.findIndex((x) => x.id === assistantId);
        if (i >= 0) return i;
        msgs.push({ id: assistantId, role: "assistant", content: "" });
        return msgs.length - 1;
      };
      if (ev.event === "message_start") {
        setPhase("thinking");
      } else if (ev.event === "reasoning") {
        setPhase("thinking");
        const i = ensureAssistant();
        feedTypewriter(msgs[i].id, "reasoning", d.content ?? "");
      } else if (ev.event === "token") {
        setPhase("");
        const i = ensureAssistant();
        feedTypewriter(msgs[i].id, "content", d.delta ?? d.content ?? "");
      } else if (ev.event === "tool_call_delta") {
        const idx = d.index ?? 0;
        const prev = deltaArgsRef.current.get(idx) ?? "";
        deltaArgsRef.current.set(idx, prev + (d.arguments ?? ""));
        let toolId = composeRef.current.get(idx);
        if (!toolId) {
          toolId = `tc-${Date.now()}-${idx}`;
          composeRef.current.set(idx, toolId);
          msgs.push({
            id: toolId,
            role: "tool_call",
            content: deltaArgsRef.current.get(idx) ?? "",
            meta: { toolName: d.name || "tool" },
          });
          // A brand-new tool card must land on screen before any later event
          // in this same batch (e.g. tool_result arriving in the same SSE
          // read/flush) can replace it — flush synchronously instead of
          // waiting for the shared end-of-handler touch()/RAF below.
          commit();
        } else {
          const ti = msgs.findIndex((x) => x.id === toolId);
          if (ti >= 0) msgs[ti] = { ...msgs[ti], content: deltaArgsRef.current.get(idx) ?? "" };
        }
      } else if (ev.event === "tool_call") {
        setPhase(`tool:${d.name}`);
        const idx = d.index ?? 0;
        const toolId = composeRef.current.get(idx);
        const card = {
          id: toolId ?? `tc-${Date.now()}-${idx}`,
          role: "tool_call",
          content: JSON.stringify(d.args ?? d.arguments ?? {}, null, 2),
          meta: { toolName: d.name },
        };
        if (toolId) {
          const ti = msgs.findIndex((x) => x.id === toolId);
          if (ti >= 0) msgs[ti] = card;
          else msgs.push(card);
        } else {
          composeRef.current.set(idx, card.id);
          msgs.push(card);
        }
        // Same reasoning as tool_call_delta above: the "Running" state must
        // be committed to React state before a fast tool's tool_result (which
        // can arrive in the same network read, i.e. the same synchronous
        // pass through this reducer) overwrites/appends past it.
        commit();
      } else if (ev.event === "tool_progress") {
        setPhase(`tool:${d.name}`);
        const toolId = composeRef.current.get(d.index ?? 0);
        const line = d.line ?? "";
        if (toolId) {
          const ti = msgs.findIndex((x) => x.id === toolId);
          if (ti >= 0) {
            const cur = msgs[ti];
            const progress = (cur.meta?.progress ?? "") + line;
            msgs[ti] = { ...cur, meta: { ...cur.meta, progress } };
          }
        }
      } else if (ev.event === "tool_result") {
        setPhase("result");
        msgs.push({
          id: `tr-${Date.now()}-${Math.random().toString(36).slice(2)}`,
          role: "tool_result",
          content: `${d.result ?? d.output ?? ""}`,
          meta: { toolName: d.name },
        });
      } else if (ev.event === "message_done") {
        setPhase("");
        flushTypewriter(assistantId);
        const filtered = msgs
          .filter((x) => x.role !== "tool_call" && x.role !== "tool_result")
          .map((x) =>
            x.id === assistantId
              ? {
                  ...x,
                  meta: {
                    ...x.meta,
                    in_tokens: d.usage?.input_tokens,
                    out_tokens: d.usage?.output_tokens,
                    cost_usd: d.cost_usd,
                    latency_ms: d.latency_ms,
                    tools: d.tools,
                    model: d.model,
                    ...(d.reasoning ? { reasoning: d.reasoning } : {}),
                  },
                }
              : x,
          );
        liveRef.current = filtered;
        commit();
        if (d.session_id) setSession(d.session_id);
        void refetchSessions();
      } else if (ev.event === "error") {
        setPhase("");
        toast.error(d.message ?? "Stream error");
      } else if (ev.event === "approval_required") {
        setPhase("approval");
        if (!msgs.some((x) => x.role === "approval" && x.meta?.approvalId === d.approval_id)) {
          msgs.push({
            id: `approval-${d.approval_id}`,
            role: "approval",
            content: "",
            meta: {
              approvalId: d.approval_id,
              approvalTool: d.tool_name,
              approvalArgs: d.args_snapshot ?? {},
              approvalStatus: "pending",
            },
          });
        }
      } else if (ev.event === "approval_rejected") {
        setPhase("");
        const i = msgs.findIndex((x) => x.meta?.approvalId === d.approval_id);
        if (i >= 0) msgs[i] = { ...msgs[i], meta: { ...msgs[i].meta, approvalStatus: "rejected" } };
      } else if (ev.event === "budget_exceeded") {
        setPhase("");
        toast.error(d.reason ?? "Run budget exceeded");
      } else if (ev.event === "replay_diverged") {
        setPhase("");
        toast.error("Run replay diverged and was stopped");
      }
      touch();
    },
    [commit, feedTypewriter, flushTypewriter, refetchSessions, setSession, touch],
  );

  // Stream recovery: after a reload / tab switch while a run is still in
  // flight, rebuild the exact UI from the durable event log and keep following
  // it live. The run id (and thus the log) survives in localStorage, so the
  // client reconnects instead of waiting blind until message_done.
  React.useEffect(() => {
    if (!chatHydrated || !agentReady) return;
    if (!activeRunId) return;
    if (attachedRunRef.current === activeRunId) return;
    const run = chatRun.data;
    if (!run) return;
    const TERMINAL = ["succeeded", "failed", "diverged", "cancelled", "waiting_approval"];
    if (TERMINAL.includes(run.status)) {
      // The run already finished by the time this effect saw its first
      // chatRun read (fast model + slow first poll tick). The other effect
      // that normally flips streaming off and refetches messages only runs
      // on the next chatRun poll (up to useChatRun's 2s interval) — without
      // this, the UI would sit in "streaming" for that whole window even
      // though the answer has been sitting in the DB the entire time.
      if (terminalRunRef.current !== run.id) {
        terminalRunRef.current = run.id;
        setStreaming(false);
        setPhase(run.status === "waiting_approval" ? "approval" : "");
        void refetchMessages();
        if (run.status !== "succeeded" && run.error) toast.error(run.error);
      }
      return;
    }
    attachedRunRef.current = activeRunId;
    setStreaming(true);
    assistantIdRef.current = `a-${activeRunId}`;
    lastEventSeqRef.current = 0;
    composeRef.current.clear();
    deltaArgsRef.current.clear();
    if (liveRef.current.length === 0 && run.message) {
      liveRef.current = [{ id: `u-${activeRunId}`, role: "user", content: run.message }];
      commit();
    }

    const ctrl = new AbortController();
    reattachAbortRef.current = ctrl;
    let stopped = false;
    const terminalEvents = new Set(["message_done", "error", "approval_required", "approval_rejected", "replay_diverged"]);
    const follow = async () => {
      let backoffMs = 500;
      while (!stopped && !ctrl.signal.aborted) {
        let terminalSeen = false;
        try {
          await streamSSEGet(
            `/api/chat/runs/${activeRunId}/events?follow=true&after_seq=${lastEventSeqRef.current}`,
            (ev) => {
              if (typeof ev.data?.seq === "number") lastEventSeqRef.current = ev.data.seq;
              if (terminalEvents.has(ev.event)) terminalSeen = true;
              handleChatEvent(ev);
            },
            ctrl.signal,
          );
          setConnectionState("connected");
          if (terminalSeen) break;
        } catch {
          if (stopped || ctrl.signal.aborted) break;
          // The follow stream dropped mid-run (network blip, server restart).
          // Surface a non-blocking banner while the backoff loop retries;
          // it clears itself on the next successful attempt above.
          setConnectionState("reconnecting");
        }
        if (stopped || ctrl.signal.aborted) break;
        await new Promise((resolve) => window.setTimeout(resolve, backoffMs));
        backoffMs = Math.min(backoffMs * 2, 5000);
      }
    };
    void follow();
    return () => {
      stopped = true;
      ctrl.abort();
      setConnectionState("connected");
      if (attachedRunRef.current === activeRunId) attachedRunRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    chatHydrated,
    agentReady,
    sessionId,
    sessionBelongsToAgent,
    activeRunId,
    chatRun.data?.status,
    refetchMessages,
  ]);

  React.useEffect(() => {
    const approval = approvals.data?.find((item) => item.run_id === activeRunId);
    if (!approval || liveRef.current.some((item) => item.meta?.approvalId === approval.id)) return;
    liveRef.current.push({
      id: `approval-${approval.id}`,
      role: "approval",
      content: "",
      meta: {
        approvalId: approval.id,
        approvalTool: approval.tool_name ?? undefined,
        approvalArgs: approval.args_snapshot,
        approvalStatus: approval.status === "expired" ? "rejected" : approval.status,
      },
    });
    commit();
    setPhase("approval");
  }, [activeRunId, approvals.data, commit]);

  const handleApprovalDecision = React.useCallback(async (messageId: string, decision: "approved" | "rejected") => {
    const message = liveRef.current.find((item) => item.id === messageId);
    const approvalId = message?.meta?.approvalId;
    if (!approvalId) return;
    liveRef.current = liveRef.current.map((item) => item.id === messageId
      ? { ...item, meta: { ...item.meta, approvalStatus: decision } }
      : item);
    commit();
    try {
      const decided = await api.post<{ status: "pending" | "approved" | "rejected" | "expired" }>(`/api/approvals/${approvalId}/decide`, { decision });
      const authoritative = decided.status === "expired" ? "rejected" : decided.status;
      liveRef.current = liveRef.current.map((item) => item.id === messageId
        ? { ...item, meta: { ...item.meta, approvalStatus: authoritative } }
        : item);
      commit();
      attachedRunRef.current = null;
      terminalRunRef.current = null;
      setStreaming(true);
      setPhase("thinking");
      await refetchChatRun();
    } catch (error) {
      liveRef.current = liveRef.current.map((item) => item.id === messageId
        ? { ...item, meta: { ...item.meta, approvalStatus: "pending" } }
        : item);
      commit();
      toast.error(error instanceof Error ? error.message : "Could not decide approval");
    }
  }, [commit, refetchChatRun, setStreaming]);

  const abortRef = React.useRef<AbortController | null>(null);
  const pageUnloadingRef = React.useRef(false);

  React.useEffect(() => {
    const markUnloading = () => {
      pageUnloadingRef.current = true;
    };
    window.addEventListener("pagehide", markUnloading);
    return () => window.removeEventListener("pagehide", markUnloading);
  }, []);

  const send = async () => {
    if (!draft.trim() || !agentId) return;
    const userMsg: UIMessage = { id: `u-${Date.now()}`, role: "user", content: draft };
    const assistantId = `a-${Date.now()}`;
    assistantIdRef.current = assistantId;
    lastEventSeqRef.current = 0;
    liveRef.current = [...liveRef.current, userMsg, { id: assistantId, role: "assistant", content: "" }];
    commit();
    const sentDraft = draft;
    setDraft("");
    setStreaming(true);
    composeRef.current.clear();
    deltaArgsRef.current.clear();

    const payload: Record<string, any> = {
      agent_id: agentId,
      run_id: crypto.randomUUID(),
      message: sentDraft,
      session_id: sessionId || undefined,
      stream: true,
    };
    if (pendingSessionModelId) payload.model_id = pendingSessionModelId;
    // The POST creates the durable Task and then emits chat_run_start. Do not
    // publish the run id before that frame: useChatRun would poll a row that
    // does not exist yet and produce a visible 404 race. Once the bootstrap
    // frame is received, the id is persisted and reload recovery remains
    // available.
    attachedRunRef.current = null;
    setActiveRun(null);

    abortRef.current = new AbortController();
    try {
      await streamSSE(
        `/api/chat`,
        payload,
        (ev) => {
          // session_start / chat_run_start only arrive on the live POST stream
          // (not on the reattach follow-stream); handle them, then delegate
          // everything else to the shared reducer used by both paths.
          if (ev.event === "session_start") {
            // The backend has persisted the selected model's release on this
            // session; subsequent requests use the normal pinned release.
            setPendingSessionModelId("");
            setSession(ev.data.session_id);
            void refetchSessions();
            return;
          }
          if (ev.event === "chat_run_start") {
            setActiveRun(ev.data.run_id);
            // The POST response only bootstraps the durable run. The
            // reattach effect owns the GET follow stream that carries live
            // tool_call/tool_progress/tool_result events.
            attachedRunRef.current = null;
            setStreaming(true);
            setPhase("thinking");
            return;
          }
          handleChatEvent(ev);
        },
        abortRef.current.signal,
      );
    } catch (e: any) {
      setStreaming(false);
      if (e.name !== "AbortError" && !pageUnloadingRef.current) {
        setActiveRun(null);
        toast.error(e.message);
      }
    } finally {
      abortRef.current = null;
      // The POST/SSE connection only bootstraps a durable run. Its state is
      // controlled by useChatRun polling, including after a page reload.
      // Do not clear streaming here: the bootstrap request ending is not the
      // same thing as the agent run finishing.
    }
  };

  const resetReattach = () => {
    reattachAbortRef.current?.abort();
    reattachAbortRef.current = null;
    attachedRunRef.current = null;
    setConnectionState("connected");
  };

  const resetTypewriter = () => {
    if (typewriterRafRef.current != null) {
      cancelAnimationFrame(typewriterRafRef.current);
      typewriterRafRef.current = null;
    }
    typewriterRef.current.clear();
  };

  const stop = () => {
    const runId = activeRunId;
    abortRef.current?.abort();
    resetReattach();
    resetTypewriter();
    setStreaming(false);
    setPhase("");
    setActiveRun(null);
    if (runId) {
      void api.post(`/api/chat/runs/${runId}/cancel`).catch(() => {
        // The local stream is already stopped; a missing/finished run needs no UI recovery.
      });
    }
  };

  const handleAgentChange = (nextAgentId: string) => {
    if (nextAgentId === agentId) return;
    abortRef.current?.abort();
    resetReattach();
    resetTypewriter();
    liveRef.current = [];
    setMessages([]);
    setSession(null);
    setActiveRun(null);
    setStreaming(false);
    setPhase("");
    setAgent(nextAgentId);
    setAgentReady(true);
  };

  const handleSessionChange = (nextSessionId: string) => {
    const nextSession = sessions.data?.find((s) => s.id === nextSessionId);
    if (!nextSession || nextSession.agent_id !== agentId) return;
    abortRef.current?.abort();
    resetReattach();
    resetTypewriter();
    liveRef.current = [];
    setMessages([]);
    setActiveRun(null);
    setSession(nextSessionId);
    setStreaming(false);
    setPhase("");
  };

  const clearMessages = () => {
    abortRef.current?.abort();
    resetReattach();
    resetTypewriter();
    liveRef.current = [];
    setMessages([]);
    setSession(null);
    setActiveRun(null);
    setStreaming(false);
    setPhase("");
  };

  const setDefaultModel = async (modelId: string) => {
    if (!agentId || modelId === currentAgent?.model_id) return;
    try {
      await updateAgent.mutateAsync({ id: agentId, model_id: modelId });
      setPendingSessionModelId(modelId);
      toast.success(
        sessionId
          ? "Agent default model updated. It will be used in this session on the next message."
          : "Agent default model updated.",
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update agent model");
    }
  };

  const hasLiveTools = messages.some((x) => x.role === "tool_call" || x.role === "tool_result");

  return (
    <div className="grid grid-cols-1 gap-6 lg:h-[calc(100vh-10rem)] lg:grid-cols-4">
      <ChatSidebar
        agents={agents.data}
        models={models.data}
        sessions={sessions.data}
        agentId={agentId}
        sessionId={sessionId}
        currentAgentModel={currentAgentModel}
        pendingSessionModelId={pendingSessionModelId}
        streaming={streaming}
        updateAgentPending={updateAgent.isPending}
        onAgentChange={handleAgentChange}
        onDefaultModelChange={(modelId) => void setDefaultModel(modelId)}
        onSessionChange={handleSessionChange}
        onNewSession={clearMessages}
        onDeleteSession={async (id) => {
          await delSession.mutateAsync(id);
          if (sessionId === id) clearMessages();
        }}
      />

      <div className="flex min-h-[520px] flex-col lg:col-span-3">
        <ChatThread
          messages={messages}
          debug={debug}
          streaming={streaming}
          statusPhase={statusPhase}
          currentAgent={currentAgent}
          effectiveModel={effectiveModel}
          onToggleDebug={() => setDebug((v) => !v)}
          onClearMessages={clearMessages}
          onApprovalDecision={handleApprovalDecision}
          scrollHostRef={scrollHostRef}
          bottomRef={bottomRef}
          onThreadScroll={onThreadScroll}
        />

        <ChatInput
          draft={draft}
          onDraftChange={setDraft}
          onSubmit={streaming ? stop : send}
          streaming={streaming}
          disabled={!agentId || (!streaming && !draft.trim())}
          connectionState={connectionState}
        />
      </div>
    </div>
  );
}

