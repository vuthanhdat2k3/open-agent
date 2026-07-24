import { create } from "zustand";
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
  setGraph: (nodes: GraphNode[], edges: GraphEdge[]) => void;
  setSelectedNode: (id: string | null) => void;
  reset: () => void;
}

export const useWorkflowStore = create<WorkflowState>((set) => ({
  nodes: [],
  edges: [],
  selectedNodeId: null,
  setGraph: (nodes, edges) => set({ nodes, edges }),
  setSelectedNode: (id) => set({ selectedNodeId: id }),
  reset: () => set({ nodes: [], edges: [], selectedNodeId: null }),
}));

interface ChatState {
  sessionId: string | null;
  setSession: (id: string | null) => void;
}

export const useChatStore = create<ChatState>((set) => ({
  sessionId: null,
  setSession: (id) => set({ sessionId: id }),
}));
