"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import {
  CalendarDays,
  ChevronRight,
  Clock3,
  Gauge,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Zap,
} from "lucide-react";
import {
  useApprovals,
  useCurrentRole,
  useDecideApproval,
  useMe,
  useQuotaUsage,
  useUrlSearchParam,
} from "@/hooks";
import { createServerClock, formatRemaining, remainingMs } from "@/lib/email-intelligence/server-time";
import { createIdempotencyKey } from "@/lib/email-intelligence/idempotency";
import type { ApprovalRequest } from "@/types";
import { PageHeader } from "@/components/page-header";
import { useTranslation } from "@/lib/i18n";
import { formatVietnamDateTime } from "@/lib/datetime";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState, ErrorState, LoadingSkeleton, ConfirmDialog, DataPagination } from "@/components/shared";
import { approvalTitle } from "@/components/layout/approval-bell";
import { getActiveOrgId } from "@/lib/auth";

function ApprovalExpiry({ expiresAt, serverTime }: { expiresAt?: string | null; serverTime?: string | null }) {
    const { t, locale } = useTranslation();
  const [remaining, setRemaining] = React.useState<number | null>(null);
  React.useEffect(() => {
    if (!expiresAt || !serverTime) return;
    const clock = createServerClock(serverTime);
    const update = () => setRemaining(remainingMs(expiresAt, clock));
    update();
    const timer = window.setInterval(update, 30_000);
    return () => window.clearInterval(timer);
  }, [expiresAt, serverTime]);
  if (remaining === null) return null;
  return <span className={remaining <= 15 * 60 * 1000 ? "font-semibold text-destructive" : "text-muted-foreground"}>{formatRemaining(remaining, t)}</span>;
}

function eventDetails(approval: ApprovalRequest, locale: string) {
  const args = approval.args_snapshot || {};
  return {
    summary: String(args.summary || args.title || args.subject || (locale === "vi" ? "Hành động được yêu cầu" : "Requested action")),
    start: args.start ? String(args.start) : null,
    end: args.end ? String(args.end) : null,
    attendees: Array.isArray(args.attendees) ? args.attendees.map(String) : [],
    source: args.description ? String(args.description) : (locale === "vi" ? "OpenAgent đã tạo yêu cầu này từ quy trình làm việc hoặc email của bạn." : "OpenAgent generated this request from your workflow or email."),
  };
}

