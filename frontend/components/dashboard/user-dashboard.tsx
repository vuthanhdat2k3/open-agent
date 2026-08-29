"use client";

import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Building2,
  CalendarDays,
  CheckCircle2,
  Clock,
  Inbox,
  Mail,
  MessageSquare,
  Search,
  ShieldAlert,
  Sparkles,
  Workflow,
  Zap,
} from "lucide-react";
import {
  useAgents,
  useApprovals,
  useEmailIntelligenceNavigationSummary,
  useMe,
  useWorkflows,
} from "@/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, LoadingSkeleton, SectionHeader } from "@/components/shared";
import { approvalTitle, expiry } from "@/components/layout/approval-bell";
import { useTranslation } from "@/lib/i18n";

export function UserDashboard() {
  const { t, dict, tx, locale } = useTranslation();
  const me = useMe();
  const agents = useAgents();
  const workflows = useWorkflows();
  const approvals = useApprovals(true);
  const emailSummary = useEmailIntelligenceNavigationSummary();

  const name = me.data?.display_name || me.data?.email?.split("@")[0] || "";
  const pendingApprovals = approvals.data ?? [];
  const agentList = agents.data ?? [];
  const workflowList = workflows.data ?? [];

  function getGreeting() {
    const hour = new Date().getHours();
    if (hour < 12) return dict.pages.dashboard.greetingMorning;
    if (hour < 18) return dict.pages.dashboard.greetingAfternoon;
    return dict.pages.dashboard.greetingEvening;
  }

  const unreadEmails = emailSummary.data?.user_workspace.inbox.unread ?? 0;
  const pendingActions = emailSummary.data?.user_workspace.approvals.pending ?? pendingApprovals.length;

  return (
    <div className="space-y-8">
      {/* Hero Banner */}
      <section className="flex flex-col gap-6 rounded-xl border border-primary/25 bg-card/75 p-6 shadow-card sm:p-8 lg:flex-row lg:items-end lg:justify-between">
        <div className="max-w-2xl space-y-3">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="border-primary/40 bg-primary/10 text-primary font-semibold">
              <Sparkles className="mr-1 h-3.5 w-3.5" />
              {tx("Không gian Làm việc Cá nhân", "Personal Workspace")}
            </Badge>
          </div>
          <p className="text-sm font-semibold text-primary">{getGreeting()}{name ? `, ${name}` : ""}</p>
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            {dict.pages.dashboard.titleUser}
          </h1>
          <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">
            {dict.pages.dashboard.descUser}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button asChild className="gap-2">
            <Link href="/chat">
              <MessageSquare className="h-4 w-4" />
              {dict.pages.dashboard.btnStartChat}
            </Link>
          </Button>
          <Button asChild variant="outline" className="gap-2">
            <Link href="/workflows">
              <Workflow className="h-4 w-4" />
              {dict.pages.dashboard.btnRunWorkflow}
            </Link>
          </Button>
          <Button asChild variant="ghost" className="gap-2">
            <Link href="/email-intelligence">
              <Inbox className="h-4 w-4" />
              {tx("Hộp thư AI", "AI Inbox")}
            </Link>
          </Button>
        </div>
      </section>

      {/* Quick Launch Cards */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Link href="/chat" className="group block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <Card className="p-5 flex items-center justify-between border-border/80 bg-card hover:border-primary/40 transition-colors">
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">{tx("Trợ lý Trò chuyện", "Conversational AI")}</p>
              <p className="text-lg font-bold text-foreground group-hover:text-primary transition-colors">{tx("Bắt đầu Chat mới", "Start New Chat")}</p>
              <p className="text-xs text-muted-foreground">{agentList.length} {tx("agent sẵn sàng", "agents available")}</p>
            </div>
            <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary">
              <MessageSquare className="h-6 w-6" />
            </div>
          </Card>
        </Link>

        <Link href="/email-intelligence" className="group block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <Card className="p-5 flex items-center justify-between border-border/80 bg-card hover:border-primary/40 transition-colors">
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">{tx("Email Intelligence", "Email Intelligence")}</p>
              <p className="text-lg font-bold text-foreground group-hover:text-primary transition-colors">{tx("Hộp thư thông minh", "Smart Email Inbox")}</p>
              <p className="text-xs text-muted-foreground">{unreadEmails} {tx("email cần xử lý", "pending items")}</p>
            </div>
            <div className="grid h-12 w-12 place-items-center rounded-xl bg-primary/10 text-primary">
              <Mail className="h-6 w-6" />
            </div>
          </Card>
        </Link>

        <Link href="/approvals" className="group block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <Card className="p-5 flex items-center justify-between border-border/80 bg-card hover:border-primary/40 transition-colors">
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">{tx("Phê duyệt Hành động", "Pending Approvals")}</p>
              <p className="text-lg font-bold text-foreground group-hover:text-primary transition-colors">{tx("Yêu cầu cần duyệt", "Action Items")}</p>
              <p className={`text-xs ${pendingActions > 0 ? "text-amber-500 font-semibold" : "text-muted-foreground"}`}>
                {pendingActions} {tx("yêu cầu đang chờ", "pending approvals")}
              </p>
            </div>
            <div className={`grid h-12 w-12 place-items-center rounded-xl ${pendingActions > 0 ? "bg-amber-500/10 text-amber-500" : "bg-primary/10 text-primary"}`}>
              <ShieldAlert className="h-6 w-6" />
            </div>
          </Card>
        </Link>
      </section>

      {/* Pending Approvals Section */}
      {pendingApprovals.length > 0 ? (
        <section className="space-y-3" aria-label={tx("Phê duyệt cần được chú ý", "Approvals that need attention")}>
          <SectionHeader
            title={dict.pages.approvals.pendingDecisions}
            description={tx(`${pendingApprovals.length} hành động tự động cần bạn xác nhận trước khi thực hiện`, `${pendingApprovals.length} action item${pendingApprovals.length === 1 ? "" : "s"} requiring your review`)}
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
                  {String(approval.args_snapshot?.summary || approval.args_snapshot?.title || tx("Xem xét trước khi thực thi", "Review before execution"))}
                </p>
                <span className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-primary">
                  {dict.pages.approvals.btnApprove} <ArrowRight className="h-3 w-3" />
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

      {/* Available AI Assistants Grid */}
      <section className="space-y-4">
        <SectionHeader
          title={dict.pages.dashboard.sectionMyAgents}
          description={dict.pages.dashboard.sectionMyAgentsDesc}
        />
        {agents.isLoading ? (
          <LoadingSkeleton variant="grid" />
        ) : agentList.length ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {agentList.map((agent) => (
              <Link
                key={agent.id}
                href={`/chat?agent=${agent.id}`}
                className="group block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Card glass className="h-full p-5 transition-colors group-hover:border-primary/40 flex flex-col justify-between">
                  <div className="space-y-3">
                    <div className="flex items-start gap-3">
                      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                        {agent.kind === "orchestrator" ? <Sparkles className="h-5 w-5" /> : <Bot className="h-5 w-5" />}
                      </div>
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-foreground">{agent.name}</p>
                        <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                          {agent.description || tx("Trợ lý AI sẵn sàng hỗ trợ giải quyết công việc.", "AI assistant ready to help with tasks.")}
                        </p>
                      </div>
                    </div>
                  </div>
                  <div className="mt-5 flex items-center justify-between pt-3 border-t border-border/50">
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                      {agent.kind === "orchestrator" ? tx("Điều phối", "Orchestrator") : tx("Chuyên trách", "Worker")}
                    </span>
                    <span className="flex items-center gap-1 text-xs font-semibold text-primary group-hover:translate-x-0.5 transition-transform">
                      {dict.nav.chat} <ArrowRight className="h-3 w-3" />
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
            description={tx("Chưa có trợ lý nào được phân quyền cho bạn.", "No assistants currently assigned.")}
          />
        )}
      </section>

      {/* Automated Workflows Shortcuts */}
      {workflowList.length > 0 && (
        <section className="space-y-4">
          <SectionHeader
            title={tx("Quy trình Tự động hóa", "Automated Workflows")}
            description={tx("Khởi chạy các tác vụ liên hoàn tự động chỉ với một lần bấm.", "One-click automated multi-step task workflows.")}
            actions={
              <Button asChild variant="ghost" size="sm" className="gap-1">
                <Link href="/workflows">
                  {dict.common.view} <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            }
          />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {workflowList.slice(0, 3).map((wf) => (
              <Card key={wf.id} glass className="p-4 flex flex-col justify-between hover:border-primary/40 transition-colors">
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Badge variant="outline" className="border-primary/30 bg-primary/5 text-primary text-[11px]">
                      <Workflow className="mr-1 h-3 w-3" />
                      Workflow
                    </Badge>
                    <span className="text-[11px] text-muted-foreground font-mono">
                      {wf.graph?.nodes?.length ?? 0} {tx("bước", "steps")}
                    </span>
                  </div>
                  <p className="font-semibold text-sm text-foreground truncate">{wf.name}</p>
                  <p className="text-xs text-muted-foreground line-clamp-2">
                    {wf.description || tx("Quy trình làm việc tự động.", "Automated task execution.")}
                  </p>
                </div>
                <div className="mt-4 flex items-center justify-end pt-2 border-t border-border/40">
                  <Button asChild size="sm" variant="outline" className="h-7 text-xs gap-1 text-primary">
                    <Link href={`/workflows`}>
                      {dict.pages.dashboard.btnRunWorkflow} <ArrowRight className="h-3 w-3" />
                    </Link>
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
