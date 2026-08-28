"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  CalendarDays,
  CheckCheck,
  Clock3,
  ExternalLink,
  Filter,
  Mail,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Trash2,
  Inbox,
  UserCheck,
  ChevronRight,
} from "lucide-react";
import { useTranslation } from "@/lib/i18n";

const NOTIFICATION_TYPE_KEYS: Record<string, string> = {
  CONTRACT_UPDATE: "notifications.contractUpdate",
  CALENDAR_INVITE: "notifications.calendarInvite",
  GENERAL: "notifications.general",
};

function notificationTypeLabel(type: string, t: (p: string, f?: string) => string): string {
  const key = NOTIFICATION_TYPE_KEYS[type] || type;
  if (key.includes(".")) return t(key, type);
  return key;
}
import { useCustomerIntelligenceNotifications, useMarkCustomerIntelligenceNotificationRead, useUrlSearchParam } from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingSkeleton, DataPagination, ConfirmDialog } from "@/components/shared";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { getActiveOrgId } from "@/lib/auth";
import { emailIntelligenceQueryKeys } from "@/lib/email-intelligence/query-keys";
import type { CustomerIntelligenceNotification } from "@/types";

type DateRange = "all" | "today" | "7d" | "30d";

type Rule = {
  id: string;
  name: string;
  match_type: string;
  match_value: string;
  action: string;
  calendar_connection_id: string;
  expires_at: string;
  is_active: boolean;
};

type RuleResponse = {
  rules: Rule[];
};

