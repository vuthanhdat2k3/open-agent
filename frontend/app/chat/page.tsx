"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { streamSSE } from "@/lib/api";
import { useAgents, useSessions, useSessionMessages, useDeleteSession, useModels, useChatRun } from "@/hooks";
import { useChatStore } from "@/stores";
import {
  Bot,
  MessageSquare,
  Plus,
  Send,
  Square,
  Cpu,
  Trash2,
  Sparkles,
  Bug,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { ChatMessageItem, type UIMessage } from "@/components/chat/chat-message-item";

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
  const sessions = useSessions();
  const delSession = useDeleteSession();
  const [agentReady, setAgentReady] = React.useState(false);
  const selectedSession = sessions.data?.find((s) => s.id === sessionId);
  const sessionBelongsToAgent = Boolean(
    agentReady && selectedSession && selectedSession.agent_id === agentId,
  );
  const messagesQuery = useSessionMessages(
    sessionId,
    agentReady && sessions.isSuccess && sessionBelongsToAgent,
  );
  const [modelOverrideId, setModelOverrideId] = React.useState("");
  const [draft, setDraft] = React.useState("");
  const [messages, setMessages] = React.useState<UIMessage[]>([]);
  // Live message store mutated during a stream, flushed to React state via
  // requestAnimationFrame so per-token events coalesce into one render per
  // frame instead of an O(n²) re-map for every token.
  const liveRef = React.useRef<UIMessage[]>([]);
  const rafRef = React.useRef<number | null>(null);
  const composeRef = React.useRef<Map<number, string>>(new Map());
  const deltaArgsRef = React.useRef<Map<number, string>>(new Map());
  const [streaming, setStreaming] = React.useState(false);
  const [phase, setPhase] = React.useState<string>("");
  const [debug, setDebug] = React.useState(true);
  const bottomRef = React.useRef<HTMLDivElement>(null);

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
    setModelOverrideId("");
  }, [agentId]);

  React.useEffect(() => {
    if (!agentReady || !sessions.isSuccess || !sessionId) return;
    const session = sessions.data?.find((s) => s.id === sessionId);
    if (!session || session.agent_id !== agentId) {
      liveRef.current = [];
      setMessages([]);
      setSession(null);
      setActiveRun(null);
    }
  }, [agentId, agentReady, sessionId, sessions.data, sessions.isSuccess, setActiveRun, setSession]);

  React.useEffect(() => {
    if (!agentReady || !sessionId || !sessionBelongsToAgent) {
      liveRef.current = [];
      setMessages([]);
      composeRef.current.clear();
      deltaArgsRef.current.clear();
      return;
    }
    if (messagesQuery.data) {
      const initial = messagesQuery.data.map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        meta: m.meta,
      }));
      liveRef.current = initial;
      setMessages(initial);
    }
  }, [agentReady, messagesQuery.data, sessionBelongsToAgent, sessionId]);

  React.useEffect(() => {
    const run = chatRun.data;
    if (!run) return;
    if (["succeeded", "failed", "diverged", "cancelled"].includes(run.status)) {
      setStreaming(false);
      setPhase("");
      messagesQuery.refetch();
      sessions.refetch?.();
      if (run.status !== "succeeded" && run.error) toast.error(run.error);
    } else {
      setStreaming(true);
    }
  }, [chatRun.data, messagesQuery, sessions, setActiveRun]);


  const currentAgent = agents.data?.find((a) => a.id === agentId);
  const currentAgentModel = models.data?.find((m) => m.id === currentAgent?.model_id);
  const effectiveModelId = modelOverrideId || currentAgent?.model_id || "";
  const effectiveModel = models.data?.find((m) => m.id === effectiveModelId);

  const commit = React.useCallback(() => {
    rafRef.current = null;
    setMessages([...liveRef.current]);
  }, []);

  const touch = React.useCallback(() => {
    if (rafRef.current == null) rafRef.current = requestAnimationFrame(commit);
  }, [commit]);

  const abortRef = React.useRef<AbortController | null>(null);

  const send = async () => {
    if (!draft.trim() || !agentId) return;
    const userMsg: UIMessage = { id: `u-${Date.now()}`, role: "user", content: draft };
    const assistantId = `a-${Date.now()}`;
    liveRef.current = [...liveRef.current, userMsg, { id: assistantId, role: "assistant", content: "" }];
    commit();
    const sentDraft = draft;
    setDraft("");
    setStreaming(true);
    composeRef.current.clear();
    deltaArgsRef.current.clear();

    const payload: Record<string, any> = {
      agent_id: agentId,
      message: sentDraft,
      session_id: sessionId || undefined,
      stream: true,
    };
    if (modelOverrideId) payload.model_id = modelOverrideId;

    abortRef.current = new AbortController();
    try {
      await streamSSE(
        `/api/chat`,
        payload,
        (ev) => {
          const d = ev.data;
          const msgs = liveRef.current;
          const aIdx = msgs.findIndex((x) => x.id === assistantId);
          if (ev.event === "session_start") {
            setSession(d.session_id);
          } else if (ev.event === "chat_run_start") {
            setActiveRun(d.run_id);
            setStreaming(true);
            setPhase("thinking");
          } else if (ev.event === "message_start") {
            setPhase("thinking");
          } else if (ev.event === "reasoning") {
            setPhase("thinking");
            if (aIdx >= 0) {
              const cur = msgs[aIdx];
              msgs[aIdx] = {
                ...cur,
                meta: { ...cur.meta, reasoning: (cur.meta?.reasoning ?? "") + (d.content ?? "") },
              };
            }
            touch();
          } else if (ev.event === "token") {
            setPhase("");
            if (aIdx >= 0) {
              const cur = msgs[aIdx];
              msgs[aIdx] = { ...cur, content: cur.content + (d.delta ?? d.content ?? "") };
            }
            touch();
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
            } else {
              const ti = msgs.findIndex((x) => x.id === toolId);
              if (ti >= 0) {
                msgs[ti] = { ...msgs[ti], content: deltaArgsRef.current.get(idx) ?? "" };
              }
            }
            touch();
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
            touch();
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
            touch();
          } else if (ev.event === "tool_result") {
            setPhase("result");
            msgs.push({
              id: `tr-${Date.now()}-${Math.random().toString(36).slice(2)}`,
              role: "tool_result",
              content: `${d.result ?? d.output ?? ""}`,
              meta: { toolName: d.name },
            });
            touch();
          } else if (ev.event === "message_done") {
            setPhase("");
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
            if (d.session_id) {
              setSession(d.session_id);
            }
            sessions.refetch?.();
          } else if (ev.event === "error") {
            setPhase("");
            toast.error(d.message ?? "Stream error");
          }
        },
        abortRef.current.signal,
      );
    } catch (e: any) {
      setStreaming(false);
      if (e.name !== "AbortError") toast.error(e.message);
    } finally {
      abortRef.current = null;
      // The POST/SSE connection only bootstraps a durable run. Its state is
      // controlled by useChatRun polling, including after a page reload.
      // Do not clear streaming here: the bootstrap request ending is not the
      // same thing as the agent run finishing.
    }
  };

  const stop = () => {
    abortRef.current?.abort();
  };

  const handleAgentChange = (nextAgentId: string) => {
    if (nextAgentId === agentId) return;
    abortRef.current?.abort();
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
    liveRef.current = [];
    setMessages([]);
    setActiveRun(null);
    setSession(nextSessionId);
    setStreaming(false);
    setPhase("");
  };

  const clearMessages = () => {
    abortRef.current?.abort();
    liveRef.current = [];
    setMessages([]);
    setSession(null);
    setActiveRun(null);
    setStreaming(false);
    setPhase("");
  };

  const hasLiveTools = messages.some((x) => x.role === "tool_call" || x.role === "tool_result");

  return (
    <div className="grid grid-cols-1 gap-6 lg:h-[calc(100vh-10rem)] lg:grid-cols-4 stagger">
      {/* Sidebar */}
      <div className="flex flex-col gap-4">
        <div className="rounded-xl border border-border/80 bg-card/50 p-4 space-y-4 backdrop-blur-xl shadow-3d-card">
          <div className="space-y-1.5">
            <Label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
              <Bot className="h-3.5 w-3.5 text-primary" /> Active Agent
            </Label>
            <Select value={agentId ?? ""} onChange={(e) => handleAgentChange(e.target.value)} className="w-full text-xs">
              {agents.data?.map((a) => (
                <option key={a.id} value={a.id}>{a.name}</option>
              ))}
            </Select>
            {currentAgentModel && (
              <div className="flex items-center gap-1.5 mt-1 px-2 py-1 rounded-md bg-muted/30 border border-border/30">
                <Cpu className="h-3 w-3 text-primary/70 shrink-0" />
                <span className="text-[10px] font-mono text-muted-foreground truncate">
                  {currentAgentModel.display_name || currentAgentModel.name}
                </span>
                <span className="ml-auto text-[9px] uppercase tracking-wider text-muted-foreground/50 shrink-0">
                  {currentAgentModel.tier}
                </span>
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <Label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
              <Cpu className="h-3.5 w-3.5 text-primary" /> Model Override
            </Label>
            <Select
              value={modelOverrideId}
              onChange={(e) => setModelOverrideId(e.target.value)}
              className="w-full text-xs"
            >
              <option value="">— Agent default —</option>
              {models.data
                ?.filter((m) => m.active)
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.display_name || m.name}
                  </option>
                ))}
            </Select>
            {modelOverrideId && effectiveModel && (
              <div className="flex items-center gap-1 px-2 py-1 rounded-md bg-primary/10 border border-primary/25">
                <span className="text-[10px] text-primary font-medium">
                  Override active
                </span>
                <span className="text-[10px] font-mono text-primary/80 ml-auto truncate">
                  {effectiveModel.display_name || effectiveModel.name}
                </span>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <Label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
              <MessageSquare className="h-3.5 w-3.5 text-primary" /> Chat Sessions
            </Label>
            <Button
              variant="outline"
              className="w-full gap-2 active-tactile transition-transform text-xs"
              onClick={clearMessages}
            >
              <Plus className="h-3.5 w-3.5" /> New Session
            </Button>
            <div className="space-y-1 max-h-[30vh] overflow-y-auto pr-1 scrollbar-thin">
              {sessions.data
                ?.filter((s) => s.agent_id === agentId)
                .map((s) => (
                  <div
                    key={s.id}
                    className={`group flex items-center gap-1 rounded-lg transition-all duration-200 ${
                      sessionId === s.id
                        ? "bg-primary text-primary-foreground shadow-3d-card font-semibold"
                        : "text-muted-foreground hover:bg-accent hover:text-foreground"
                    }`}
                  >
                    <button
                      onClick={() => handleSessionChange(s.id)}
                      className="block flex-1 truncate px-3 py-2 text-left text-xs"
                    >
                      {s.title}
                    </button>
                    <button
                      onClick={async (e) => {
                        e.stopPropagation();
                        if (!window.confirm(`Xóa phiên trò chuyện "${s.title}"? Hành động này không thể hoàn tác.`)) return;
                        await delSession.mutateAsync(s.id);
                        if (sessionId === s.id) {
                          clearMessages();
                        }
                      }}
                      className="shrink-0 rounded-md p-1.5 text-current/70 opacity-0 transition-opacity hover:bg-destructive/15 hover:text-destructive group-hover:opacity-100"
                      title="Delete session"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              {sessions.data?.filter((s) => s.agent_id === agentId).length === 0 && (
                <div className="text-[11px] text-muted-foreground/60 py-4 text-center">No active sessions.</div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Main Chat Stream */}
      <div className="flex min-h-[520px] flex-col lg:col-span-3">
        <Card glass className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <CardHeader className="flex flex-row items-center gap-3 space-y-0 border-b border-border/80 bg-muted/20 px-4 py-3">
            <div className="grid h-8 w-8 place-items-center rounded-xl bg-gradient-to-br from-primary/25 via-primary/10 to-transparent text-primary shadow-3d-card border border-primary/20">
              <MessageSquare className="h-4 w-4" />
            </div>
            <div className="flex-1 min-w-0">
              <CardTitle className="text-sm font-semibold tracking-tight">Conversation Thread</CardTitle>
              {currentAgent && (
                <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
                  {currentAgent.name}
                  {effectiveModel && (
                    <span className="text-muted-foreground/60"> · {effectiveModel.display_name || effectiveModel.name}</span>
                  )}
                </p>
              )}
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant={debug ? "secondary" : "ghost"}
                size="sm"
                className={`h-7 gap-1 px-2 text-[10px] ${debug ? "text-primary font-semibold" : "text-muted-foreground"}`}
                onClick={() => setDebug((v) => !v)}
                title="Toggle debug trace (thinking, tool calls, results)"
              >
                <Bug className="h-3.5 w-3.5" /> Debug
              </Button>
              {messages.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                  onClick={clearMessages}
                  title="Clear conversation"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
          </CardHeader>

          <CardContent className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4 scrollbar-thin">
            {messages.length === 0 ? (
              <div className="m-auto text-center max-w-sm animate-scale-in">
                <div className="grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-primary/25 via-primary/10 to-transparent text-primary shadow-3d-card border border-primary/20 mx-auto mb-4">
                  <Bot className="h-6 w-6" />
                </div>
                <p className="text-sm font-semibold tracking-tight">Ready to prompt</p>
                <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">
                  Start a conversation with <span className="text-foreground font-medium">{currentAgent?.name ?? "the selected agent"}</span>.
                  Tool actions will appear inline.
                </p>
                {effectiveModel && (
                  <div className="mt-3 inline-flex items-center gap-1.5 rounded-full bg-muted/40 border border-border/40 px-3 py-1">
                    <Cpu className="h-3 w-3 text-primary" />
                    <span className="text-[11px] font-mono text-muted-foreground">
                      {effectiveModel.display_name || effectiveModel.name}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <>
                {messages.map((m) => (
                  <ChatMessageItem key={m.id} message={m} debug={debug} hasLiveTools={hasLiveTools} />
                ))}
                <div ref={bottomRef} />
              </>
            )}
          </CardContent>
        </Card>

        <div className="mt-3 flex gap-2 items-end">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
            className="min-h-[48px] flex-1 text-xs resize-none"
          />
          <Button
            onClick={streaming ? stop : send}
            disabled={!agentId || (!streaming && !draft.trim())}
            className="gap-2 px-5 active-tactile transition-transform h-10 text-xs self-end"
            variant={streaming ? "outline" : "default"}
            title={streaming ? "Stop streaming" : "Send message"}
          >
            {streaming ? (
              <>
                <Square className="h-3.5 w-3.5" />
                Stop
              </>
            ) : (
              <>
                <Send className="h-3.5 w-3.5" />
                Send
              </>
            )}
          </Button>
        </div>

        {streaming && (
          <div className="mt-2 flex items-center gap-2 text-[10px] text-muted-foreground">
            {phase.startsWith("tool:") ? (
              <>
                <span className="h-1.5 w-1.5 rounded-full bg-info animate-pulse" />
                Using tool: {phase.slice(5)}…
              </>
            ) : phase === "result" ? (
              <>
                <span className="h-1.5 w-1.5 rounded-full bg-info animate-pulse" />
                Processing result…
              </>
            ) : null}
            {effectiveModel && <span className="font-mono text-muted-foreground/60">· {effectiveModel.display_name || effectiveModel.name}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
