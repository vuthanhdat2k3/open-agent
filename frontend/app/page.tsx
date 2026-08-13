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

function greeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Chào buổi sáng";
  if (hour < 18) return "Chào buổi chiều";
  return "Chào buổi tối";
}

export default function Dashboard() {
  const role = useCurrentRole();
  const isAdmin = role === "admin";
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

  const stats: { label: string; value: number; icon: LucideIcon }[] = [
    ...(isAdmin ? [
      { label: "Providers", value: providers.data?.length ?? 0, icon: Network },
      { label: "Models", value: models.data?.length ?? 0, icon: Cpu },
    ] : []),
    { label: "Workflows", value: workflows.data?.length ?? 0, icon: Workflow },
    ...(isAdmin ? [{ label: "MCP Servers", value: mcp.data?.length ?? 0, icon: Activity }] : []),
  ];

  async function retryResources() {
    await Promise.all(resourceQueries.map((query) => query.refetch()));
  }

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-6 rounded-xl border border-primary/20 bg-card/70 p-6 shadow-card sm:p-8 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl space-y-3">
          <p className="text-sm font-semibold text-primary">{greeting()}{name ? `, ${name}` : ""}</p>
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">Đội ngũ agent của bạn đang sẵn sàng</h1>
          <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">{agents.data?.length ?? 0} agent · {workflows.data?.length ?? 0} workflow đã cấu hình. Bắt đầu trò chuyện hoặc chạy một workflow.</p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button asChild className="gap-2"><Link href="/chat"><MessageSquare className="h-4 w-4" aria-hidden="true" />Bắt đầu Chat</Link></Button>
          <Button asChild variant="outline" className="gap-2"><Link href={isAdmin ? "/workflows" : "/run-workflow"}><Workflow className="h-4 w-4" aria-hidden="true" />Chạy Workflow</Link></Button>
          {grafanaUrl && <Button asChild variant="ghost" className="gap-2"><a href={grafanaUrl} target="_blank" rel="noreferrer"><BarChart3 className="h-4 w-4" aria-hidden="true" />Grafana</a></Button>}
        </div>
      </section>

      {hasResourceError && <ErrorState title="Không thể tải toàn bộ tài nguyên" description="Một số số liệu hoặc agent chưa tải được. Hãy thử lại." onRetry={() => void retryResources()} />}

      {approvals.data?.length ? <section className="space-y-3" aria-label="Approvals that need attention"><SectionHeader title="Needs your attention" description={`${approvals.data.length} approval${approvals.data.length === 1 ? "" : "s"} need review`} actions={<Button asChild variant="ghost" size="sm" className="gap-1"><Link href="/approvals">View all<ArrowRight className="h-3.5 w-3.5" aria-hidden="true" /></Link></Button>} /><div className="grid gap-3 lg:grid-cols-3">{approvals.data.slice(0, 3).map((approval) => <Link key={approval.id} href={`/approvals?approval_id=${encodeURIComponent(approval.id)}`} className="group rounded-xl border border-border/80 bg-card p-4 transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><div className="flex items-center justify-between gap-2"><Badge variant={approval.risk_level === "HIGH" ? "destructive" : "outline"}>{approval.risk_level === "HIGH" ? "HIGH RISK" : "STANDARD"}</Badge><span className="text-xs text-muted-foreground">{expiry(approval.expires_at)}</span></div><p className="mt-3 font-semibold text-foreground">{approvalTitle(approval)}</p><p className="mt-1 truncate text-sm text-muted-foreground">{String(approval.args_snapshot?.summary || approval.args_snapshot?.title || "Review before execution")}</p><span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-primary">Review <ArrowRight className="h-3 w-3" aria-hidden="true" /></span></Link>)}</div></section> : <section className="rounded-xl border border-dashed border-border bg-card/50 p-5"><p className="text-sm font-medium text-foreground">All caught up</p><p className="mt-1 text-sm text-muted-foreground">No approvals need your attention right now.</p></section>}

      <section className="space-y-4">
        <SectionHeader title="Agent của bạn" description="Truy cập nhanh vào những agent đang được cấu hình." actions={isAdmin ? <Button asChild variant="ghost" size="sm" className="gap-1"><Link href="/agents">Quản lý tất cả<ArrowRight className="h-3.5 w-3.5" aria-hidden="true" /></Link></Button> : undefined} />
        {agents.isLoading ? <LoadingSkeleton variant="grid" /> : agents.data?.length ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {agents.data.map((agent) => <Link key={agent.id} href={`/chat?agent=${agent.id}`} className="group block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><Card glass className="h-full p-5 transition-colors group-hover:border-primary/40"><div className="flex items-start gap-3"><div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary"><>{agent.kind === "orchestrator" ? <Sparkles className="h-4 w-4" aria-hidden="true" /> : <Bot className="h-4 w-4" aria-hidden="true" />}</></div><div className="min-w-0"><p className="truncate font-semibold text-foreground">{agent.name}</p><p className="mt-1 line-clamp-2 text-sm leading-relaxed text-muted-foreground">{agent.description || "Chưa có mô tả"}</p></div></div><div className="mt-5 flex items-center justify-between"><span className="rounded-full bg-muted px-2 py-1 text-xs font-medium text-muted-foreground">{agent.kind === "orchestrator" ? "Điều phối" : "Chuyên trách"}</span><span className="flex items-center gap-1 text-xs font-medium text-primary">Trò chuyện<ArrowRight className="h-3 w-3" aria-hidden="true" /></span></div></Card></Link>)}
          </div>
        ) : <EmptyState icon={Bot} title="Chưa có agent nào" description={isAdmin ? "Tạo agent đầu tiên để bắt đầu." : "Chưa có agent trò chuyện nào được cấu hình."} action={isAdmin ? <Button asChild><Link href="/agents">Tạo agent</Link></Button> : undefined} />}
      </section>

      <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map(({ label, value, icon: Icon }) => <Card key={label} className="flex items-center gap-3 p-4"><div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground"><Icon className="h-4 w-4" aria-hidden="true" /></div><div><p className="text-xl font-bold leading-none tabular-nums text-foreground">{value}</p><p className="mt-1 text-xs text-muted-foreground">{label}</p></div></Card>)}
      </section>

      {isAdmin && <section>
        <Card glass className="overflow-hidden">
          <CardHeader className="border-b border-border/70 bg-muted/20"><CardTitle className="flex items-center gap-2 text-lg"><BarChart3 className="h-5 w-5 text-primary" aria-hidden="true" />Usage Summary</CardTitle><p className="text-sm text-muted-foreground">Agent activity and token usage analytics</p></CardHeader>
          <CardContent className="p-0">
            {usage.isLoading ? <div className="space-y-2 p-6"><LoadingSkeleton variant="table" /></div> : usage.isError ? <div className="p-6"><ErrorState title="Không thể tải usage" description="Usage summary chưa sẵn sàng. Hãy thử lại." onRetry={() => void usage.refetch()} /></div> : usage.data?.length ? <Table><TableHeader><TableRow><TableHead>Agent</TableHead><TableHead>Model</TableHead><TableHead className="text-right">Calls</TableHead><TableHead className="text-right">In Tokens</TableHead><TableHead className="text-right">Out Tokens</TableHead><TableHead className="text-right">Cost</TableHead></TableRow></TableHeader><TableBody>{usage.data.map((item, index) => <TableRow key={`${item.agent_name}-${item.model_name}-${index}`}><TableCell className="font-medium">{item.agent_name}</TableCell><TableCell className="text-muted-foreground">{item.model_name}</TableCell><TableCell className="text-right font-mono tabular-nums text-muted-foreground">{item.calls}</TableCell><TableCell className="text-right font-mono tabular-nums text-muted-foreground">{item.input_tokens.toLocaleString()}</TableCell><TableCell className="text-right font-mono tabular-nums text-muted-foreground">{item.output_tokens.toLocaleString()}</TableCell><TableCell className="text-right font-mono font-semibold tabular-nums text-primary">${item.cost_usd.toFixed(6)}</TableCell></TableRow>)}</TableBody></Table> : <div className="p-6"><EmptyState icon={BarChart3} title="No usage recorded yet" description="Start by creating an agent or running a chat." /></div>}
          </CardContent>
        </Card>
      </section>}
    </div>
  );
}
