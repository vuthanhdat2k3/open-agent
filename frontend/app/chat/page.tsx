"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { api, ApiError, streamSSE, streamSSEGet } from "@/lib/api";
import {
  useAgents,
  useCurrentRole,
  useSessions,
  useSessionMessages,
  useDeleteSession,
  useModels,
  useChatRun,
  useApprovals,
  useUpdateAgent,
} from "@/hooks";
import { useChatStore } from "@/stores";
import {
  type ChatMessage,
  type RunProjectionState,
  createRunProjection,
  applyChatEvent,
  messagesFromPersisted,
  type PersistedMessageRow,
} from "@/lib/chat/projection";
import { ChatThread } from "@/components/chat/chat-thread";
import { ChatInput } from "@/components/chat/chat-input";
import type { ConnectionState } from "@/components/chat/chat-connection-banner";
import type { UploadedFile } from "@/types";

export default function ChatPage() {
  const searchParams = useSearchParams();
  const role = useCurrentRole();
  const agents = useAgents();
  const models = useModels();
  const {
    agentId,
    sessionId,
    activeRunId,
    pendingModelIdByAgent,
    hydrated: chatHydrated,
    setAgent,
    setSession,
    setActiveRun,
    setPendingModel,
  } = useChatStore();

  const pendingSessionModelId = (agentId && pendingModelIdByAgent[agentId]) || "";
  const setPendingSessionModelId = React.useCallback(
    (modelId: string) => setPendingModel(agentId, modelId || null),
    [agentId, setPendingModel],
  );
  const chatRun = useChatRun(activeRunId);
  const { refetch: refetchChatRun } = chatRun;
  const approvals = useApprovals(Boolean(activeRunId));
  const sessions = useSessions();
  const delSession = useDeleteSession();
  const updateAgent = useUpdateAgent();
  const [agentReady, setAgentReady] = React.useState(false);
  const selectedSession = sessions.data?.find((s) => s.id === sessionId);
  const [draft, setDraft] = React.useState("");
  const [attachments, setAttachments] = React.useState<UploadedFile[]>([]);

  // Projection state
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const projectionRef = React.useRef<RunProjectionState>(createRunProjection(""));

  const rafRef = React.useRef<number | null>(null);

  // Typewriter reveal buffer (maps blockId -> full & shown count)
  const typewriterRef = React.useRef<
    Map<string, { full: string; shown: number }>
  >(new Map());
  const typewriterRafRef = React.useRef<number | null>(null);

  const [streaming, setStreamingState] = React.useState(false);
  const streamingRef = React.useRef(false);
  const setStreaming = React.useCallback((value: boolean) => {
    streamingRef.current = value;
    setStreamingState(value);
  }, []);

  const [phase, setPhase] = React.useState<string>("");
  const [debug, setDebug] = React.useState(false);
  const [connectionState, setConnectionState] = React.useState<ConnectionState>("connected");
  const bottomRef = React.useRef<HTMLDivElement>(null);
  const assistantIdRef = React.useRef<string>("");
  const attachedRunRef = React.useRef<string | null>(null);
  const justStartedRunRef = React.useRef<string | null>(null);
  const terminalRunRef = React.useRef<string | null>(null);
  const terminalSyncRef = React.useRef(false);
  const reattachAbortRef = React.useRef<AbortController | null>(null);
  const lastEventSeqRef = React.useRef(0);
  const nearBottomRef = React.useRef(true);
  const scrollHostRef = React.useRef<HTMLDivElement>(null);

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

  const commit = React.useCallback(() => {
    rafRef.current = null;
    setMessages([...projectionRef.current.messages]);
  }, []);

  const touch = React.useCallback(() => {
    if (rafRef.current == null) rafRef.current = requestAnimationFrame(commit);
  }, [commit]);

  // Reveal buffer (Typewriter smoothing)
  const TYPEWRITER_CHARS_PER_FRAME = 3;

  const applyTypewriterFrame = React.useCallback(() => {
    typewriterRafRef.current = null;
    let dirty = false;

    for (const [blockId, buf] of typewriterRef.current) {
      if (buf.shown >= buf.full.length) {
        typewriterRef.current.delete(blockId);
        continue;
      }
      buf.shown = Math.min(buf.full.length, buf.shown + TYPEWRITER_CHARS_PER_FRAME);
      const shownText = buf.full.slice(0, buf.shown);

      // Find block in projection state and update content
      const msgs = projectionRef.current.messages;
      for (let mi = 0; mi < msgs.length; mi++) {
        const m = msgs[mi];
        if (m.role === "assistant") {
          const bi = m.blocks.findIndex((b) => b.id === blockId);
          if (bi >= 0) {
            const b = m.blocks[bi];
            if (b.kind === "text" || b.kind === "reasoning") {
              const updatedBlocks = [...m.blocks];
              updatedBlocks[bi] = { ...b, content: shownText };
              msgs[mi] = { ...m, blocks: updatedBlocks };
              dirty = true;
            }
            break;
          }
        }
      }
    }

    if (dirty) commit();
    if (typewriterRef.current.size > 0) {
      typewriterRafRef.current = requestAnimationFrame(applyTypewriterFrame);
    }
  }, [commit]);

  const feedTypewriter = React.useCallback(
    (blockId: string, fullContent: string) => {
      const existing = typewriterRef.current.get(blockId);
      if (existing) {
        existing.full = fullContent;
      } else {
        typewriterRef.current.set(blockId, { full: fullContent, shown: 0 });
      }
      if (typewriterRafRef.current == null) {
        typewriterRafRef.current = requestAnimationFrame(applyTypewriterFrame);
      }
    },
    [applyTypewriterFrame],
  );

  const flushTypewriter = React.useCallback(() => {
    if (typewriterRafRef.current != null) {
      cancelAnimationFrame(typewriterRafRef.current);
      typewriterRafRef.current = null;
    }
    for (const [blockId, buf] of typewriterRef.current) {
      const msgs = projectionRef.current.messages;
      for (let mi = 0; mi < msgs.length; mi++) {
        const m = msgs[mi];
        if (m.role === "assistant") {
          const bi = m.blocks.findIndex((b) => b.id === blockId);
          if (bi >= 0) {
            const b = m.blocks[bi];
            if (b.kind === "text" || b.kind === "reasoning") {
              const updatedBlocks = [...m.blocks];
              updatedBlocks[bi] = { ...b, content: buf.full };
              msgs[mi] = { ...m, blocks: updatedBlocks };
            }
            break;
          }
        }
      }
    }
    typewriterRef.current.clear();
  }, []);

  const resetTypewriter = React.useCallback(() => {
    if (typewriterRafRef.current != null) {
      cancelAnimationFrame(typewriterRafRef.current);
      typewriterRafRef.current = null;
    }
    typewriterRef.current.clear();
  }, []);

  const syncPersistedMessages = React.useCallback(async () => {
    if (!sessionId) return;
    terminalSyncRef.current = true;
    try {
      for (let attempt = 0; attempt < 8; attempt += 1) {
        const result = await refetchMessages();
        if (!result.isSuccess || !result.data) return;
        const persisted = messagesFromPersisted(result.data as PersistedMessageRow[]);
        const persistedHasAssistant = persisted.some((m) => m.role === "assistant");
        const liveHasAssistant = projectionRef.current.messages.some((m) => m.role === "assistant");

        if (!persistedHasAssistant && liveHasAssistant) {
          if (attempt < 7) {
            await new Promise((resolve) => window.setTimeout(resolve, 150));
            continue;
          }
          return;
        }

        if (persisted.length === 0 && projectionRef.current.messages.length > 0) {
          return;
        }

        if (rafRef.current != null) {
          cancelAnimationFrame(rafRef.current);
          rafRef.current = null;
        }
        resetTypewriter();
        projectionRef.current = createRunProjection(assistantIdRef.current, persisted);
        setMessages(persisted);
        return;
      }
    } finally {
      terminalSyncRef.current = false;
    }
  }, [refetchMessages, resetTypewriter, sessionId]);

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
    if (!agentReady || !sessions.isSuccess || !sessionId) return;
    const session = sessions.data?.find((s) => s.id === sessionId);
    if (!session && (activeRunId || pendingSession)) return;
    if (!session || session.agent_id !== agentId) {
      projectionRef.current = createRunProjection("");
      resetTypewriter();
      setMessages([]);
      setSession(null);
      setActiveRun(null);
    }
  }, [activeRunId, agentId, agentReady, pendingSession, resetTypewriter, sessionId, sessions.data, sessions.isSuccess, setActiveRun, setSession]);

  React.useEffect(() => {
    if (!agentReady || pendingSession) return;
    if (!sessionId || !sessionBelongsToAgent) {
      projectionRef.current = createRunProjection("");
      resetTypewriter();
      setMessages([]);
      return;
    }
    if (messagesQuery.data) {
      if (messagesQuery.data.length === 0 && chatRun.data?.status === "failed" && chatRun.data.error) {
        return;
      }
      const initial = messagesFromPersisted(messagesQuery.data as PersistedMessageRow[]);
      const hasPendingApproval = projectionRef.current.messages.some(
        (m) => m.role === "approval" && m.status === "pending",
      );
      const terminalSyncInFlight = terminalSyncRef.current;
      if (!streamingRef.current && !hasPendingApproval && !terminalSyncInFlight) {
        projectionRef.current = createRunProjection(assistantIdRef.current, initial);
        setMessages(initial);
      } else {
        const existing = projectionRef.current.messages;
        const merged = [...initial];
        for (const message of existing) {
          const duplicate = merged.some((item) => item.id === message.id);
          if (!duplicate) merged.push(message);
        }
        projectionRef.current = createRunProjection(assistantIdRef.current, merged);
        setMessages(merged);
      }
    }
  }, [agentReady, chatRun.data, messagesQuery.data, pendingSession, resetTypewriter, sessionBelongsToAgent, sessionId, streaming]);

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
      const alreadyTerminal = terminalRunRef.current === run.id;
      if (!alreadyTerminal) {
        terminalRunRef.current = run.id;
        setStreaming(false);
        setPhase(run.status === "waiting_approval" ? "approval" : "");
      }
      if (run.status !== "waiting_approval") {
        if (run.status === "failed" && run.error) {
          const message = run.message || "Your request";
          const current = [...projectionRef.current.messages];
          if (!current.some((item) => item.role === "user")) {
            current.unshift({ id: `u-${run.id}`, role: "user", content: message });
          }
          if (!current.some((item) => item.role === "error")) {
            current.push({ id: `e-${run.id}`, role: "error", content: run.error });
          }
          projectionRef.current = createRunProjection(assistantIdRef.current, current);
          setMessages(current);
        }
        if (!alreadyTerminal) void syncPersistedMessages();
      }
    } else {
      if (terminalRunRef.current !== run.id) terminalRunRef.current = null;
      setStreaming(true);
    }
  }, [chatRun.data, sessionId, setSession, setStreaming, syncPersistedMessages]);

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

  // Shared event handler using pure projection reducer
  const handleChatEvent = React.useCallback(
    (ev: { event: string; data?: any }) => {
      const { state: nextState, side } = applyChatEvent(projectionRef.current, ev);
      projectionRef.current = nextState;

      // Typewriter smoothing for live streaming text and reasoning blocks
      if (ev.event === "token" || ev.event === "reasoning") {
        const assistant = nextState.messages.find((m) => m.role === "assistant");
        if (assistant && assistant.role === "assistant") {
          const lastBlock = assistant.blocks[assistant.blocks.length - 1];
          if (lastBlock && (lastBlock.kind === "text" || lastBlock.kind === "reasoning")) {
            feedTypewriter(lastBlock.id, lastBlock.content);
          }
        }
      } else if (ev.event === "message_done") {
        flushTypewriter();
      }

      // Execute side effects
      if (side.phase !== undefined) setPhase(side.phase ?? "");
      if (side.terminal) {
        setStreaming(false);
        void syncPersistedMessages();
        void refetchSessions();
      }
      if (side.sessionId) setSession(side.sessionId);
      if (side.errorMessage) {
        setStreaming(false);
        toast.error(side.errorMessage);
      }
      if (side.budgetReason) {
        toast.error(side.budgetReason);
      }
      if (side.diverged) {
        toast.error("Run replay diverged and was stopped");
      }

      // For tool calls and structural additions, commit immediately for crisp feedback
      if (ev.event === "tool_call" || ev.event === "tool_call_delta" || ev.event === "message_done" || ev.event === "error") {
        commit();
      } else {
        touch();
      }
    },
    [commit, feedTypewriter, flushTypewriter, refetchSessions, setSession, setStreaming, syncPersistedMessages, touch],
  );

  const chatRunLoaded = Boolean(chatRun.data);

  // Stream recovery / follow effect
  React.useEffect(() => {
    if (!chatHydrated || !agentReady) return;
    if (!activeRunId) return;
    if (attachedRunRef.current === activeRunId) return;
    const run = chatRun.data;
    const justStarted = justStartedRunRef.current === activeRunId;
    if (!run && !justStarted) return;
    const TERMINAL = ["succeeded", "failed", "diverged", "cancelled", "waiting_approval"];
    if (run && TERMINAL.includes(run.status)) {
      if (terminalRunRef.current !== run.id) {
        terminalRunRef.current = run.id;
        setStreaming(false);
        setPhase(run.status === "waiting_approval" ? "approval" : "");
        if (run.status !== "waiting_approval") {
          void syncPersistedMessages();
        }
        if (run.status !== "succeeded" && run.error) toast.error(run.error);
      }
      return;
    }
    attachedRunRef.current = activeRunId;
    setStreaming(true);

    if (!justStarted) {
      assistantIdRef.current = `a-${activeRunId}`;
      lastEventSeqRef.current = 0;
      projectionRef.current = createRunProjection(assistantIdRef.current);
    }
    if (projectionRef.current.messages.length === 0 && run?.message) {
      const initialUser: ChatMessage[] = [{ id: `u-${activeRunId}`, role: "user", content: run.message }];
      projectionRef.current = createRunProjection(assistantIdRef.current, initialUser);
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
    chatRunLoaded,
    commit,
    handleChatEvent,
    syncPersistedMessages,
    setStreaming,
  ]);

  React.useEffect(() => {
    const approval = approvals.data?.find((item) => item.run_id === activeRunId);
    if (!approval || projectionRef.current.messages.some((item) => item.role === "approval" && item.approvalId === approval.id)) return;
    const approvalMsg: ChatMessage = {
      id: `approval-${approval.id}`,
      role: "approval",
      approvalId: approval.id,
      toolName: approval.tool_name ?? undefined,
      argsSnapshot: approval.args_snapshot,
      status: approval.status === "expired" ? "rejected" : approval.status,
    };
    projectionRef.current = {
      ...projectionRef.current,
      messages: [...projectionRef.current.messages, approvalMsg],
    };
    commit();
    setPhase("approval");
  }, [activeRunId, approvals.data, commit]);

  const handleApprovalDecision = React.useCallback(
    async (messageId: string, decision: "approved" | "rejected") => {
      const message = projectionRef.current.messages.find((item) => item.id === messageId);
      if (!message || message.role !== "approval") return;
      const approvalId = message.approvalId;

      projectionRef.current = {
        ...projectionRef.current,
        messages: projectionRef.current.messages.map((item) =>
          item.id === messageId && item.role === "approval" ? { ...item, status: decision } : item,
        ),
      };
      commit();

      try {
        const decided = await api.post<{ status: "pending" | "approved" | "rejected" | "expired" }>(
          `/api/approvals/${approvalId}/decide`,
          { decision },
        );
        const authoritative = decided.status === "expired" ? "rejected" : decided.status;
        projectionRef.current = {
          ...projectionRef.current,
          messages: projectionRef.current.messages.map((item) =>
            item.id === messageId && item.role === "approval" ? { ...item, status: authoritative } : item,
          ),
        };
        commit();
        attachedRunRef.current = null;
        terminalRunRef.current = null;
        setStreaming(true);
        setPhase("thinking");
        await refetchChatRun();
      } catch (error) {
        projectionRef.current = {
          ...projectionRef.current,
          messages: projectionRef.current.messages.map((item) =>
            item.id === messageId && item.role === "approval" ? { ...item, status: "pending" } : item,
          ),
        };
        commit();
        toast.error(error instanceof Error ? error.message : "Could not decide approval");
      }
    },
    [commit, refetchChatRun, setStreaming],
  );

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
    if ((!draft.trim() && attachments.length === 0) || !agentId) return;
    const attachmentNote = attachments.length
      ? `\n\n[Attached file${attachments.length > 1 ? "s" : ""}: ${attachments.map((f) => f.original_name).join(", ")}]`
      : "";
    const sentDraft = (draft.trim() ? draft : "Please review the attached file(s).") + attachmentNote;
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", content: sentDraft };
    const assistantId = `a-${Date.now()}`;
    assistantIdRef.current = assistantId;
    lastEventSeqRef.current = 0;

    const initialMessages: ChatMessage[] = [
      ...projectionRef.current.messages,
      userMsg,
      { role: "assistant", id: assistantId, blocks: [] },
    ];
    projectionRef.current = createRunProjection(assistantId, initialMessages);
    commit();
    setDraft("");
    setAttachments([]);
    setStreaming(true);

    const payload: Record<string, any> = {
      agent_id: agentId,
      run_id: crypto.randomUUID(),
      message: sentDraft,
      session_id: sessionId || undefined,
      stream: true,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    };
    if (pendingSessionModelId) payload.model_id = pendingSessionModelId;

    attachedRunRef.current = null;
    setActiveRun(null);

    abortRef.current = new AbortController();
    try {
      await streamSSE(
        `/api/chat`,
        payload,
        (ev) => {
          if (ev.event === "session_start") {
            setSession(ev.data.session_id);
            void refetchSessions();
            return;
          }
          if (ev.event === "chat_run_start") {
            justStartedRunRef.current = ev.data.run_id;
            setActiveRun(ev.data.run_id);
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
    }
  };

  const resetReattach = () => {
    reattachAbortRef.current?.abort();
    reattachAbortRef.current = null;
    attachedRunRef.current = null;
    justStartedRunRef.current = null;
    setConnectionState("connected");
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
      void api.post(`/api/chat/runs/${runId}/cancel`).catch(() => {});
    }
  };

  const handleAgentChange = (nextAgentId: string) => {
    if (nextAgentId === agentId) return;
    abortRef.current?.abort();
    resetReattach();
    resetTypewriter();
    projectionRef.current = createRunProjection("");
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
    projectionRef.current = createRunProjection("");
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
    projectionRef.current = createRunProjection("");
    setMessages([]);
    setSession(null);
    setActiveRun(null);
    setStreaming(false);
    setPhase("");
  };

  const setDefaultModel = async (modelId: string) => {
    if (!agentId) return;
    if (role !== "admin" && role !== "platform_admin" && role !== "operator") {
      setPendingSessionModelId(modelId);
      toast.success("Model selected for this chat");
      return;
    }
    if (modelId === currentAgent?.model_id) return;
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

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ChatThread
        messages={messages}
        debug={debug}
        streaming={streaming}
        statusPhase={statusPhase}
        agents={agents.data}
        models={models.data}
        sessions={sessions.data}
        agentId={agentId}
        sessionId={sessionId}
        currentAgent={currentAgent}
        currentAgentModel={currentAgentModel}
        effectiveModel={effectiveModel}
        pendingSessionModelId={pendingSessionModelId}
        updateAgentPending={updateAgent.isPending}
        onAgentChange={handleAgentChange}
        onDefaultModelChange={(modelId: string) => void setDefaultModel(modelId)}
        onSessionChange={handleSessionChange}
        onNewSession={clearMessages}
        onDeleteSession={async (id: string) => {
          try {
            await delSession.mutateAsync(id);
            if (sessionId === id) clearMessages();
            toast.success("Session deleted");
          } catch (error) {
            toast.error(error instanceof Error ? error.message : "Could not delete session");
          }
        }}
        onToggleDebug={() => setDebug((v) => !v)}
        onClearMessages={clearMessages}
        onApprovalDecision={handleApprovalDecision}
        draft={draft}
        onDraftChange={setDraft}
        onSubmit={send}
        composerDisabled={!agentId || (!draft.trim() && attachments.length === 0)}
        attachments={attachments}
        onAttachmentsChange={setAttachments}
        scrollHostRef={scrollHostRef}
        bottomRef={bottomRef}
        onThreadScroll={onThreadScroll}
      />

      {messages.length > 0 && (
        <div className="mx-auto w-full max-w-[var(--dsh-chat-content-width,736px)] px-4 pb-4 sm:px-6">
          <ChatInput
            draft={draft}
            onDraftChange={setDraft}
            onSubmit={streaming ? stop : send}
            disabled={!agentId || (!streaming && !draft.trim() && attachments.length === 0)}
            streaming={streaming}
            connectionState={connectionState}
            attachments={attachments}
            onAttachmentsChange={setAttachments}
          />
        </div>
      )}
    </div>
  );
}
