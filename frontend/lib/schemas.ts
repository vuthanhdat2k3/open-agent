import { z } from "zod";

export const Tier = z.enum(["frontier", "balanced", "economy"]);
export const Transport = z.enum(["stdio", "sse", "http"]);
export const NodeKind = z.enum(["input", "agent", "tool", "merge", "output"]);

export const providerCreate = z.object({
  key: z
    .string()
    .min(1)
    .regex(/^[a-z0-9-]+$/, "lowercase letters, numbers, hyphens only"),
  name: z.string().min(1),
  base_url: z.string().min(1),
  api_key: z.string().optional().default(""),
  env_var: z.string().optional().default(""),
  is_default: z.boolean().optional(),
});
export type ProviderCreate = z.infer<typeof providerCreate>;

export const modelCreate = z.object({
  provider_id: z.string().min(1),
  name: z.string().min(1),
  display_name: z.string().min(1),
  tier: Tier,
  context_window: z.number().int().positive(),
  input_cost_per_1k: z.number().min(0),
  output_cost_per_1k: z.number().min(0),
  active: z.boolean().optional(),
});
export type ModelCreate = z.infer<typeof modelCreate>;

export const agentCreate = z.object({
  name: z.string().min(1),
  description: z.string().optional().default(""),
  system_prompt: z.string().optional().default(""),
  model_id: z.string().min(1),
  tools: z.array(z.string()).optional().default([]),
  max_iterations: z.number().int().positive().optional().default(12),
  temperature: z.number().min(0).max(2).optional().default(0.7),
});
export type AgentCreate = z.infer<typeof agentCreate>;

export const mcpServerCreate = z.object({
  name: z.string().min(1),
  transport: Transport,
  command: z.string().optional().default(""),
  args: z.array(z.string()).optional().default([]),
  env: z.record(z.string()).optional().default({}),
  url: z.string().optional().default(""),
  headers: z.record(z.string()).optional().default({}),
});
export type McpServerCreate = z.infer<typeof mcpServerCreate>;

export const graphNode = z.object({
  id: z.string(),
  kind: NodeKind,
  label: z.string().optional().default(""),
  agent_id: z.string().optional(),
  merge_mode: z.enum(["all", "any"]).optional().default("all"),
  config: z.record(z.any()).optional().default({}),
});
export type GraphNode = z.infer<typeof graphNode>;

export const graphEdge = z.object({
  from_: z.string(),
  to: z.string(),
  condition: z.string().optional(),
});
export type GraphEdge = z.infer<typeof graphEdge>;

export const workflowCreate = z.object({
  name: z.string().min(1),
  description: z.string().optional().default(""),
  graph: z.object({
    nodes: z.array(graphNode),
    edges: z.array(graphEdge),
  }),
});
export type WorkflowCreate = z.infer<typeof workflowCreate>;

export const chatRequest = z.object({
  agent_id: z.string().min(1),
  message: z.string().min(1),
  session_id: z.string().optional(),
  stream: z.boolean().optional().default(true),
});
export type ChatRequest = z.infer<typeof chatRequest>;

export const runWorkflowRequest = z.object({
  input: z.string().min(1),
  stream: z.boolean().optional().default(true),
});
export type RunWorkflowRequest = z.infer<typeof runWorkflowRequest>;
