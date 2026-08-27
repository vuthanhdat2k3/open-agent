"use client";

import Link from "next/link";
import { Activity, ArrowRight, BarChart3, Bot, Cpu, MessageSquare, Network, Sparkles, Workflow, type LucideIcon } from "lucide-react";
import { useAgents, useApprovals, useCurrentRole, useMcpServers, useMe, useModels, useProviders, useUsageSummary, useWorkflows } from "@/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "@/components/shared";
import { approvalTitle, expiry } from "@/components/layout/approval-bell";
import { Badge } from "@/components/ui/badge";

import { useTranslation } from "@/lib/i18n";

export default function Dashboard() {
  const { t, dict, locale } = useTranslation();
  const role = useCurrentRole();
  const isAdmin = role === "admin" || role === "platform_admin" || role === "operator";
  const me = useMe();
  const usage = useUsageSummary(isAdmin);
  const providers = useProviders(isAdmin);
  const models = useModels(isAdmin);
  const agents = useAgents();
  const workflows = useWorkflows();
  const approvals = useApprovals(true);
  const mcp = useMcpServers(isAdmin);
  const grafanaUrl = process.env.NEXT_PUBLIC_GRAFANA_URL;
  const name = me.data?.display_name || me.data?.email?.split("@")[0] || "";
  const resourceQueries = isAdmin ? [providers, models, agents, workflows, mcp] : [agents, workflows];
  const hasResourceError = resourceQueries.some((query) => query.isError);

  function getGreeting() {
    const hour = new Date().getHours();
    if (hour < 12) return dict.pages.dashboard.greetingMorning;
    if (hour < 18) return dict.pages.dashboard.greetingAfternoon;
    return dict.pages.dashboard.greetingEvening;
  }

  const stats: { label: string; value: number; icon: LucideIcon }[] = [
    ...(isAdmin ? [
      { label: dict.nav.providers, value: providers.data?.length ?? 0, icon: Network },
      { label: dict.nav.models, value: models.data?.length ?? 0, icon: Cpu },
    ] : []),
    { label: dict.nav.workflows, value: workflows.data?.length ?? 0, icon: Workflow },
    ...(isAdmin ? [{ label: dict.nav.mcpServers, value: mcp.data?.length ?? 0, icon: Activity }] : []),
  ];

  async function retryResources() {
    await Promise.all(resourceQueries.map((query) => query.refetch()));
  }

  const isPlatformAdmin = role === "platform_admin";
  const isOrgAdmin = role === "admin";
  const isOperator = role === "operator";
  const isEndUser = role === "user";

  const heroHeading = isPlatformAdmin
    ? (locale === "vi" ? "Quản trị Nền tảng & Phân bổ Tenant" : "Platform Administration & Tenant Management")
    : isOrgAdmin
      ? dict.pages.dashboard.titleAdmin
      : isOperator
        ? (locale === "vi" ? "Trung tâm Thiết kế & Giám sát Agentic DAG" : "AI Studio, Workflow & Evaluator")
        : dict.pages.dashboard.titleUser;

  const heroSubtitle = isPlatformAdmin
    ? (locale === "vi" ? "Quản lý danh sách các Tổ chức (Tenants), bổ nhiệm Org Admin và kiểm soát trạng thái hoạt động toàn platform." : "Manage multi-tenant organizations, assign Org Admins, and govern global platform health.")
    : isOrgAdmin
      ? dict.pages.dashboard.descAdmin
      : isOperator
        ? (locale === "vi" ? `${agents.data?.length ?? 0} agent · ${workflows.data?.length ?? 0} workflow đã cấu hình. Thiết kế prompt, xây dựng workflow hoặc chạy evaluation benchmark.` : `${agents.data?.length ?? 0} agents · ${workflows.data?.length ?? 0} workflows configured. Design prompts, build workflows, or run benchmarks.`)
        : dict.pages.dashboard.descUser;

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-6 rounded-xl border border-primary/20 bg-card/70 p-6 shadow-card sm:p-8 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl space-y-3">
          <p className="text-sm font-semibold text-primary">{getGreeting()}{name ? `, ${name}` : ""}</p>
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">{heroHeading}</h1>
          <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">{heroSubtitle}</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {isPlatformAdmin && (
            <>
              <Button asChild className="gap-2"><Link href="/organizations">{dict.pages.dashboard.btnManageOrgs}</Link></Button>
            </>
          )}
          {isOrgAdmin && !isPlatformAdmin && (
            <>
              <Button asChild className="gap-2"><Link href="/settings/members">{dict.pages.dashboard.btnManageMembers}</Link></Button>
              <Button asChild variant="outline" className="gap-2"><Link href="/providers">{dict.nav.providers}</Link></Button>
              <Button asChild variant="ghost" className="gap-2"><Link href="/settings/quotas">{dict.nav.quotas}</Link></Button>
            </>
          )}
          {isOperator && (
            <>
              <Button asChild className="gap-2"><Link href="/agents"><Bot className="h-4 w-4" aria-hidden="true" />{dict.nav.agents}</Link></Button>
              <Button asChild variant="outline" className="gap-2"><Link href="/workflows"><Workflow className="h-4 w-4" aria-hidden="true" />{dict.nav.workflows}</Link></Button>
            </>
          )}
          {isEndUser && (
            <>
              <Button asChild className="gap-2"><Link href="/chat"><MessageSquare className="h-4 w-4" aria-hidden="true" />{dict.pages.dashboard.btnStartChat}</Link></Button>
              <Button asChild variant="outline" className="gap-2"><Link href="/workflows"><Workflow className="h-4 w-4" aria-hidden="true" />{dict.pages.dashboard.btnRunWorkflow}</Link></Button>
            </>
          )}
          {grafanaUrl && <Button asChild variant="ghost" className="gap-2"><a href={grafanaUrl} target="_blank" rel="noreferrer"><BarChart3 className="h-4 w-4" aria-hidden="true" />{locale === "vi" ? "Grafana" : "Grafana"}</a></Button>}
        </div>
      </section>

      {hasResourceError && (
        <ErrorState
          title={locale === "vi" ? "Không thể tải toàn bộ tài nguyên" : "Failed to load all resources"}
          description={locale === "vi" ? "Một số số liệu hoặc agent chưa tải được. Hãy thử lại." : "Some metrics or agents could not be loaded. Please retry."}
          onRetry={() => void retryResources()}
        />
      )}

      {approvals.data?.length ? (
        <section className="space-y-3" aria-label="Approvals that need attention">
          <SectionHeader
            title={dict.pages.approvals.pendingDecisions}
            description={`${approvals.data.length} approval${approvals.data.length === 1 ? "" : "s"} need review`}
            actions={
              <Button asChild variant="ghost" size="sm" className="gap-1">
                <Link href="/approvals">
                  {dict.common.view} <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Link>
              </Button>
            }
          />
          <div className="grid gap-3 lg:grid-cols-3">
            {approvals.data.slice(0, 3).map((approval) => (
              <Link
                key={approval.id}
                href={`/approvals?approval_id=${encodeURIComponent(approval.id)}`}
                className="group rounded-xl border border-border/80 bg-card p-4 transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <div className="flex items-center justify-between gap-2">
                  <Badge variant={approval.risk_level === "HIGH" ? "destructive" : "outline"}>
                    {approval.risk_level === "HIGH" ? "HIGH RISK" : "STANDARD"}
                  </Badge>
                  <span className="text-xs text-muted-foreground">{expiry(approval.expires_at, locale)}</span>
                </div>
                <p className="mt-3 font-semibold text-foreground">{approvalTitle(approval, locale)}</p>
                <p className="mt-1 truncate text-sm text-muted-foreground">
                  {String(approval.args_snapshot?.summary || approval.args_snapshot?.title || "Review before execution")}
                </p>
                <span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-primary">
                  {dict.pages.approvals.btnApprove} <ArrowRight className="h-3 w-3" aria-hidden="true" />
                </span>
              </Link>
            ))}
          </div>
        </section>
      ) : (
        <section className="rounded-xl border border-dashed border-border bg-card/50 p-5">
          <p className="text-sm font-medium text-foreground">{dict.common.allCaughtUp}</p>
          <p className="mt-1 text-sm text-muted-foreground">{dict.pages.approvals.allCaughtUpDesc}</p>
        </section>
      )}

      <section className="space-y-4">
        <SectionHeader
          title={dict.pages.dashboard.sectionMyAgents}
          description={dict.pages.dashboard.sectionMyAgentsDesc}
          actions={
            isAdmin ? (
              <Button asChild variant="ghost" size="sm" className="gap-1">
                <Link href="/agents">
                  {dict.common.all} <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Link>
              </Button>
            ) : undefined
          }
        />
        {agents.isLoading ? (
          <LoadingSkeleton variant="grid" />
        ) : agents.data?.length ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {agents.data.map((agent) => (
              <Link
                key={agent.id}
                href={`/chat?agent=${agent.id}`}
                className="group block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Card glass className="h-full p-5 transition-colors group-hover:border-primary/40">
                  <div className="flex items-start gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                      <>{agent.kind === "orchestrator" ? <Sparkles className="h-4 w-4" aria-hidden="true" /> : <Bot className="h-4 w-4" aria-hidden="true" />}</>
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-foreground">{agent.name}</p>
                      <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
                        {agent.description || (locale === "vi" ? "Chưa có mô tả" : "No description")}
                      </p>
                    </div>
                  </div>
                  <div className="mt-5 flex items-center justify-between">
                    <span className="rounded-full bg-muted px-2 py-1 text-xs font-medium text-muted-foreground">
                      {agent.kind === "orchestrator"
                        ? (locale === "vi" ? "Điều phối" : "Orchestrator")
                        : (locale === "vi" ? "Chuyên trách" : "Worker")}
                    </span>
                    <span className="flex items-center gap-1 text-xs font-medium text-primary">
                      {dict.nav.chat} <ArrowRight className="h-3 w-3" aria-hidden="true" />
                    </span>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Bot}
            title={dict.pages.dashboard.noAgentsTitle}
            description={isAdmin ? dict.pages.dashboard.noAgentsDesc : (locale === "vi" ? "Chưa có agent nào được phân quyền." : "No agents currently configured.")}
            action={isAdmin ? <Button asChild><Link href="/agents">{dict.pages.dashboard.createFirstAgent}</Link></Button> : undefined}
          />
        )}
      </section>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map(({ label, value, icon: Icon }) => (
          <Card key={label} className="flex items-center gap-3 p-4">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground">
              <Icon className="h-4 w-4" aria-hidden="true" />
            </div>
            <div>
              <p className="text-xl font-bold leading-none tabular-nums text-foreground">{value}</p>
              <p className="mt-1 text-xs text-muted-foreground">{label}</p>
            </div>
          </Card>
        ))}
      </section>

      {isAdmin && (
        <section>
          <Card glass className="overflow-hidden">
            <CardHeader className="border-b border-border/70 bg-muted/20">
              <CardTitle className="flex items-center gap-2 text-lg">
                <BarChart3 className="h-5 w-5 text-primary" aria-hidden="true" />
                {dict.pages.dashboard.recentUsage}
              </CardTitle>
              <p className="text-sm text-muted-foreground">
                {locale === "vi" ? "Hoạt động của agent và phân tích mức tiêu thụ token" : "Agent activity and token usage analytics"}
              </p>
            </CardHeader>
            <CardContent className="p-0">
              {usage.isLoading ? (
                <div className="space-y-2 p-6"><LoadingSkeleton variant="table" /></div>
              ) : usage.isError ? (
                <div className="p-6">
                  <ErrorState
                    title={locale === "vi" ? "Không thể tải usage" : "Failed to load usage"}
                    description={locale === "vi" ? "Số liệu thống kê chưa sẵn sàng. Hãy thử lại." : "Usage summary is not available. Please retry."}
                    onRetry={() => void usage.refetch()}
                  />
                </div>
              ) : usage.data?.length ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{locale === "vi" ? "Agent" : "Agent"}</TableHead>
                      <TableHead>{locale === "vi" ? "Model" : "Model"}</TableHead>
                      <TableHead className="text-right">{locale === "vi" ? "Calls" : "Calls"}</TableHead>
                      <TableHead className="text-right">{locale === "vi" ? "In Tokens" : "In Tokens"}</TableHead>
                      <TableHead className="text-right">{locale === "vi" ? "Out Tokens" : "Out Tokens"}</TableHead>
                      <TableHead className="text-right">{locale === "vi" ? "Cost" : "Cost"}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {usage.data.map((item, index) => (
                      <TableRow key={`${item.agent_name}-${item.model_name}-${index}`}>
                        <TableCell className="font-medium">{item.agent_name}</TableCell>
                        <TableCell className="text-muted-foreground">{item.model_name}</TableCell>
                        <TableCell className="text-right font-mono tabular-nums text-muted-foreground">{item.calls}</TableCell>
                        <TableCell className="text-right font-mono tabular-nums text-muted-foreground">{item.input_tokens.toLocaleString()}</TableCell>
                        <TableCell className="text-right font-mono tabular-nums text-muted-foreground">{item.output_tokens.toLocaleString()}</TableCell>
                        <TableCell className="text-right font-mono font-semibold tabular-nums text-primary">${item.cost_usd.toFixed(6)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <div className="p-6">
                  <EmptyState
                    icon={BarChart3}
                    title={locale === "vi" ? "Chưa có dữ liệu tiêu thụ" : "No usage recorded yet"}
                    description={locale === "vi" ? "Bắt đầu bằng cách tạo agent hoặc thực hiện hội thoại chat." : "Start by creating an agent or running a chat."}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        </section>
      )}
    </div>
  );
}
