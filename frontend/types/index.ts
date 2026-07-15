export interface Provider {
  id: string;
  key: string;
  name: string;
  base_url: string;
  api_key?: string;
  env_var?: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProviderTestResult {
  ok: boolean;
  latency_ms: number;
  model_count: number;
  message: string;
}

export interface Model {
  id: string;
  provider_id: string;
  name: string;
  display_name: string;
  tier: "frontier" | "balanced" | "economy";
  context_window: number;
  input_cost_per_1k: number;
  output_cost_per_1k: number;
  active: boolean;
  created_at: string;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  model_id: string;
  tools: string[];
  max_iterations: number;
  temperature: number;
  created_at: string;
  updated_at: string;
}

export interface AgentToolInfo {
  name: string;
  description: string;
  available: boolean;
}

export interface McpTool {
  id: string;
  server_id: string;
  name: string;
  description: string;
  input_schema: Record<string, any>;
  enabled: boolean;
}

export interface McpServer {
  id: string;
  name: string;
  transport: "stdio" | "sse" | "http";
  command: string;
  args: string[];
  env: Record<string, string>;
  url: string;
  headers: Record<string, string>;
  connection_status: "disconnected" | "connected" | "error";
  tools: McpTool[];
  created_at: string;
  updated_at: string;
}

export interface GraphNode {
  id: string;
  kind: "input" | "agent" | "tool" | "merge" | "output";
  label: string;
  agent_id?: string;
  merge_mode?: "all" | "any";
  config: Record<string, any>;
}

export interface GraphEdge {
  from_: string;
  to: string;
  condition?: string;
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  created_at: string;
  updated_at: string;
}

export interface Session {
  id: string;
  agent_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "tool_call" | "tool_result" | "system";
  content: string;
  meta: Record<string, any>;
  position: number;
  created_at: string;
}

export interface UsageSummary {
  agent_name: string;
  model_name: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number;
  calls: number;
}
