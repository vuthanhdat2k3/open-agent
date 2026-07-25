"use client";

import Link from "next/link";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Bot,
  Cpu,
  MessageSquare,
  Network,
  Sparkles,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { useUsageSummary, useProviders, useModels, useAgents, useWorkflows, useMcpServers, useMe } from "@/hooks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Chào buổi sáng";
  if (h < 18) return "Chào buổi chiều";
  return "Chào buổi tối";
}

export default function Dashboard() {
  const me = useMe();
  const usage = useUsageSummary();
  const providers = useProviders();
  const models = useModels();
  const agents = useAgents();
  const workflows = useWorkflows();
  const mcp = useMcpServers();
  const grafanaUrl = process.env.NEXT_PUBLIC_GRAFANA_URL;

  const name = me.data?.display_name || me.data?.email?.split("@")[0] || "";

  const stats: { label: string; value: number; icon: LucideIcon }[] = [
    { label: "Providers", value: providers.data?.length ?? 0, icon: Network },
    { label: "Models", value: models.data?.length ?? 0, icon: Cpu },
    { label: "Workflows", value: workflows.data?.length ?? 0, icon: Workflow },
    { label: "MCP Servers", value: mcp.data?.length ?? 0, icon: Activity },
  ];

  return (
    <div className="space-y-10">
      {/* Hero */}
      <div className="relative overflow-hidden rounded-2xl border border-border/60 bg-gradient-to-br from-primary/10 via-card to-card p-8 shadow-3d-elevated sm:p-10">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-primary/20 blur-3xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-32 -left-16 h-64 w-64 rounded-full bg-info/10 blur-3xl"
        />
        <div className="relative animate-slide-up">
          <p className="text-sm font-semibold text-primary">
            {greeting()}
            {name ? `, ${name}` : ""}
          </p>
          <h1 className="mt-2 text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            Đội ngũ agent của bạn đang sẵn sàng
          </h1>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            {agents.data?.length ?? 0} agent · {workflows.data?.length ?? 0} workflow đã cấu hình.
            Bắt đầu trò chuyện hoặc chạy một workflow.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Button asChild size="lg" className="gap-2 shadow-3d-card">
              <Link href="/chat">
                <MessageSquare className="h-4 w-4" />
                Bắt đầu Chat
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg" className="gap-2">
              <Link href="/workflows">
                <Workflow className="h-4 w-4" />
                Chạy Workflow
              </Link>
            </Button>
            {grafanaUrl && (
              <Button asChild variant="ghost" size="lg" className="gap-2">
                <a href={grafanaUrl} target="_blank" rel="noreferrer">
                  <BarChart3 className="h-4 w-4" />
                  Grafana
                </a>
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Agent quick-launch grid */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">Agent của bạn</h2>
          <Button asChild variant="ghost" size="sm" className="gap-1 text-muted-foreground">
            <Link href="/agents">
              Quản lý tất cả <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        </div>
        {agents.isLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-32 rounded-xl" />
            ))}
          </div>
        ) : agents.data && agents.data.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 stagger">
            {agents.data.map((a) => (
              <Link key={a.id} href={`/chat?agent=${a.id}`} className="group block">
                <Card
                  glass
                  className="h-full overflow-hidden p-5 transition-all duration-300 ease-spring hover:-translate-y-1 hover:shadow-3d-elevated"
                >
                  <div className="flex items-start gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-primary/20 bg-gradient-to-br from-primary/25 via-primary/10 to-transparent text-primary shadow-3d-card">
                      {a.kind === "orchestrator" ? (
                        <Sparkles className="h-4 w-4" />
                      ) : (
                        <Bot className="h-4 w-4" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-foreground">{a.name}</p>
                      <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                        {a.description || "Chưa có mô tả"}
                      </p>
                    </div>
                  </div>
                  <div className="mt-4 flex items-center justify-between">
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      {a.kind === "orchestrator" ? "Điều phối" : "Chuyên trách"}
                    </span>
                    <span className="flex items-center gap-1 text-xs font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
                      Trò chuyện <ArrowRight className="h-3 w-3" />
                    </span>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Bot}
            title="Chưa có agent nào"
            description="Tạo agent đầu tiên để bắt đầu."
            action={
              <Button asChild>
                <Link href="/agents">Tạo agent</Link>
              </Button>
            }
          />
        )}
      </div>

      {/* Compact system stats strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <Card key={s.label} className="flex items-center gap-3 p-4">
              <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground">
                <Icon className="h-4 w-4" />
              </div>
              <div>
                <p className="text-lg font-bold leading-none tabular-nums text-foreground">{s.value}</p>
                <p className="mt-1 text-[11px] text-muted-foreground">{s.label}</p>
              </div>
            </Card>
          );
        })}
      </div>

      {/* Usage summary, secondary */}
      <div className="animate-slide-up" style={{ animationDelay: "150ms" }}>
        <Card glass className="overflow-hidden">
          <CardHeader className="flex flex-row items-center gap-3 border-b border-border/80 bg-muted/20">
            <div className="grid h-9 w-9 place-items-center rounded-xl border border-primary/20 bg-gradient-to-br from-primary/25 via-primary/10 to-transparent text-primary shadow-3d-card">
              <BarChart3 className="h-4 w-4" />
            </div>
            <div>
              <CardTitle className="text-lg">Usage Summary</CardTitle>
              <p className="mt-0.5 text-xs text-muted-foreground">Agent activity and token usage analytics</p>
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            {usage.isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-11 w-full" />
                ))}
              </div>
            ) : usage.data && usage.data.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Agent</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead className="text-right">Calls</TableHead>
                    <TableHead className="text-right">In Tokens</TableHead>
                    <TableHead className="text-right">Out Tokens</TableHead>
                    <TableHead className="text-right">Cost</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {usage.data.map((u, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-medium">{u.agent_name}</TableCell>
                      <TableCell className="text-muted-foreground">{u.model_name}</TableCell>
                      <TableCell className="text-right tabular-nums font-mono text-muted-foreground">{u.calls}</TableCell>
                      <TableCell className="text-right tabular-nums font-mono text-muted-foreground">
                        {u.input_tokens.toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right tabular-nums font-mono text-muted-foreground">
                        {u.output_tokens.toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right tabular-nums font-mono font-semibold text-primary">
                        ${u.cost_usd.toFixed(6)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <EmptyState
                icon={BarChart3}
                title="No usage recorded yet"
                description="Start by creating an agent or running a chat."
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
