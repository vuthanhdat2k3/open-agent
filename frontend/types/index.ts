export interface Provider {
  id: string;
  key: string;
  name: string;
  base_url: string;
  env_var?: string;
  is_default: boolean;
  template_key?: string | null;
  api_key_configured: boolean;
  api_key_last4?: string | null;
  status: string;
  discovery_status: string;
  discovery_error?: string | null;
  models_discovered: number;
  last_discovery_attempt_at?: string | null;
  last_successful_discovery_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProviderTemplate {
  key: string;
  display_name: string;
  description: string;
  driver: string;
  default_base_url: string;
  api_key_required: boolean;
  supports_tools: boolean;
  supports_reasoning: boolean;
  supports_vision: boolean;
  catalog_source: string;
  catalog_version: string;
}

export interface ProviderTestResult {
  ok: boolean;
  latency_ms: number;
  model_count: number;
  message: string;
}

export interface ModelTestResult {
  ok: boolean;
  latency_ms: number;
  message: string;
  sample_response?: string | null;
  model_name?: string | null;
}

export type ModelTier = "economy" | "balanced" | "frontier";

export interface OrgModelTierMatrixResponse {
  tiers: Record<ModelTier, Model | null>;
}

export interface OrgModelTierMatrixUpdate {
  tier_mappings: Record<ModelTier, string | null>;
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
  enabled: boolean;
  discovered: boolean;
  source: "discovered" | "fallback" | "manual";
  last_seen_at?: string | null;
  catalog_source?: string | null;
  catalog_version?: string | null;
  last_discovered_at?: string | null;
  supports_tools?: boolean | null;
  supports_reasoning?: boolean | null;
  supports_vision?: boolean | null;
  created_at: string;
}

export interface Agent {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  model_id: string;
  tools: string[];
  allowed_risk_tiers: string[];
  max_iterations: number;
  temperature: number;
  enable_thinking: boolean | null;
  kind: "worker" | "orchestrator";
  active_release_id: string | null;
  latest_release_number: number;
  template_key?: string | null;
  is_customized?: boolean;
  is_pinned?: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentRelease {
  id: string;
  agent_id: string;
  version: number;
  status: "draft" | "published" | "archived";
  description: string;
  system_prompt: string;
  model_id: string;
  tools: string[];
  allowed_risk_tiers: string[];
  kind: "worker" | "orchestrator";
  max_iterations: number;
  temperature: number;
  change_note: string;
  config_hash: string;
  created_by_user_id: string | null;
  published_by_user_id: string | null;
  created_at: string;
  published_at: string | null;
}

export interface EvaluationCase {
  id: string;
  suite_id: string;
  input: string;
  expected_output: string | null;
  required_substrings: string[];
  expected_tools: string[];
  forbidden_patterns: string[];
  max_latency_ms: number | null;
  max_cost_usd: number | null;
  metadata: Record<string, unknown>;
  ordinal: number;
  added_in_version: number;
  created_at: string;
  updated_at: string;
}

export interface EvaluationSuite {
  id: string;
  name: string;
  description: string;
  agent_id: string;
  dataset_version: number;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
  cases: EvaluationCase[];
}

export interface EvaluationRun {
  id: string;
  suite_id: string;
  agent_release_id: string;
  baseline_run_id: string | null;
  dataset_version: number;
  execution_mode: "live" | "recorded";
  status: "running" | "completed" | "failed";
  total_cases: number;
  passed_cases: number;
  pass_rate: number;
  average_latency_ms: number;
  total_cost_usd: number;
  created_at: string;
  completed_at: string | null;
}

export interface EvaluationCaseInput {
  input: string;
  expected_output?: string | null;
  required_substrings?: string[];
  expected_tools?: string[];
  forbidden_patterns?: string[];
  max_latency_ms?: number | null;
  max_cost_usd?: number | null;
  metadata?: Record<string, unknown>;
}

export interface EvaluationSuiteInput {
  name: string;
  description?: string;
  agent_id: string;
  cases?: EvaluationCaseInput[];
}

export interface RecordedEvaluationOutput {
  case_id: string;
  output: string;
  observed_tools?: string[];
  latency_ms?: number;
  cost_usd?: number;
}

export interface EvaluationRunInput {
  agent_release_id: string;
  baseline_run_id?: string | null;
  execution_mode: "live" | "recorded";
  recorded_outputs?: RecordedEvaluationOutput[];
}

export interface OrganizationQuota {
  org_id: string;
  requests_per_minute: number;
  agent_runs_per_minute: number;
  max_concurrent_runs: number;
  monthly_cost_usd: number;
  max_agents: number | null;
  max_workflows: number | null;
  max_storage_bytes: number | null;
  enforcement_mode: "enforce" | "observe";
  updated_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface QuotaUsage {
  org_id: string;
  month: string;
  monthly_cost_usd: number;
  monthly_cost_limit_usd: number;
  agents: number;
  agent_limit: number | null;
  workflows: number;
  workflow_limit: number | null;
  storage_bytes: number;
  storage_limit_bytes: number | null;
  active_run_leases: number;
  concurrent_run_limit: number;
}

export interface AgentToolInfo {
  name: string;
  description: string;
  available: boolean;
  risk_tier?: "safe" | "read" | "write" | "execute" | "network" | "dangerous";
  allowed_for_orchestrator?: boolean;
  allowed_for_worker?: boolean;
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
  kind: "input" | "agent" | "tool" | "merge" | "output" | "approval" | "sub_workflow" | "scheduler" | "triager" | "integration";
  label: string;
  position?: { x: number; y: number };
  agent_id?: string;
  merge_mode?: "all" | "any";
  config: Record<string, any>;
  parameters?: Record<string, any>;
}

export interface GraphEdge {
  from_: string;
  to: string;
  condition?: string;
}

export interface NodeField {
  name: string;
  label: string;
  type: "string" | "time" | "date" | "textarea" | "number" | "boolean" | "options" | "multiOptions" | "collection" | "fixedCollection" | "json";
  default?: any;
  required?: boolean;
  description?: string;
  placeholder?: string;
  options?: Array<{ name: string; value: string; description?: string }>;
  load_options_from?: "tools" | "models" | "agents" | "workflows" | "connections" | "users" | "categories";
  display?: { show?: Record<string, any[]>; hide?: Record<string, any[]> };
  type_options?: Record<string, any>;
  advanced?: boolean;
  internal?: boolean;
  multiple?: boolean;
}

export interface NodeDefinition {
  kind: string;
  label: string;
  description: string;
  icon: string;
  fields: NodeField[];
  default_parameters: Record<string, any>;
}

export interface NodeOption {
  name: string;
  value: string;
  description?: string;
  risk_tier?: string;
  input_schema?: Record<string, any>;
}

export interface Workflow {
  id: string;
  name: string;
  description: string;
  graph: { nodes: GraphNode[]; edges: GraphEdge[] };
  template_key?: string;
  is_customized?: boolean;
  created_at: string;
  updated_at: string;
}

export type ExecutionPolicy = "read-only" | "manual" | "full-access";

export interface Session {
  id: string;
  agent_id: string;
  execution_policy: ExecutionPolicy;
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

export interface UploadedFile {
  id: string;
  original_name: string;
  content_type: string;
  size: number;
  status: "uploaded" | "queued" | "processing" | "retrying" | "ingested" | "error" | "dead_letter";
  collection: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface IngestResult {
  job_id: string;
  file_id: string;
  status: string;
  deduplicated: boolean;
  attempt_count: number;
  max_attempts: number;
  rag_document_id: string | null;
  chunk_count: number | null;
  warnings: string[];
  error_code: string | null;
  error_detail: string | null;
}

export interface WorkspaceArtifact {
  id: string;
  path: string;
  content_type: string;
  size: number;
  sha256: string;
  source_tool: string;
  agent_id: string | null;
  session_id: string | null;
  task_id: string | null;
  root_run_id: string | null;
  created_by_user_id?: string | null;
  creator_email?: string | null;
  creator_name?: string | null;
  exists: boolean;
  created_at: string;
  updated_at: string;
}

export interface SandboxExecution {
  id: string;
  source: string;
  language: string;
  command: string;
  status: "running" | "succeeded" | "failed" | "timed_out" | string;
  exit_code: number | null;
  duration_ms: number | null;
  stdout_preview: string;
  error: string | null;
  agent_id: string | null;
  session_id: string | null;
  task_id: string | null;
  root_run_id: string | null;
  created_by_user_id?: string | null;
  creator_email?: string | null;
  creator_name?: string | null;
  started_at: string;
  finished_at: string | null;
  created_at: string;
}

export interface OrgMember {
  user_id: string;
  email: string;
  display_name: string;
  // The backend's `/api/orgs/{id}/members` endpoint never returns `platform_admin`
  // (the roster filters them out) nor the legacy `admin` alias; canonical
  // `Role` covers every value the FE may receive.
  role: "platform_admin" | "org_admin" | "operator" | "user";
  created_at: string;
}

export interface ApiKey {
  id: string;
  name: string;
  key_prefix: string;
  created_at: string;
  expires_at: string | null;
}

export interface ApiKeyCreateResponse {
  api_key: ApiKey;
  secret_key: string;
}

export interface ApprovalRequest {
  id: string;
  org_id: string;
  run_type: "agent" | "workflow";
  run_id: string | null;
  tool_name: string | null;
  node_id: string | null;
  args_snapshot: Record<string, unknown>;
  case_id?: string | null;
  action?: string | null;
  status: "pending" | "approved" | "rejected" | "expired";
  requested_by: string | null;
  decided_by: string | null;
  reason: string;
  created_at: string;
  expires_at?: string | null;
  risk_level?: string;
  approval_mode?: string;
  capabilities?: Record<string, boolean | Record<string, string>>;
  server_time?: string | null;
}

export interface TaskTreeNode {
  id: string;
  parent_task_id: string | null;
  root_run_id: string;
  agent_id: string;
  goal: string;
  status: string;
  result: string | null;
  cost_usd: number;
  token_usage: Record<string, unknown>;
  depth: number;
  children: TaskTreeNode[];
}

export interface TaskTree {
  root_run_id: string;
  tasks: TaskTreeNode[];
}

export interface ChatRunDetail {
  id: string;
  status: string;
  result: string | null;
  error: string | null;
  message?: string | null;
  session_id?: string | null;
  // Live checkpoint written by the running loop (see backend chat_events).
  progress?: {
    session_id?: string;
    phase?: string;
    last_seq?: number;
    content_chars?: number;
    reasoning_chars?: number;
    updated_at?: string;
  };
  started_at?: string | null;
  finished_at?: string | null;
}

export type WorkflowNodeRunDetail = WorkflowRunDetail["nodes"][number];

export interface WorkflowRunDetail {
  id: string;
  org_id?: string;
  workflow_id: string;
  trigger_node_id?: string | null;
  trigger_type?: string | null;
  graph_hash?: string | null;
  status: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  error: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  nodes: Array<{
    id: string;
    node_id: string;
    status: string;
    attempt: number;
    input: Record<string, unknown>;
    output: Record<string, unknown>;
    error: string | null;
    started_at: string;
    finished_at: string | null;
    tokens?: number;
    cost_usd?: number;
    timing_ms?: number;
    data?: Record<string, unknown>;
  }>;
}

export interface UserMembership {
  org_id: string;
  org_name: string;
  org_slug: string;
  role: string;
}

export interface UserProfile {
  id: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
  // True when the current password was set by an admin (invite default reset);
  // the UI redirects to /settings/profile?force=1 until the user sets a new one.
  must_change_password?: boolean;
  created_at: string;
  memberships: UserMembership[];
  permissions_by_org: Record<string, string[]>;
  active_org_id?: string | null;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface CustomerIntelligenceConnection {
  id: string;
  provider: string;
  account_email: string;
  status: string;
  error: string | null;
  has_credentials: boolean;
  last_sync_at: string | null;
  created_at: string;
}

export interface CustomerIntelligenceSchedule {
  id: string;
  connection_id: string;
  enabled: boolean;
  run_time: string;
  timezone: string;
  last_run_at: string | null;
  next_run_at: string | null;
}


export interface CustomerIntelligenceCase {
  id: string;
  email_id: string;
  company_name: string | null;
  company_domain: string | null;
  status: string;
  confidence: number | null;
  trigger: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface CustomerIntelligenceSource {
  id: string;
  url: string;
  source_type: string;
  title: string;
  publisher: string | null;
  published_date: string | null;
  retrieved_date: string | null;
  excerpt: string;
  confidence: number | null;
}

export interface CustomerIntelligenceMeeting {
  id: string;
  provider_event_id: string;
  title: string;
  start_at: string | null;
  end_at: string | null;
  attendees: string[];
  match_type: string;
  confidence: number | null;
}

export interface CustomerIntelligenceCaseDetail extends CustomerIntelligenceCase {
  error: string | null;
  sources: CustomerIntelligenceSource[];
  meetings: CustomerIntelligenceMeeting[];
  report: {
    id: string;
    case_id: string;
    version: number;
    canonical_markdown: string;
    rendering: Record<string, any> | null;
    confidence: number | null;
    status: string;
    created_at: string;
  } | null;
}

export interface CustomerIntelligenceNotification {
  id: string;
  email_id: string;
  type: string;
  title: string;
  body: string;
  read_at: string | null;
  created_at: string;
  received_at: string;
  sender_email: string;
  sender_name: string | null;
  subject: string;
  classification: string;
}

export interface CustomerIntelligenceNotificationPage {
  items: CustomerIntelligenceNotification[];
  next_cursor: string | null;
  has_more: boolean;
  total: number;
  unread: number;
}

export interface EmailIntelligenceNavigationSummary {
  user_workspace: {
    inbox: { unread: number; urgent: number };
    research_cases: { active: number; failed: number };
    approvals: { pending: number; urgent: number };
  };
  admin_operations: {
    manual_reviews: { open: number; urgent: number };
    dead_letters: { total: number; urgent: number };
    connections: { unhealthy: number };
  };
  capabilities: {
    can_access_user_workspace: boolean;
    can_access_admin_operations: boolean;
  };
  meta: { server_time: string; reason_registry_version?: string; correlation_id?: string };
}