function dateRange(range: DateRange) {
  if (range === "all") return {};
  const end = new Date();
  const start = new Date();
  if (range === "today") {
    start.setHours(0, 0, 0, 0);
  } else if (range === "7d") {
    start.setDate(end.getDate() - 7);
  } else if (range === "30d") {
    start.setDate(end.getDate() - 30);
  }
  return {
    from_date: start.toISOString(),
    to_date: end.toISOString(),
  };
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function createIdempotencyKey() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `idemp-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export default function EmailIntelligencePage() {
  const { t, dict, locale, tx } = useTranslation();
  const [tabParam, setTabParam] = useUrlSearchParam("tab");
  const activeTab = (tabParam as "inbox" | "rules") || "inbox";

  const [unreadOnly, setUnreadOnly] = React.useState(false);
  const [range, setRange] = React.useState<DateRange>("all");
  const [notificationType, setNotificationType] = React.useState("");
  const [searchInput, setSearchInput] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [pageSize, setPageSize] = React.useState(10);
  const [pageIndex, setPageIndex] = React.useState(0);
  const [pageCursors, setPageCursors] = React.useState<(string | null)[]>([null]);
  const markRead = useMarkCustomerIntelligenceNotificationRead();

  // Rules state
  const orgId = getActiveOrgId();
  const qc = useQueryClient();
  const rules = useQuery({
    queryKey: emailIntelligenceQueryKeys(orgId).rules(),
    queryFn: () => api.get<RuleResponse>("/api/email-intelligence/trusted-rules"),
  });
  const [ruleName, setRuleName] = React.useState("");
  const [ruleDomain, setRuleDomain] = React.useState("");
  const [calendarConnectionId, setCalendarConnectionId] = React.useState("");
  const [ruleExpiry, setRuleExpiry] = React.useState("");
  const [ruleError, setRuleError] = React.useState("");

  const [rulePage, setRulePage] = React.useState(1);
  const [rulePageSize, setRulePageSize] = React.useState(10);

  const createRule = useMutation({
    mutationFn: () =>
      api.post<Rule>(
        "/api/email-intelligence/trusted-rules",
        {
          name: ruleName,
          match_type: "DOMAIN",
          match_value: ruleDomain,
          calendar_connection_id: calendarConnectionId,
          minimum_classification_confidence: 0.95,
          maximum_events_per_day: 3,
          expires_at: new Date(ruleExpiry).toISOString(),
        },
        { headers: { "Idempotency-Key": createIdempotencyKey() } },
      ),
    onSuccess: () => {
      setRuleName("");
      setRuleDomain("");
      setCalendarConnectionId("");
      setRuleExpiry("");
      toast.success(tx("Đã tạo quy tắc phê duyệt tự động", "Trusted calendar rule created"));
      void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).rules() });
    },
    onError: (value) => setRuleError(value instanceof Error ? value.message : (tx("Lỗi khi tạo quy tắc", "Failed to create rule"))),
  });

  React.useEffect(() => {
    const timer = window.setTimeout(() => setQuery(searchInput.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const resetPaging = React.useCallback(() => {
    setPageIndex(0);
    setPageCursors([null]);
  }, []);

  const filters = React.useMemo(
    () => ({
      unreadOnly,
      cursor: pageCursors[pageIndex],
      limit: pageSize,
      query,
      notificationType,
      ...dateRange(range),
    }),
    [notificationType, pageCursors, pageIndex, pageSize, query, range, unreadOnly],
  );

  const notifications = useCustomerIntelligenceNotifications(filters);
  const items = React.useMemo(
    () => [...(notifications.data?.items ?? [])].sort((a, b) => new Date(b.received_at).getTime() - new Date(a.received_at).getTime()),
    [notifications.data?.items],
  );

  const paginatedRules = React.useMemo(() => {
    const start = (rulePage - 1) * rulePageSize;
    return (rules.data?.rules ?? []).slice(start, start + rulePageSize);
  }, [rules.data?.rules, rulePage, rulePageSize]);

  function changeUnread(val: boolean) {
    setUnreadOnly(val);
    resetPaging();
  }

  function changeRange(val: DateRange) {
    setRange(val);
    resetPaging();
  }

  function changeType(val: string) {
    setNotificationType(val);
    resetPaging();
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Mail}
        title={dict.pages.emailIntelligence.title}
        description={dict.pages.emailIntelligence.description}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void notifications.refetch();
              if (activeTab === "rules") void rules.refetch();
            }}
            className="gap-2"
          >
            <RefreshCw className="h-4 w-4" />
            {tx("Làm mới", "Refresh")}
          </Button>
        }
      />

      {/* Segmented Navigation Tabs */}
      <div className="flex gap-2 border-b border-border/70 pb-2">
        <Button
          type="button"
          variant={activeTab === "inbox" ? "secondary" : "ghost"}
          onClick={() => setTabParam("inbox")}
          className="gap-2 font-medium"
        >
          <Mail className="h-4 w-4 text-primary" />
          {tx("Hộp thư thông minh", "Inbox")}
        </Button>

        <Button
          type="button"
          variant={activeTab === "rules" ? "secondary" : "ghost"}
          onClick={() => setTabParam("rules")}
          className="gap-2 font-medium"
        >
          <ShieldCheck className="h-4 w-4 text-primary" />
          {tx("Quy tắc Tự động duyệt", "Trusted Rules")}
        </Button>
      </div>

      {/* Tab 1: Email Inbox View */}
      {activeTab === "inbox" && (
        <div className="space-y-4">
          {/* Filter Bar */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative flex-1 max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder={tx("Tìm theo người gửi, tiêu đề, công ty...", "Search sender, subject, company...")}
                className="pl-9 text-xs"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className="inline-flex rounded-lg border border-border bg-muted/40 p-0.5">
                <Button
                  size="sm"
                  variant={!unreadOnly ? "secondary" : "ghost"}
                  className="h-7 text-xs font-medium"
                  onClick={() => changeUnread(false)}
                >
                  {tx("Tất cả", "All")}
                </Button>
                <Button
                  size="sm"
                  variant={unreadOnly ? "secondary" : "ghost"}
                  className="h-7 text-xs font-medium"
                  onClick={() => changeUnread(true)}
                >
                  {tx("Chưa đọc", "Unread")}
                </Button>
              </div>

              <select
                value={range}
                onChange={(e) => changeRange(e.target.value as DateRange)}
                className="flex h-8 cursor-pointer rounded-lg border border-border bg-background px-2.5 py-1 text-xs text-foreground shadow-sm hover:border-primary/40 focus-visible:outline-none"
              >
                <option value="all">{tx("Toàn thời gian", "All Time")}</option>
                <option value="today">{tx("Hôm nay", "Today")}</option>
                <option value="7d">{tx("7 ngày qua", "Last 7 Days")}</option>
                <option value="30d">{tx("30 ngày qua", "Last 30 Days")}</option>
              </select>

              <select
                value={notificationType}
                onChange={(e) => changeType(e.target.value)}
                className="flex h-8 cursor-pointer rounded-lg border border-border bg-background px-2.5 py-1 text-xs text-foreground shadow-sm hover:border-primary/40 focus-visible:outline-none"
              >
                <option value="">{tx("Tất cả danh mục", "All Categories")}</option>
                <option value="CONTRACT_UPDATE">{tx("Cập nhật hợp đồng", "Contract Updates")}</option>
                <option value="CALENDAR_INVITE">{tx("Lời mời họp lịch", "Calendar Invites")}</option>
                <option value="GENERAL">{tx("Tổng hợp thông thường", "General")}</option>
              </select>
            </div>
          </div>

          {/* Inbox List */}
          {notifications.isLoading ? (
            <LoadingSkeleton variant="table" />
          ) : notifications.isError ? (
            <ErrorState
              title={tx("Không thể tải thông báo email", "Unable to load notifications")}
              description={tx("Luồng dữ liệu email chưa sẵn sàng.", "Email triage feed could not be retrieved.")}
              onRetry={() => void notifications.refetch()}
            />
          ) : items.length ? (
            <div className="space-y-3">
              {items.map((n) => (
                <Card
                  key={n.id}
                  glass
                  className={`shadow-card border-border/80 p-4 transition-all hover:border-primary/40 ${
                    !n.read_at ? "bg-primary/[0.02] border-primary/30 ring-1 ring-primary/10" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-border bg-muted/40 font-semibold text-primary text-xs">
                        {initials(n.sender_email || "Client")}
                      </div>
                      <div className="min-w-0 space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="font-semibold text-xs text-foreground">{n.sender_email}</p>
                          {n.type && (
                            <Badge variant="outline" className="text-[10px] uppercase font-mono">
                              {notificationTypeLabel(n.type, t)}
                            </Badge>
                          )}
                          {!n.read_at && (
                            <span className="inline-flex h-2 w-2 rounded-full bg-primary" aria-label={tx("Chưa đọc", "Unread")} />
                          )}
                        </div>
                        <p className="font-medium text-xs text-foreground/90">{n.subject}</p>
                        <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">{n.body}</p>
                        {n.classification && (
                          <div className="mt-2 rounded bg-amber-500/10 border border-amber-500/20 px-2.5 py-1 text-[11px] text-amber-600 dark:text-amber-400 font-medium">
                            🏷️ {tx("Phân loại:", "Classification:")} {n.classification}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-col items-end gap-2 shrink-0">
                      <span className="text-[11px] text-muted-foreground font-mono">
                        {new Date(n.received_at).toLocaleDateString(tx("vi-VN", "en-US"), {
                          month: "short",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                      {!n.read_at && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 gap-1 text-[11px] text-muted-foreground hover:text-foreground"
                          onClick={() => markRead.mutate(n.id)}
                        >
                          <CheckCheck className="h-3.5 w-3.5" />
                          {tx("Đã xem", "Mark read")}
                        </Button>
                      )}
                    </div>
                  </div>
                </Card>
              ))}

              {/* Standard Pager Navigation */}
              <div className="flex items-center justify-between border-t border-border/60 pt-3 text-xs text-muted-foreground">
                <span>
                  {tx(`Trang ${pageIndex + 1}`, `Page ${pageIndex + 1}`)}
                </span>
                <div className="flex items-center gap-1.5">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 text-xs"
                    disabled={pageIndex === 0 || notifications.isLoading}
                    onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
                  >
                    {tx("Trang trước", "Previous")}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 text-xs"
                    disabled={!notifications.data?.next_cursor || notifications.isLoading}
                    onClick={() => {
                      if (notifications.data?.next_cursor) {
                        setPageCursors((prev) => {
                          const next = [...prev];
                          next[pageIndex + 1] = notifications.data?.next_cursor ?? null;
                          return next;
                        });
                        setPageIndex((p) => p + 1);
                      }
                    }}
                  >
                    {tx("Trang sau", "Next")}
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <EmptyState
              icon={Inbox}
              title={tx("Hộp thư đã xử lý gọn gàng", "All caught up in your inbox")}
              description={tx("Không có email nào khớp với bộ lọc đang chọn.", "No incoming emails matched your active filters.")}
            />
          )}
        </div>
      )}

      {/* Tab 2: Trusted Rules View */}
      {activeTab === "rules" && (
        <div className="space-y-4">
          <Card className="border-amber-500/30 bg-amber-500/[0.04] shadow-card">
            <CardContent className="space-y-1.5 p-4 text-xs">
              <p className="font-semibold text-amber-500 flex items-center gap-1.5">
                <ShieldCheck className="h-4 w-4" /> {tx("Chính sách An toàn Doanh nghiệp", "Production Safety Policy Defaults")}
              </p>
              <p className="text-muted-foreground leading-relaxed">
                {tx("Các quy tắc tự động đặt lịch chạy trong phạm vi nghiêm ngặt (CALENDAR_AUTO_CREATE). Yêu cầu tên miền doanh nghiệp chính xác, ngày hết hạn, giới hạn số sự kiện mỗi ngày và xác thực SPF/DKIM/DMARC.", "Rules currently operate with strict safety boundaries (CALENDAR_AUTO_CREATE). Rules require a verified exact company domain, expiration date, daily execution caps, and SPF/DKIM/DMARC authentication.")}
              </p>
            </CardContent>
          </Card>

          <Card glass className="shadow-card border-border/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-foreground">
                {tx("Tạo Quy tắc Phê duyệt Lịch tự động", "Create Trusted Calendar Rule")}
              </CardTitle>
              <CardDescription className="text-xs">
                {t("pages.emailIntelligence.autoApproveDesc", "Tự động chấp thuận lời mời họp từ tên miền đối tác uy tín đáp ứng tiêu chuẩn an toàn.")}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  setRuleError("");
                  createRule.mutate();
                }}
                className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 items-end"
              >
                <div className="space-y-1">
                  <Label className="text-xs">{tx("Tên quy tắc", "Rule Name")}</Label>
                  <Input
                    value={ruleName}
                    onChange={(e) => setRuleName(e.target.value)}
                    placeholder={tx("ví dụ: Khách hàng VIP", "e.g. Strategic Partner")}
                    required
                    className="text-xs"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">{tx("Tên miền đối tác", "Partner Domain")}</Label>
                  <Input
                    value={ruleDomain}
                    onChange={(e) => setRuleDomain(e.target.value)}
                    placeholder={tx("partner.com", "partner.com")}
                    required
                    className="text-xs font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">{tx("ID Kết nối Lịch", "Calendar Connection ID")}</Label>
                  <Input
                    value={calendarConnectionId}
                    onChange={(e) => setCalendarConnectionId(e.target.value)}
                    placeholder={tx("conn-google-...", "conn-google-...")}
                    required
                    className="text-xs font-mono"
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">{tx("Ngày hết hạn", "Expiration Date")}</Label>
                  <Input
                    type="date"
                    value={ruleExpiry}
                    onChange={(e) => setRuleExpiry(e.target.value)}
                    required
                    className="text-xs"
                  />
                </div>
                <div className="sm:col-span-2 lg:col-span-4 flex items-center justify-between pt-2">
                  {ruleError && <p className="text-xs text-destructive">{ruleError}</p>}
                  <div className="ml-auto">
                    <Button type="submit" disabled={createRule.isPending} className="gap-1.5 font-medium text-xs">
                      <Plus className="h-4 w-4" />
                      {tx("Lưu quy tắc", "Create Rule")}
                    </Button>
                  </div>
                </div>
              </form>
            </CardContent>
          </Card>

          {/* Rules List Table */}
          <Card glass className="overflow-hidden shadow-card border-border/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-foreground">
                {tx("Danh sách Quy tắc đang hiệu lực", "Active Trusted Rules")}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {rules.isLoading ? (
                <div className="p-6"><LoadingSkeleton variant="table" /></div>
              ) : rules.isError ? (
                <div className="p-6">
                  <ErrorState
                    title={tx("Không thể tải quy tắc", "Unable to load rules")}
                    description={tx("Dữ liệu quy tắc tin cậy chưa sẵn sàng.", "Trusted rules could not be loaded.")}
                    onRetry={() => void rules.refetch()}
                  />
                </div>
              ) : rules.data?.rules?.length ? (
                <div>
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/40">
                        <TableHead className="text-xs font-semibold">{tx("Tên quy tắc", "Name")}</TableHead>
                        <TableHead className="text-xs font-semibold">{tx("Tên miền", "Domain")}</TableHead>
                        <TableHead className="text-xs font-semibold">{tx("Hành động", "Action")}</TableHead>
                        <TableHead className="text-xs font-semibold">{tx("Hết hạn", "Expires")}</TableHead>
                        <TableHead className="text-xs font-semibold">{tx("Trạng thái", "Status")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedRules.map((r) => (
                        <TableRow key={r.id} className="hover:bg-muted/20 transition-colors">
                          <TableCell className="font-medium text-xs text-foreground">{r.name}</TableCell>
                          <TableCell className="font-mono text-xs text-muted-foreground">{r.match_value}</TableCell>
                          <TableCell className="font-mono text-[10px] text-muted-foreground">
                            <Badge variant="outline">{r.action}</Badge>
                          </TableCell>
                          <TableCell className="text-xs font-mono text-muted-foreground">
                            {new Date(r.expires_at).toLocaleDateString(tx("vi-VN", "en-US"))}
                          </TableCell>
                          <TableCell>
                            <Badge variant={r.is_active ? "success" : "secondary"} className="text-[10px]">
                              {r.is_active ? (tx("Đang chạy", "active")) : (tx("Tắt", "disabled"))}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                  <div className="p-3 border-t border-border/60">
                    <DataPagination
                      page={rulePage}
                      pageSize={rulePageSize}
                      totalItems={rules.data.rules.length}
                      onPageChange={setRulePage}
                      onPageSizeChange={setRulePageSize}
                      pageSizeOptions={[5, 10, 25]}
                    />
                  </div>
                </div>
              ) : (
                <div className="p-6">
                  <EmptyState
                    icon={ShieldAlert}
                    title={tx("Chưa có quy tắc tin cậy nào", "No trusted rules yet")}
                    description={tx("Thêm tên miền đối tác để kích hoạt tự động đặt lịch an toàn.", "Add a partner domain to enable automated meeting approvals.")}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
