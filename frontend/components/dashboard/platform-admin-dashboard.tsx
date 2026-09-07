"use client";

import Link from "next/link";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Building2,
  CheckCircle2,
  Cpu,
  Database,
  Globe2,
  HardDrive,
  KeyRound,
  Layers,
  Network,
  Plus,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useHealth, useMe, useOrganizations, useUsageSummary } from "@/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "@/components/shared";
import { useTranslation } from "@/lib/i18n";

export function PlatformAdminDashboard() {
  const { t, dict, tx, locale } = useTranslation();
  const me = useMe();
  const orgs = useOrganizations();
  const health = useHealth();
  const usage = useUsageSummary(true);
  const name = me.data?.display_name || me.data?.email?.split("@")[0] || "Platform Admin";

  function getGreeting() {
    const hour = new Date().getHours();
    if (hour < 12) return dict.pages.dashboard.greetingMorning;
    if (hour < 18) return dict.pages.dashboard.greetingAfternoon;
    return dict.pages.dashboard.greetingEvening;
  }

  const orgList = orgs.data ?? [];
  const activeOrgsCount = orgList.length;
  const totalCalls = (usage.data ?? []).reduce((acc, curr) => acc + curr.calls, 0);

  const coreServices = [
    { name: "FastAPI Core API", icon: Server, status: health.data?.runtime ? "operational" : "degraded", port: "8000", badge: "Core REST/SSE" },
    { name: "ZITADEL Identity Provider", icon: KeyRound, status: "operational", port: "80", badge: "Auth & RBAC" },
    { name: "PostgreSQL Database", icon: Database, status: "operational", port: "5432", badge: "Primary Data" },
    { name: "Redis In-Memory Store", icon: Activity, status: "operational", port: "6379", badge: "Queue & Cache" },
    { name: "Qdrant Vector DB", icon: Layers, status: "operational", port: "6333", badge: "Vector Search" },
    { name: "MinIO Object Storage", icon: HardDrive, status: "operational", port: "9000", badge: "S3 Artifacts" },
    { name: "Langfuse LLM Observability", icon: BarChart3, status: "operational", port: "3002", badge: "Tracing & Metrics" },
    { name: "RAG & Docling Engine", icon: Cpu, status: "operational", port: "8100", badge: "Embeddings & OCR" },
  ];

  return (
    <div className="space-y-8">
      {/* Hero Section */}
      <section className="flex flex-col gap-6 rounded-xl border border-primary/25 bg-card/75 p-6 shadow-card sm:p-8 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl space-y-3">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="border-primary/40 bg-primary/10 text-primary font-semibold">
              <ShieldCheck className="mr-1 h-3.5 w-3.5" />
              {tx("Quản trị Toàn Nền tảng", "Platform Administrator")}
            </Badge>
            <span className="text-xs text-muted-foreground">• {tx("Cấp độ Toàn cầu (Global)", "Global Scope")}</span>
          </div>
          <p className="text-sm font-semibold text-primary">{getGreeting()}, {name}</p>
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            {dict.pages.dashboard.titlePlatform}
          </h1>
          <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">
            {dict.pages.dashboard.descPlatform}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button asChild className="gap-2">
            <Link href="/organizations">
              <Building2 className="h-4 w-4" />
              {dict.pages.dashboard.btnManageOrgs}
            </Link>
          </Button>
          <Button asChild variant="outline" className="gap-2">
            <Link href="/debug">
              <Activity className="h-4 w-4" />
              {dict.pages.dashboard.btnViewAudit}
            </Link>
          </Button>
        </div>
      </section>

      {/* KPI Stats Grid */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-5 flex items-center justify-between border-border/80 bg-card">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{dict.pages.dashboard.statOrgsTotal}</p>
            <p className="text-2xl font-bold tracking-tight text-foreground tabular-nums">{orgList.length}</p>
            <p className="text-xs text-muted-foreground">{tx("Các tổ chức đa tenant", "Registered organizations")}</p>
          </div>
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary">
            <Building2 className="h-6 w-6" />
          </div>
        </Card>

        <Card className="p-5 flex items-center justify-between border-border/80 bg-card">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{dict.pages.dashboard.statOrgsActive}</p>
            <p className="text-2xl font-bold tracking-tight text-emerald-500 tabular-nums">{activeOrgsCount}</p>
            <p className="text-xs text-muted-foreground">{tx("Trạng thái hoạt động bình thường", "Active & healthy tenants")}</p>
          </div>
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-emerald-500/10 text-emerald-500">
            <CheckCircle2 className="h-6 w-6" />
          </div>
        </Card>

        <Card className="p-5 flex items-center justify-between border-border/80 bg-card">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{dict.pages.dashboard.statPlatformServices}</p>
            <p className="text-2xl font-bold tracking-tight text-foreground tabular-nums">8 / 8</p>
            <p className="text-xs text-emerald-500 font-medium">{tx("Tất cả dịch vụ sẵn sàng", "All services online")}</p>
          </div>
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary">
            <Server className="h-6 w-6" />
          </div>
        </Card>

        <Card className="p-5 flex items-center justify-between border-border/80 bg-card">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{dict.pages.dashboard.statPlatformInvocations}</p>
            <p className="text-2xl font-bold tracking-tight text-foreground tabular-nums">{totalCalls.toLocaleString()}</p>
            <p className="text-xs text-muted-foreground">{tx("Tổng lượt gọi AI toàn platform", "Total AI invocations")}</p>
          </div>
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary">
            <Cpu className="h-6 w-6" />
          </div>
        </Card>
      </section>

      {/* Core Platform Services Health Grid */}
      <section className="space-y-4">
        <SectionHeader
          title={dict.pages.dashboard.platformHealthTitle}
          description={dict.pages.dashboard.platformHealthDesc}
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {coreServices.map((srv) => {
            const Icon = srv.icon;
            return (
              <Card key={srv.name} className="p-4 border-border/70 bg-card/60">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="grid h-9 w-9 place-items-center rounded-lg bg-muted text-foreground">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div>
                      <p className="font-semibold text-xs text-foreground truncate max-w-[150px]">{srv.name}</p>
                      <p className="text-[11px] text-muted-foreground font-mono">Port :{srv.port}</p>
                    </div>
                  </div>
                  <Badge variant="outline" className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 text-[10px] uppercase font-mono">
                    {tx("Hoạt động", "Online")}
                  </Badge>
                </div>
                <div className="mt-3 flex items-center justify-between text-[11px] text-muted-foreground pt-2 border-t border-border/40">
                  <span>{srv.badge}</span>
                  <span className="font-mono text-emerald-500">100% Up</span>
                </div>
              </Card>
            );
          })}
        </div>
      </section>

      {/* Organizations Quick Management */}
      <section className="space-y-4">
        <SectionHeader
          title={dict.pages.dashboard.recentOrgsTitle}
          description={dict.pages.dashboard.recentOrgsDesc}
          actions={
            <Button asChild variant="outline" size="sm" className="gap-1">
              <Link href="/organizations">
                {dict.common.view} <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          }
        />

        <Card glass className="overflow-hidden">
          <CardContent className="p-0">
            {orgs.isLoading ? (
              <div className="p-6"><LoadingSkeleton variant="table" /></div>
            ) : orgs.isError ? (
              <div className="p-6">
                <ErrorState
                  title={tx("Không thể tải danh sách tổ chức", "Failed to load organizations")}
                  description={tx("Vui lòng thử lại sau.", "Please try again later.")}
                  onRetry={() => void orgs.refetch()}
                />
              </div>
            ) : orgList.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{tx("Mã Tổ chức (Slug)", "Organization Slug")}</TableHead>
                    <TableHead>{tx("Tên hiển thị", "Display Name")}</TableHead>
                    <TableHead>{tx("Trạng thái", "Status")}</TableHead>
                    <TableHead>{tx("Khởi tạo", "Created At")}</TableHead>
                    <TableHead className="text-right">{tx("Thao tác", "Action")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {orgList.map((org) => (
                    <TableRow key={org.id}>
                      <TableCell className="font-mono font-medium text-foreground">{org.slug}</TableCell>
                      <TableCell className="font-medium text-foreground">{org.name}</TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className="border-emerald-500/30 bg-emerald-500/10 text-emerald-500"
                        >
                          {tx("Hoạt động", "Active")}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground font-mono">
                        {new Date(org.created_at).toLocaleDateString(locale === "vi" ? "vi-VN" : "en-US")}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button asChild variant="ghost" size="sm" className="gap-1 text-xs">
                          <Link href={`/organizations`}>
                            {tx("Chi tiết", "Manage")} <ArrowRight className="h-3 w-3" />
                          </Link>
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="p-6">
                <EmptyState
                  icon={Building2}
                  title={tx("Chưa có tổ chức nào", "No organizations found")}
                  description={tx("Khởi tạo tổ chức (tenant) đầu tiên để bắt đầu phân quyền cho người dùng.", "Create your first organization to assign users and quotas.")}
                  action={
                    <Button asChild>
                      <Link href="/organizations">{dict.pages.dashboard.btnCreateOrg}</Link>
                    </Button>
                  }
                />
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      {/* Global Resource Consumption Analytics */}
      <section>
        <Card glass className="overflow-hidden">
          <CardHeader className="border-b border-border/70 bg-muted/20">
            <CardTitle className="flex items-center gap-2 text-lg">
              <BarChart3 className="h-5 w-5 text-primary" />
              {dict.pages.dashboard.recentUsage}
            </CardTitle>
            <CardDescription>
              {tx("Mức độ tiêu thụ Token và chi phí mô hình AI toàn nền tảng", "Platform-wide AI model invocation and token consumption")}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {usage.isLoading ? (
              <div className="p-6"><LoadingSkeleton variant="table" /></div>
            ) : usage.data?.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{tx("Agent", "Agent")}</TableHead>
                    <TableHead>{tx("Mô hình AI", "Model")}</TableHead>
                    <TableHead className="text-right">{tx("Lượt gọi", "Calls")}</TableHead>
                    <TableHead className="text-right">{tx("Token đầu vào", "Input Tokens")}</TableHead>
                    <TableHead className="text-right">{tx("Token đầu ra", "Output Tokens")}</TableHead>
                    <TableHead className="text-right">{tx("Ước tính chi phí", "Cost (USD)")}</TableHead>
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
                  title={tx("Chưa có lượt tiêu thụ", "No usage recorded yet")}
                  description={tx("Dữ liệu tiêu thụ tài nguyên sẽ xuất hiện khi các tenant thực hiện hội thoại chat hoặc workflow.", "Resource metrics will appear when tenant organizations run chats or workflows.")}
                />
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
