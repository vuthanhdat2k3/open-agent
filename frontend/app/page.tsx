"use client";

import Link from "next/link";
import {
  Activity,
  BarChart3,
  Bot,
  Cpu,
  MessageSquare,
  Network,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { useUsageSummary, useProviders, useModels, useAgents, useWorkflows, useMcpServers } from "@/hooks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function Dashboard() {
  const usage = useUsageSummary();
  const providers = useProviders();
  const models = useModels();
  const agents = useAgents();
  const workflows = useWorkflows();
  const mcp = useMcpServers();
  const grafanaUrl = process.env.NEXT_PUBLIC_GRAFANA_URL;

  const stats: { label: string; value: number; icon: LucideIcon }[] = [
    { label: "Providers", value: providers.data?.length ?? 0, icon: Network },
    { label: "Models", value: models.data?.length ?? 0, icon: Cpu },
    { label: "Agents", value: agents.data?.length ?? 0, icon: Bot },
    { label: "Workflows", value: workflows.data?.length ?? 0, icon: Workflow },
    { label: "MCP Servers", value: mcp.data?.length ?? 0, icon: Activity },
  ];

  return (
    <div className="space-y-8">
      <PageHeader
        icon={Activity}
        title="Dashboard"
        description="Overview of your OpenAgent system"
        actions={
          <>
            <Button asChild variant="outline" size="lg" className="gap-2">
              <Link href="/agents">
                <Bot className="h-4 w-4" />
                Manage Agents
              </Link>
            </Button>
            {grafanaUrl && (
              <Button asChild variant="outline" size="lg" className="gap-2">
                <a href={grafanaUrl} target="_blank" rel="noreferrer">
                  <BarChart3 className="h-4 w-4" />
                  Open Grafana
                </a>
              </Button>
            )}
            <Button asChild size="lg" className="gap-2">
              <Link href="/chat">
                <MessageSquare className="h-4 w-4" />
                Start Chat
              </Link>
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5 stagger">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <Card key={s.label} glass className="card-lift overflow-hidden p-5">
              <div className="flex items-start justify-between">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {s.label}
                </p>
                <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-primary/25 via-primary/10 to-transparent text-primary shadow-3d-card border border-primary/20">
                  <Icon className="h-4 w-4" />
                </div>
              </div>
              <div className="mt-4 text-3xl font-bold tracking-tight tabular-nums text-foreground">{s.value}</div>
            </Card>
          );
        })}
      </div>

      <div className="animate-slide-up" style={{ animationDelay: "150ms" }}>
        <Card glass className="overflow-hidden">
          <CardHeader className="flex flex-row items-center gap-3 border-b border-border/80 bg-muted/20">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-primary/25 via-primary/10 to-transparent text-primary shadow-3d-card border border-primary/20">
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