function ApprovalCard({ approval, onOpen, onSubmit }: { approval: ApprovalRequest; onOpen: () => void; onSubmit: (decision: "approved" | "rejected") => Promise<void> }) {
  const { t, locale } = useTranslation();
  const details = eventDetails(approval, locale);
  const highRisk = approval.risk_level === "HIGH";
  return (
    <Card className="border-border/80 bg-card transition-colors hover:border-primary/40 shadow-card">
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div className={`mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-xl ${highRisk ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary"}`}>
              {highRisk ? <ShieldAlert className="h-5 w-5" aria-hidden="true" /> : <CalendarDays className="h-5 w-5" aria-hidden="true" />}
            </div>
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-foreground">{approvalTitle(approval, locale)}</h2>
              <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{details.summary}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2 text-xs">
            <Badge variant={highRisk ? "destructive" : "outline"}>{highRisk ? (locale === "vi" ? "RỦI RO CAO" : "HIGH RISK") : (locale === "vi" ? "TIÊU CHUẨN" : "STANDARD")}</Badge>
            <Badge variant="outline">{approval.approval_mode || (locale === "vi" ? "RÕ RÀNG" : "EXPLICIT")}</Badge>
            <span className="flex items-center gap-1"><Clock3 className="h-3.5 w-3.5" aria-hidden="true" /><ApprovalExpiry expiresAt={approval.expires_at} serverTime={approval.server_time} /></span>
          </div>
        </div>
        <div className="grid gap-3 rounded-xl border border-border/70 bg-muted/20 p-4 text-sm sm:grid-cols-3">
          <div><dt className="text-xs font-medium text-muted-foreground">{locale === "vi" ? "Khi nào" : "When"}</dt><dd className="mt-1 text-foreground">{details.start ? `${formatVietnamDateTime(details.start)} · ${t("pages.approvals.vietnamTime", "Giờ Việt Nam")}` : (locale === "vi" ? "Chưa xác định" : "Not specified")}</dd></div>
          <div><dt className="text-xs font-medium text-muted-foreground">{locale === "vi" ? "Người tham dự" : "Attendees"}</dt><dd className="mt-1 truncate text-foreground">{details.attendees.length ? details.attendees.join(", ") : (locale === "vi" ? "Chưa xác định" : "Not specified")}</dd></div>
          <div><dt className="text-xs font-medium text-muted-foreground">{locale === "vi" ? "Nguồn" : "Source"}</dt><dd className="mt-1 truncate text-foreground">{approval.run_type === "agent" ? (locale === "vi" ? "Quy trình làm việc của Agent" : "Agent workflow") : (locale === "vi" ? "Chạy quy trình làm việc" : "Workflow run")}</dd></div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button variant="ghost" size="sm" className="gap-1" onClick={onOpen}>{locale === "vi" ? "Xem chi tiết " : "View details "}<ChevronRight className="h-4 w-4" aria-hidden="true" /></Button>
          <div className="flex gap-2">
            <ConfirmDialog trigger={<Button variant="outline" size="sm">{locale === "vi" ? "Từ chối" : "Reject"}</Button>} title={locale === "vi" ? "Từ chối phê duyệt này?" : "Reject this approval?"} description={locale === "vi" ? "Hành động được yêu cầu sẽ không chạy. Quyết định này không thể hoàn tác." : "The requested action will not run. This decision cannot be undone."} confirmLabel={locale === "vi" ? "Từ chối" : "Reject"} destructive onConfirm={() => onSubmit("rejected")} />
            <Button size="sm" onClick={() => void onSubmit("approved")} disabled={approval.expires_at ? Boolean(approval.server_time && remainingMs(approval.expires_at, createServerClock(approval.server_time)) === 0) : false}>{locale === "vi" ? "Phê duyệt" : "Approve"}</Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ApprovalsPage() {
  const { t, dict, locale } = useTranslation();
  const [tabParam, setTabParam] = useUrlSearchParam("tab");
  const activeTab = (tabParam as "approvals" | "quota") || "approvals";

  const searchParams = useSearchParams();
  const highlightId = searchParams.get("id") || searchParams.get("approval_id");
  const role = useCurrentRole();
  const me = useMe();
  const isUserRole = role === "user";
  const orgId = me.data?.active_org_id || getActiveOrgId() || me.data?.memberships?.[0]?.org_id;

  const approvals = useApprovals();
  const usage = useQuotaUsage(orgId);
  const decide = useDecideApproval();
  const [selected, setSelected] = React.useState<ApprovalRequest | null>(null);

  const items = approvals.data ?? [];
  const urgent = items.filter((item) => item.risk_level === "HIGH").length;

  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(5);

  const paginatedItems = React.useMemo(() => {
    const start = (page - 1) * pageSize;
    return items.slice(start, start + pageSize);
  }, [items, page, pageSize]);

  React.useEffect(() => {
    if (highlightId && items.length) {
      setSelected(items.find((item) => item.id === highlightId) ?? null);
    }
  }, [items, highlightId]);

  async function submit(id: string, decision: "approved" | "rejected") {
    try {
      const result = await decide.mutateAsync({ id, decision, idempotencyKey: createIdempotencyKey() });
      setSelected(null);
      toast.success(decision === "approved" ? (locale === "vi" ? "Đã chấp nhận phê duyệt" : "Approval accepted") : (locale === "vi" ? "Đã từ chối phê duyệt" : "Approval rejected"));
      if (result.status !== decision) toast.info(locale === "vi" ? "Máy chủ đã trả về trạng thái phê duyệt chính thức." : "The server returned the canonical approval state.");
    } catch (error: any) {
      toast.error(error?.status === 409 ? (locale === "vi" ? "Phê duyệt này đã được xử lý" : "This approval was already handled") : error?.status === 412 ? (locale === "vi" ? "Phê duyệt đã thay đổi, đang tải lại dữ liệu mới nhất" : "Approval changed, reloading latest data") : error?.message || (locale === "vi" ? "Không thể cập nhật phê duyệt" : "Could not update approval"));
      void approvals.refetch();
    }
  }

  return (
    <div className="space-y-6">
      {/* 1. Page Header */}
      <PageHeader
        icon={ShieldCheck}
        title={dict.pages.approvals.title}
        description={dict.pages.approvals.description}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void approvals.refetch();
              void usage.refetch();
            }}
            disabled={approvals.isFetching || usage.isFetching}
            className="gap-1.5"
          >
            <RefreshCw className={approvals.isFetching || usage.isFetching ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
            {locale === "vi" ? "Làm mới" : "Refresh"}
          </Button>
        }
      />

      {/* 2. Metrics Ribbon */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{items.length}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{locale === "vi" ? "Quyết định đang chờ" : "Pending Decisions"}</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${urgent > 0 ? "bg-destructive/10 text-destructive" : "bg-muted text-muted-foreground"}`}>
            <ShieldAlert className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{urgent}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{locale === "vi" ? "Hành động rủi ro cao" : "High Risk Actions"}</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-500/10 text-emerald-500">
            <Gauge className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">
              ${usage.data?.monthly_cost_usd?.toFixed(2) || "0.00"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">
              {locale === "vi" ? "Chi tiêu hàng tháng / $" : "Monthly Spend / $"}{usage.data?.monthly_cost_limit_usd || 100}
            </p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sky-500/10 text-sky-500">
            <Zap className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">
              {usage.data?.active_run_leases || 0}
            </p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{locale === "vi" ? "Phiên chạy đồng thời đang hoạt động" : "Active Concurrent Leases"}</p>
          </div>
        </Card>
      </div>

      {/* 3. Segmented Navigation Tabs */}
      <div className="flex gap-2 border-b border-border/70 pb-2">
        <Button
          type="button"
          variant={activeTab === "approvals" ? "secondary" : "ghost"}
          onClick={() => setTabParam("approvals")}
          className="gap-2 font-medium"
        >
          <ShieldCheck className="h-4 w-4" />
          {locale === "vi" ? "Phê duyệt" : "Approvals"}
          <Badge variant={urgent > 0 ? "destructive" : "outline"} className="ml-1 text-[10px] font-mono">
            {items.length}
          </Badge>
        </Button>

        <Button
          type="button"
          variant={activeTab === "quota" ? "secondary" : "ghost"}
          onClick={() => setTabParam("quota")}
          className="gap-2 font-medium"
        >
          <Gauge className="h-4 w-4" />
          {locale === "vi" ? "Sử dụng" : "Usage"}
        </Button>
      </div>

      {/* 4. Tab 1: Pending Approvals */}
      {activeTab === "approvals" && (
        <div className="space-y-3">
          {approvals.isLoading ? (
            <LoadingSkeleton variant="table" />
          ) : approvals.isError ? (
            <ErrorState
              title={locale === "vi" ? "Không thể tải các phê duyệt" : "Unable to load approvals"}
              description={locale === "vi" ? "Không thể tải yêu cầu phê duyệt." : "Approval requests could not be loaded."}
              onRetry={() => void approvals.refetch()}
            />
          ) : items.length ? (
            <div className="space-y-4">
              <div className="space-y-3" aria-label="Pending approvals">
                {paginatedItems.map((approval) => (
                  <ApprovalCard
                    key={approval.id}
                    approval={approval}
                    onOpen={() => setSelected(approval)}
                    onSubmit={(decision) => submit(approval.id, decision)}
                  />
                ))}
              </div>
              <DataPagination
                page={page}
                pageSize={pageSize}
                totalItems={items.length}
                onPageChange={setPage}
                onPageSizeChange={setPageSize}
                pageSizeOptions={[3, 5, 10, 20]}
              />
            </div>
          ) : (
            <EmptyState
              icon={ShieldCheck}
              title={locale === "vi" ? "Đã hoàn thành tất cả" : "All caught up"}
              description={locale === "vi" ? "Hiện không có hành động nào cần bạn phê duyệt." : "No actions currently need your approval."}
            />
          )}
        </div>
      )}

      {/* 5. Tab 2: Monthly Quota & Usage */}
      {activeTab === "quota" && (
        <div className="space-y-4">
          {usage.isLoading ? (
            <LoadingSkeleton variant="table" />
          ) : usage.isError ? (
            <ErrorState
              title={locale === "vi" ? "Không thể tải mức sử dụng hạn ngạch" : "Unable to load quota usage"}
              description={locale === "vi" ? "Không thể tải các chỉ số sử dụng." : "Usage metrics could not be loaded."}
              onRetry={() => void usage.refetch()}
            />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              <Card className="shadow-card border-border/80">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base font-semibold">{locale === "vi" ? "Chi tiêu & Ngân sách" : "Spend & Budget"}</CardTitle>
                  <CardDescription className="text-xs">{locale === "vi" ? "Chi tiêu tháng hiện tại so với ngưỡng của tổ chức." : "Current month spend against organization threshold."}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{locale === "vi" ? "Chi tiêu hàng tháng" : "Monthly Spend"}</span>
                    <span className="font-semibold text-foreground">${usage.data?.monthly_cost_usd?.toFixed(2) || "0.00"}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{locale === "vi" ? "Giới hạn ngân sách hàng tháng" : "Monthly Budget Limit"}</span>
                    <span className="font-semibold text-foreground">${usage.data?.monthly_cost_limit_usd || 100}</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all"
                      style={{
                        width: `${Math.min(100, (((usage.data?.monthly_cost_usd || 0) / (usage.data?.monthly_cost_limit_usd || 100)) * 100))}%`,
                      }}
                    />
                  </div>
                </CardContent>
              </Card>

              <Card className="shadow-card border-border/80">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base font-semibold">{locale === "vi" ? "Đồng thời tài nguyên" : "Resource Concurrency"}</CardTitle>
                  <CardDescription className="text-xs">{locale === "vi" ? "Phân bổ worker runtime đang hoạt động." : "Active runtime worker allocations."}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{locale === "vi" ? "Phiên chạy đang hoạt động" : "Active Run Leases"}</span>
                    <span className="font-semibold text-foreground">{usage.data?.active_run_leases || 0}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{locale === "vi" ? "Giới hạn chạy đồng thời" : "Concurrent Run Limit"}</span>
                    <span className="font-semibold text-foreground">{usage.data?.concurrent_run_limit || 5}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">{locale === "vi" ? "Agent đã đăng ký" : "Registered Agents"}</span>
                    <span className="font-semibold text-foreground">{usage.data?.agents || 0} / {usage.data?.agent_limit || (locale === "vi" ? "Không giới hạn" : "Unlimited")}</span>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      )}

      {/* Modal Detail View */}
      <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-xl">
          {selected && (() => {
            const details = eventDetails(selected, locale);
            return (
              <>
                <DialogHeader>
                  <DialogTitle>{approvalTitle(selected, locale)}</DialogTitle>
                  <DialogDescription>{locale === "vi" ? "Xem xét chi tiết hành động trước khi cho phép OpenAgent thực thi nó." : "Review the action details before allowing OpenAgent to execute it."}</DialogDescription>
                </DialogHeader>
                <div className="space-y-5" tabIndex={-1} autoFocus>
                  <section>
                    <h3 className="text-sm font-semibold text-foreground">{locale === "vi" ? "Tại sao cần phê duyệt" : "Why this needs approval"}</h3>
                    <p className="mt-1 text-sm text-muted-foreground">{details.source}</p>
                  </section>
                  <section className="space-y-3 rounded-xl border border-border/70 bg-muted/20 p-4">
                    <h3 className="text-sm font-semibold text-foreground">{locale === "vi" ? "Chi tiết hành động" : "Action details"}</h3>
                    <div className="grid gap-3 text-sm">
                      <div>
                        <span className="text-muted-foreground">{locale === "vi" ? "Tóm tắt" : "Summary"}</span>
                        <p className="font-medium text-foreground">{details.summary}</p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">{locale === "vi" ? "Khi nào" : "When"}</span>
                        <p className="font-medium text-foreground">
                          {details.start ? `${formatVietnamDateTime(details.start)} · ${t("pages.approvals.vietnamTime", "Giờ Việt Nam")}` : "Not specified"}
                        </p>
                      </div>
                      <div>
                        <span className="text-muted-foreground">{locale === "vi" ? "Người tham dự" : "Attendees"}</span>
                        <p className="break-words font-medium text-foreground">
                          {details.attendees.length ? details.attendees.join(", ") : "Not specified"}
                        </p>
                      </div>
                    </div>
                  </section>
                  <section className="flex flex-wrap gap-2">
                    <Badge variant={selected.risk_level === "HIGH" ? "destructive" : "outline"}>
                      {selected.risk_level || (locale === "vi" ? "TIÊU CHUẨN" : "STANDARD")}
                    </Badge>
                    <Badge variant="outline">{selected.approval_mode || (locale === "vi" ? "PHÊ DUYỆT RÕ RÀNG" : "EXPLICIT APPROVAL")}</Badge>
                    <Badge variant="outline">
                      <ApprovalExpiry expiresAt={selected.expires_at} serverTime={selected.server_time} />
                    </Badge>
                  </section>
                </div>
                <DialogFooter>
                  <ConfirmDialog
                    trigger={<Button variant="outline">{locale === "vi" ? "Từ chối" : "Reject"}</Button>}
                    title={locale === "vi" ? "Từ chối phê duyệt này?" : "Reject this approval?"}
                    description={locale === "vi" ? "Hành động được yêu cầu sẽ không chạy." : "The requested action will not run."}
                    confirmLabel={locale === "vi" ? "Từ chối" : "Reject"}
                    destructive
                    onConfirm={() => submit(selected.id, "rejected")}
                  />
                  <Button
                    onClick={() => void submit(selected.id, "approved")}
                    disabled={
                      selected.expires_at
                        ? Boolean(
                            selected.server_time &&
                              remainingMs(selected.expires_at, createServerClock(selected.server_time)) === 0,
                          )
                        : false
                    }
                  >
                    {locale === "vi" ? "Approve" : "Approve"}</Button>
                </DialogFooter>
              </>
            );
          })()}
        </DialogContent>
      </Dialog>
    </div>
  );
}
