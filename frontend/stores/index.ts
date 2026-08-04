import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { GraphEdge, GraphNode } from "@/types";

interface AgentState {
  selectedAgentId: string | null;
  setSelectedAgent: (id: string | null) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  selectedAgentId: null,
  setSelectedAgent: (id) => set({ selectedAgentId: id }),
}));

interface WorkflowState {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeId: string | null;
  activeRunId: string | null;
  activeRunStatus: string | null;
  setGraph: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  setSelectedNode: (id: string | null) => void;
  setActiveRun: (id: string | null, status?: string | null) => void;
  reset: () => void;
}

export const useWorkflowStore = create<WorkflowState>()(
  persist(
    (set) => ({
      nodes: [],
      edges: [],
      selectedNodeId: null,
      activeRunId: null,
      activeRunStatus: null,
      setGraph: (nodes, edges) => set({ nodes, edges }),
      setSelectedNode: (id) => set({ selectedNodeId: id }),
      setActiveRun: (id, status = null) => set({ activeRunId: id, activeRunStatus: status }),
      reset: () => set({ nodes: [], edges: [], selectedNodeId: null, activeRunId: null, activeRunStatus: null }),
    }),
    { name: "openagent-workflow-editor" },
  ),
);

interface ChatState {
  agentId: string | null;
  sessionId: string | null;
  activeRunId: string | null;
  hydrated: boolean;
  setAgent: (id: string | null) => void;
  setSession: (id: string | null) => void;
  setActiveRun: (id: string | null) => void;
  setHydrated: (hydrated: boolean) => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      agentId: null,
      sessionId: null,
      activeRunId: null,
      hydrated: false,
      setAgent: (id) => set({ agentId: id }),
      setSession: (id) => set({ sessionId: id }),
      setActiveRun: (id) => set({ activeRunId: id }),
      setHydrated: (hydrated) => set({ hydrated }),
    }),
    {
      name: "openagent-chat-state",
      partialize: (state) => ({
        agentId: state.agentId,
        sessionId: state.sessionId,
        activeRunId: state.activeRunId,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHydrated(true);
      },
    },
  ),
);
