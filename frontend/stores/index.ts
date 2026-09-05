import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ExecutionPolicy, GraphEdge, GraphNode } from "@/types";

interface AgentState {
  selectedAgentId: string | null;
  setSelectedAgent: (id: string | null) => void;
}

export const useAgentStore = create<AgentState>((set) => ({
  selectedAgentId: null,
  setSelectedAgent: (id) => set({ selectedAgentId: id }),
}));

interface WorkflowState {
  activeWorkflowId: string | null;
  activeWorkflowName: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeId: string | null;
  activeRunId: string | null;
  activeRunStatus: string | null;
  setGraph: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  setActiveWorkflow: (id: string | null, name: string) => void;
  setSelectedNode: (id: string | null) => void;
  setActiveRun: (id: string | null, status?: string | null) => void;
  reset: () => void;
}

export const useWorkflowStore = create<WorkflowState>()(
  persist(
    (set) => ({
      activeWorkflowId: null,
      activeWorkflowName: "",
      nodes: [],
      edges: [],
      selectedNodeId: null,
      activeRunId: null,
      activeRunStatus: null,
      setGraph: (nodes, edges) => set({ nodes, edges }),
      setActiveWorkflow: (id, name) => set({ activeWorkflowId: id, activeWorkflowName: name }),
      setSelectedNode: (id) => set({ selectedNodeId: id }),
      setActiveRun: (id, status = null) => set({ activeRunId: id, activeRunStatus: status }),
      reset: () =>
        set({
          activeWorkflowId: null,
          activeWorkflowName: "",
          nodes: [],
          edges: [],
          selectedNodeId: null,
          activeRunId: null,
          activeRunStatus: null,
        }),
    }),
    { name: "openagent-workflow-editor" },
  ),
);

interface ChatState {
  agentId: string | null;
  sessionId: string | null;
  activeRunId: string | null;
  debug: boolean;
  // Model the user picked for upcoming messages, kept per agent so switching
  // agents does not carry a selection that may not even be valid for the next
  // one. Persisted on purpose: this used to live in component state, so a
  // reload between picking a model and sending silently reverted the next
  // message to the agent default.
  pendingModelIdByAgent: Record<string, string>;
  pendingExecutionPolicy: ExecutionPolicy;
  hydrated: boolean;
  setAgent: (id: string | null) => void;
  setSession: (id: string | null) => void;
  setAgentAndSession: (agentId: string | null, sessionId: string | null) => void;
  setActiveRun: (id: string | null) => void;
  setDebug: (debug: boolean) => void;
  toggleDebug: () => void;
  setPendingModel: (agentId: string | null, modelId: string | null) => void;
  setPendingExecutionPolicy: (policy: ExecutionPolicy) => void;
  setHydrated: (hydrated: boolean) => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      agentId: null,
      sessionId: null,
      activeRunId: null,
      debug: false,
      pendingModelIdByAgent: {},
      pendingExecutionPolicy: "manual",
      hydrated: false,
      setAgent: (id) => set({ agentId: id }),
      setSession: (id) => set({ sessionId: id }),
      setAgentAndSession: (agentId, sessionId) => set({ agentId, sessionId }),
      setActiveRun: (id) => set({ activeRunId: id }),
      setDebug: (debug) => set({ debug }),
      toggleDebug: () => set((state) => ({ debug: !state.debug })),
      setPendingModel: (agentId, modelId) =>
        set((state) => {
          if (!agentId) return state;
          const next = { ...state.pendingModelIdByAgent };
          if (modelId) next[agentId] = modelId;
          else delete next[agentId];
          return { pendingModelIdByAgent: next };
        }),
      setPendingExecutionPolicy: (policy) => set({ pendingExecutionPolicy: policy }),
      setHydrated: (hydrated) => set({ hydrated }),
    }),
    {
      name: "openagent-chat-state",
      partialize: (state) => ({
        agentId: state.agentId,
        sessionId: state.sessionId,
        activeRunId: state.activeRunId,
        debug: state.debug,
        pendingModelIdByAgent: state.pendingModelIdByAgent,
        pendingExecutionPolicy: state.pendingExecutionPolicy,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHydrated(true);
      },
    },
  ),
);

export interface CanvasItem {
  title: string;
  code?: string;
  contentUrl?: string;
  downloadUrl?: string;
  language?: string;
  initialTab?: "code" | "preview";
}

interface CanvasState {
  isOpen: boolean;
  activeItem: CanvasItem | null;
  isFullscreen: boolean;
  panelWidthPercentage: number;
  openCanvas: (item: CanvasItem) => void;
  closeCanvas: () => void;
  toggleFullscreen: () => void;
  setPanelWidthPercentage: (width: number) => void;
}

export const useCanvasStore = create<CanvasState>()(
  persist(
    (set) => ({
      isOpen: false,
      activeItem: null,
      isFullscreen: false,
      panelWidthPercentage: 50,
      openCanvas: (item) => set({ isOpen: true, activeItem: item }),
      closeCanvas: () => set({ isOpen: false, activeItem: null, isFullscreen: false }),
      toggleFullscreen: () => set((state) => ({ isFullscreen: !state.isFullscreen })),
      setPanelWidthPercentage: (width) =>
        set({ panelWidthPercentage: Math.max(25, Math.min(75, Math.round(width))) }),
    }),
    {
      name: "openagent-canvas",
      partialize: (state) => ({
        isOpen: state.isOpen,
        activeItem: state.activeItem,
        panelWidthPercentage: state.panelWidthPercentage,
      }),
    },
  ),
);

