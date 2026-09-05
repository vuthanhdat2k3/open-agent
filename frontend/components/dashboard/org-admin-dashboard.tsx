"use client";

import Link from "next/link";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Bot,
  Building2,
  Cpu,
  Gauge,
  Mail,
  ShieldAlert,
  ShieldCheck,
  SlidersHorizontal,
  Users,
  Workflow,
} from "lucide-react";
import {
  useAgents,
  useApprovals,
  useMe,
  useMembers,
  useOrganizationQuota,
  useUsageSummary,
  useWorkflows,
} from "@/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingSkeleton, SectionHeader } from "@/components/shared";
import { approvalTitle, expiry } from "@/components/layout/approval-bell";
import { useTranslation, roleLabel } from "@/lib/i18n";
import { getActiveOrgId } from "@/lib/auth";

export function OrgAdminDashboard() {
  const { t, dict, tx, locale } = useTranslation();
  const me = useMe();
  const orgId = getActiveOrgId();
  const members = useMembers(orgId ?? undefined);
  const quota = useOrganizationQuota(orgId ?? undefined);
  const agents = useAgents();
  const workflows = useWorkflows();
  const approvals = useApprovals(true);
  const usage = useUsageSummary(true);

  const name = me.data?.display_name || me.data?.email?.split("@")[0] || "Admin";
  const activeOrg = me.data?.memberships?.find((m) => m.org_id === orgId) || me.data?.memberships?.[0];
  const orgName = activeOrg?.org_name || activeOrg?.org_slug || tx("Tổ chức hiện tại", "Current Organization");

  function getGreeting() {
    const hour = new Date().getHours();
    if (hour < 12) return dict.pages.dashboard.greetingMorning;
    if (hour < 18) return dict.pages.dashboard.greetingAfternoon;
    return dict.pages.dashboard.greetingEvening;
  }

  const memberList = members.data ?? [];
  const pendingApprovals = approvals.data ?? [];
  const monthlyCost = quota.data?.monthly_cost_usd ?? 0;

  return (
    <div className="space-y-8">
      {/* Hero Banner */}
      <section className="flex flex-col gap-6 rounded-xl border border-primary/25 bg-card/75 p-6 shadow-card sm:p-8 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl space-y-3">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="border-primary/40 bg-primary/10 text-primary font-semibold">
              <Building2 className="mr-1 h-3.5 w-3.5" />
              {orgName}
            </Badge>
            <span className="text-xs text-muted-foreground">• {tx("Quản trị Tổ chức (Org Admin)", "Organization Admin")}</span>
          </div>
          <p className="text-sm font-semibold text-primary">{getGreeting()}, {name}</p>
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            {dict.pages.dashboard.titleAdmin}
          </h1>
          <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">
            {dict.pages.dashboard.descAdmin}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button asChild className="gap-2">
            <Link href="/settings/members">
              <Users className="h-4 w-4" />
              {dict.pages.dashboard.btnManageMembers}
            </Link>
          </Button>
          <Button asChild variant="outline" className="gap-2">
            <Link href="/settings/quotas">
              <Gauge className="h-4 w-4" />
              {dict.pages.dashboard.btnQuotas}
            </Link>
          </Button>
          <Button asChild variant="ghost" className="gap-2">
            <Link href="/admin/email-intelligence">
              <Mail className="h-4 w-4" />
              {dict.pages.dashboard.btnEmailGateway}
            </Link>
          </Button>
        </div>
      </section>

      {/* KPI Stats Grid */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-5 flex items-center justify-between border-border/80 bg-card">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{dict.pages.dashboard.statMembersTotal}</p>
            <p className="text-2xl font-bold tracking-tight text-foreground tabular-nums">{memberList.length}</p>
            <p className="text-xs text-muted-foreground">{tx("Thành viên đã cấp quyền", "Assigned team members")}</p>
          </div>
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary">
            <Users className="h-6 w-6" />
          </div>
        </Card>

        <Card className="p-5 flex items-center justify-between border-border/80 bg-card">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{dict.pages.dashboard.statQuotaUsage}</p>
            <p className="text-2xl font-bold tracking-tight text-foreground tabular-nums">
              ${monthlyCost.toFixed(2)}
            </p>
            <p className="text-xs text-muted-foreground">
              {tx("Chi phí tích lũy tháng hiện tại", "Current monthly spend")}
            </p>
          </div>
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary">
            <Gauge className="h-6 w-6" />
          </div>
        </Card>

        <Card className="p-5 flex items-center justify-between border-border/80 bg-card">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{tx("Quy trình & Agent", "Agents & Workflows")}</p>
            <p className="text-2xl font-bold tracking-tight text-foreground tabular-nums">
              {(agents.data?.length ?? 0) + (workflows.data?.length ?? 0)}
            </p>
            <p className="text-xs text-muted-foreground">
              {agents.data?.length ?? 0} {tx("agent", "agents")} · {workflows.data?.length ?? 0} {tx("workflow", "workflows")}
            </p>
          </div>
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary">
            <Workflow className="h-6 w-6" />
          </div>
        </Card>

        <Card className="p-5 flex items-center justify-between border-border/80 bg-card">
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground">{tx("Phê duyệt đang chờ", "Pending Approvals")}</p>
            <p className={`text-2xl font-bold tracking-tight tabular-nums ${pendingApprovals.length > 0 ? "text-amber-500" : "text-foreground"}`}>
              {pendingApprovals.length}
            </p>
            <p className="text-xs text-muted-foreground">{tx("Cần xem xét và duyệt", "Items requiring review")}</p>
          </div>
          <div className={`grid h-12 w-12 place-items-center rounded-xl ${pendingApprovals.length > 0 ? "bg-amber-500/10 text-amber-500" : "bg-primary/10 text-primary"}`}>
            <ShieldAlert className="h-6 w-6" />
          </div>
        </Card>
      </section>

      {/* Governance Approvals Alert / List */}
      {pendingApprovals.length > 0 && (
        <section className="space-y-3">
          <SectionHeader
            title={dict.pages.approvals.pendingDecisions}
            description={tx(`${pendingApprovals.length} yêu cầu cần quản trị viên duyệt trước khi thực thi`, `${pendingApprovals.length} requests requiring org admin approval`)}
            actions={
              <Button asChild variant="ghost" size="sm" className="gap-1">
                <Link href="/approvals">
                  {dict.common.view} <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            }
          />
          <div className="grid gap-3 lg:grid-cols-3">
            {pendingApprovals.slice(0, 3).map((approval) => (
              <Link
                key={approval.id}
                href={`/approvals?approval_id=${encodeURIComponent(approval.id)}`}
                className="group rounded-xl border border-border/80 bg-card p-4 transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <div className="flex items-center justify-between gap-2">
                  <Badge variant={approval.risk_level === "HIGH" ? "destructive" : "outline"}>
                    {approval.risk_level === "HIGH" ? "HIGH RISK" : "STANDARD"}
                  </Badge>
                  <span className="text-xs text-muted-foreground">{expiry(approval.expires_at, locale, tx)}</span>
                </div>
                <p className="mt-3 font-semibold text-foreground">{approvalTitle(approval, locale, tx)}</p>
                <p className="mt-1 truncate text-sm text-muted-foreground">
                  {String(approval.args_snapshot?.summary || approval.args_snapshot?.title || tx("Xem xét hành động bên ngoài", "Review external tool execution"))}
                </p>
                <span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-primary">
                  {dict.pages.approvals.btnApprove} <ArrowRight className="h-3 w-3" />
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Recent Org Member Roster Overview */}
      <section className="space-y-4">
        <SectionHeader
          title={tx("Thành viên trong Tổ chức", "Organization Members")}
          description={tx("Danh sách thành viên và vai trò được phân quyền trong tenant hiện tại.", "Team members and assigned roles within this organization.")}
          actions={
            <Button asChild variant="outline" size="sm" className="gap-1">
              <Link href="/settings/members">
                {dict.common.view} <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
          }
        />

        <Card glass className="overflow-hidden">
          <CardContent className="p-0">
            {members.isLoading ? (
              <div className="p-6"><LoadingSkeleton variant="table" /></div>
            ) : memberList.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{tx("Thành viên", "Member")}</TableHead>
                    <TableHead>{tx("Email", "Email")}</TableHead>
                    <TableHead>{tx("Vai trò", "Role")}</TableHead>
                    <TableHead className="text-right">{tx("Thao tác", "Action")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {memberList.slice(0, 5).map((member) => (
                    <TableRow key={member.user_id}>
                      <TableCell className="font-medium text-foreground">
                        {member.display_name || member.email.split("@")[0]}
                      </TableCell>
                      <TableCell className="text-muted-foreground font-mono text-xs">{member.email}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="border-primary/30 bg-primary/5 text-primary text-xs capitalize">
                          {roleLabel(member.role, t)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button asChild variant="ghost" size="sm" className="text-xs">
                          <Link href="/settings/members">
                            {tx("Phân quyền", "Manage")}
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
                  icon={Users}
                  title={tx("Chưa có thành viên", "No members")}
                  description={tx("Mời thành viên vào tổ chức để cộng tác cùng các AI Agent.", "Invite members to collaborate in this organization.")}
                  action={
                    <Button asChild>
                      <Link href="/settings/members">{dict.pages.dashboard.btnManageMembers}</Link>
                    </Button>
                  }
                />
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      {/* Organization Resource Analytics */}
      <section>
        <Card glass className="overflow-hidden">
          <CardHeader className="border-b border-border/70 bg-muted/20">
            <CardTitle className="flex items-center gap-2 text-lg">
              <BarChart3 className="h-5 w-5 text-primary" />
              {dict.pages.dashboard.recentUsage}
            </CardTitle>
            <CardDescription>
              {tx("Mức tiêu thụ Token và chi phí mô hình AI trong tổ chức", "Token consumption and model spend in this organization")}
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
                    <TableHead className="text-right">{tx("Chi phí", "Cost")}</TableHead>
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
                  description={tx("Dữ liệu tiêu thụ tài nguyên sẽ xuất hiện khi các thành viên bắt đầu trò chuyện hoặc chạy workflow.", "Usage analytics will appear as team members run sessions or workflows.")}
                />
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
