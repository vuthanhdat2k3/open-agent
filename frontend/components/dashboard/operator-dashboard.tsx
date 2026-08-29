"use client";

import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Bot,
  Cpu,
  FlaskConical,
  FolderKanban,
  Layers,
  Network,
  Plug,
  Plus,
  Server,
  Sparkles,
  Workflow,
  Zap,
} from "lucide-react";
import {
  useAgents,
  useEvaluationSuites,
  useFiles,
  useMcpServers,
  useMe,
  useModels,
  useProviders,
  useWorkflows,
} from "@/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "@/components/shared";
import { useTranslation } from "@/lib/i18n";

export function OperatorDashboard() {
  const { t, dict, tx, locale } = useTranslation();
  const me = useMe();
  const agents = useAgents();
  const workflows = useWorkflows();
  const providers = useProviders(true);
  const models = useModels(true);
  const mcp = useMcpServers(true);
  const files = useFiles();
  const evaluations = useEvaluationSuites();

  const name = me.data?.display_name || me.data?.email?.split("@")[0] || "Operator";

  function getGreeting() {
    const hour = new Date().getHours();
    if (hour < 12) return dict.pages.dashboard.greetingMorning;
    if (hour < 18) return dict.pages.dashboard.greetingAfternoon;
    return dict.pages.dashboard.greetingEvening;
  }

  const agentList = agents.data ?? [];
  const workflowList = workflows.data ?? [];
  const mcpList = mcp.data ?? [];
  const fileList = files.data ?? [];
  const evalList = evaluations.data ?? [];

  return (
    <div className="space-y-8">
      {/* Hero Banner */}
      <section className="flex flex-col gap-6 rounded-xl border border-primary/25 bg-card/75 p-6 shadow-card sm:p-8 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl space-y-3">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="border-primary/40 bg-primary/10 text-primary font-semibold">
              <Zap className="mr-1 h-3.5 w-3.5" />
              {tx("AI Studio & Vận hành", "AI Studio & Operator")}
            </Badge>
            <span className="text-xs text-muted-foreground">• {tx("Trung tâm Kỹ sư AI", "AI Engineering Hub")}</span>
          </div>
          <p className="text-sm font-semibold text-primary">{getGreeting()}, {name}</p>
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            {dict.pages.dashboard.titleOperator}
          </h1>
          <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">
            {dict.pages.dashboard.descOperator}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button asChild className="gap-2">
            <Link href="/agents">
              <Plus className="h-4 w-4" />
              {dict.pages.dashboard.btnNewAgent}
            </Link>
          </Button>
          <Button asChild variant="outline" className="gap-2">
            <Link href="/workflows">
              <Workflow className="h-4 w-4" />
              {dict.pages.dashboard.btnDesignWorkflow}
            </Link>
          </Button>
          <Button asChild variant="ghost" className="gap-2">
            <Link href="/evaluations">
              <FlaskConical className="h-4 w-4" />
              {dict.pages.dashboard.btnRunEvaluation}
            </Link>
          </Button>
        </div>
      </section>

      {/* KPI Stats Grid */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-5 flex items-center justify-between border-border/80 bg-card">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{tx("Agent đã cấu hình", "Configured Agents")}</p>
            <p className="text-2xl font-bold tracking-tight text-foreground tabular-nums">{agentList.length}</p>
            <p className="text-xs text-muted-foreground">{tx("Trợ lý sẵn sàng thực thi", "Ready for deployment")}</p>
          </div>
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary">
            <Bot className="h-6 w-6" />
          </div>
        </Card>

        <Card className="p-5 flex items-center justify-between border-border/80 bg-card">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{dict.pages.dashboard.statWorkflowsTotal}</p>
            <p className="text-2xl font-bold tracking-tight text-foreground tabular-nums">{workflowList.length}</p>
            <p className="text-xs text-muted-foreground">{tx("Quy trình DAG tự động", "Active DAG pipelines")}</p>
          </div>
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary">
            <Workflow className="h-6 w-6" />
          </div>
        </Card>

        <Card className="p-5 flex items-center justify-between border-border/80 bg-card">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{dict.pages.dashboard.statMcpConnected}</p>
            <p className="text-2xl font-bold tracking-tight text-foreground tabular-nums">{mcpList.length}</p>
            <p className="text-xs text-muted-foreground">{tx("Giao thức MCP Tools", "External tool integrations")}</p>
          </div>
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary">
            <Plug className="h-6 w-6" />
          </div>
        </Card>

        <Card className="p-5 flex items-center justify-between border-border/80 bg-card">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{dict.pages.dashboard.statKnowledgeDocs}</p>
            <p className="text-2xl font-bold tracking-tight text-foreground tabular-nums">{fileList.length}</p>
            <p className="text-xs text-muted-foreground">{tx("Tài liệu đã lập chỉ mục RAG", "Indexed knowledge chunks")}</p>
          </div>
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary">
            <FolderKanban className="h-6 w-6" />
          </div>
        </Card>
      </section>

      {/* Active Agents Management Grid */}
      <section className="space-y-4">
        <SectionHeader
          title={dict.pages.dashboard.sectionMyAgents}
          description={dict.pages.dashboard.sectionMyAgentsDesc}
          actions={
            <Button asChild variant="outline" size="sm" className="gap-1">
              <Link href="/agents">
                {dict.common.view} <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          }
        />
        {agents.isLoading ? (
          <LoadingSkeleton variant="grid" />
        ) : agentList.length ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {agentList.map((agent) => (
              <Card key={agent.id} glass className="p-5 flex flex-col justify-between hover:border-primary/40 transition-colors">
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                        {agent.kind === "orchestrator" ? <Sparkles className="h-5 w-5" /> : <Bot className="h-5 w-5" />}
                      </div>
                      <div>
                        <p className="font-semibold text-foreground truncate max-w-[160px]">{agent.name}</p>
                        <Badge variant="outline" className="mt-0.5 text-[10px] uppercase font-mono">
                          {agent.kind === "orchestrator" ? tx("Điều phối", "Orchestrator") : tx("Chuyên trách", "Worker")}
                        </Badge>
                      </div>
                    </div>
                  </div>
                  <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                    {agent.description || tx("Chưa có mô tả chi tiết.", "No prompt description configured.")}
                  </p>
                </div>

                <div className="mt-5 flex items-center justify-between pt-3 border-t border-border/50">
                  <span className="text-xs text-muted-foreground font-mono truncate max-w-[120px]">
                    {agent.model_id || "gpt-4o-mini"}
                  </span>
                  <div className="flex items-center gap-2">
                    <Button asChild variant="outline" size="sm" className="h-7 text-xs px-2.5">
                      <Link href={`/chat?agent=${agent.id}`}>
                        {dict.nav.chat}
                      </Link>
                    </Button>
                    <Button asChild variant="default" size="sm" className="h-7 text-xs px-2.5">
                      <Link href={`/agents`}>
                        {tx("Sửa", "Edit")}
                      </Link>
                    </Button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Bot}
            title={dict.pages.dashboard.noAgentsTitle}
            description={dict.pages.dashboard.noAgentsDesc}
            action={
              <Button asChild>
                <Link href="/agents">{dict.pages.dashboard.createFirstAgent}</Link>
              </Button>
            }
          />
        )}
      </section>

      {/* Workflows & Automations Quick Overview */}
      <section className="space-y-4">
        <SectionHeader
          title={tx("Quy trình DAG & Automations", "Workflows & Automations")}
          description={tx("Các quy trình tự động hóa chuỗi tác vụ và xử lý dữ liệu phức tạp.", "Automated DAG task pipelines and orchestration workflows.")}
          actions={
            <Button asChild variant="outline" size="sm" className="gap-1">
              <Link href="/workflows">
                {dict.common.view} <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          }
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {workflowList.slice(0, 6).map((wf) => (
            <Card key={wf.id} glass className="p-4 flex flex-col justify-between hover:border-primary/40 transition-colors">
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Badge variant="outline" className="border-primary/30 bg-primary/5 text-primary text-[11px]">
                    <Workflow className="mr-1 h-3 w-3" />
                    DAG
                  </Badge>
                  <span className="text-[11px] text-muted-foreground font-mono">
                    {wf.graph?.nodes?.length ?? 0} {tx("bước", "nodes")}
                  </span>
                </div>
                <p className="font-semibold text-sm text-foreground truncate">{wf.name}</p>
                <p className="text-xs text-muted-foreground line-clamp-2">
                  {wf.description || tx("Quy trình tự động hóa nhiều bước.", "Multi-step automated execution pipeline.")}
                </p>
              </div>

              <div className="mt-4 flex items-center justify-between pt-2 border-t border-border/40">
                <span className="text-[11px] text-emerald-500 font-medium">
                  {tx("🟢 Sẵn sàng", "🟢 Ready")}
                </span>
                <Button asChild variant="ghost" size="sm" className="h-7 text-xs px-2 gap-1 text-primary">
                  <Link href={`/workflows`}>
                    {tx("Mở Canvas", "Open Canvas")} <ArrowRight className="h-3 w-3" />
                  </Link>
                </Button>
              </div>
            </Card>
          ))}
        </div>
      </section>

      {/* Evaluations & Benchmarking Widget */}
      <section>
        <Card glass className="overflow-hidden">
          <CardHeader className="border-b border-border/70 bg-muted/20 flex flex-row items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-lg">
                <FlaskConical className="h-5 w-5 text-primary" />
                {tx("Đánh giá & Benchmark Mô hình", "Evaluations & Benchmarks")}
              </CardTitle>
              <CardDescription>
                {tx("Kiểm thử độ chính xác, an toàn và hiệu năng của các Agent Prompt", "Evaluate accuracy, safety, and latency benchmarks across model releases")}
              </CardDescription>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href="/evaluations">{dict.pages.dashboard.btnRunEvaluation}</Link>
            </Button>
          </CardHeader>
          <CardContent className="p-6">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="rounded-lg border border-border/80 bg-card p-4 space-y-1">
                <p className="text-xs text-muted-foreground">{tx("Bộ đề đánh giá", "Evaluation Suites")}</p>
                <p className="text-xl font-bold text-foreground">{evalList.length}</p>
                <p className="text-[11px] text-muted-foreground">{tx("Bộ test case đã thiết lập", "Configured test benchmarks")}</p>
              </div>
              <div className="rounded-lg border border-border/80 bg-card p-4 space-y-1">
                <p className="text-xs text-muted-foreground">{tx("Công cụ Sandbox", "Execution Sandbox")}</p>
                <p className="text-xl font-bold text-emerald-500">{tx("Kích hoạt", "Enabled")}</p>
                <p className="text-[11px] text-muted-foreground">{tx("Môi trường Python/Bash an toàn", "Isolated execution runtime")}</p>
              </div>
              <div className="rounded-lg border border-border/80 bg-card p-4 space-y-1">
                <p className="text-xs text-muted-foreground">{tx("Khả năng Quan sát", "Observability Tracing")}</p>
                <p className="text-xl font-bold text-primary">{tx("Langfuse Active", "Langfuse Active")}</p>
                <p className="text-[11px] text-muted-foreground">{tx("Ghi nhận 100% trace và token", "Tracing all LLM transactions")}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
