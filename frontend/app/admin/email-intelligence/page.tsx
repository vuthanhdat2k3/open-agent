"use client";

import * as React from "react";
import { Activity, Database, GitBranch, Search, ShieldAlert, Timer, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { useTranslation } from "@/lib/i18n";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ErrorState, LoadingSkeleton, DataPagination, EmptyState } from "@/components/shared";
import { useQuery } from "@tanstack/react-query";
import { getActiveOrgId } from "@/lib/auth";
import { emailIntelligenceQueryKeys } from "@/lib/email-intelligence/query-keys";

type Overview = {
  connections: { total: number; healthy: number; unhealthy: number };
  queue: { ready: number; retrying: number; oldest_age_seconds: number; dead_letter: number };
  reviews: { open: number; due_soon: number; breached: number };
  scheduler: { healthy: boolean; missed_occurrences: number };
};

function useAdminResource<T>(resource: string, enabled: boolean) {
  const orgId = getActiveOrgId();
  return useQuery({
    queryKey: ["admin-email-intelligence", orgId, resource],
    queryFn: () => api.get<T>(`/api/admin/email-intelligence/${resource}`),
    enabled,
    refetchInterval: 30_000,
  });
}

export default function EmailOperationsPage() {
  const { t, dict, locale, tx } = useTranslation();
  const orgId = getActiveOrgId();
  const overview = useQuery({
    queryKey: emailIntelligenceQueryKeys(orgId).adminOverview,
    queryFn: () => api.get<Overview>("/api/admin/email-intelligence/overview"),
    refetchInterval: 30_000,
  });
  const [tab, setTab] = React.useState("overview");
  const [traceId, setTraceId] = React.useState("");
  const queue = useAdminResource<Array<Record<string, unknown>>>("queue", tab === "queue");
  const schedulers = useAdminResource<Array<Record<string, unknown>>>("schedulers", tab === "schedulers");
  const reviews = useAdminResource<Array<Record<string, unknown>>>("reviews", tab === "reviews");
  const traces = useQuery({
    queryKey: ["admin-trace", orgId, traceId],
    queryFn: () =>
      api.get<{ events: Array<Record<string, unknown>> }>(
        `/api/admin/email-intelligence/traces?correlation_id=${encodeURIComponent(traceId)}`
      ),
    enabled: tab === "traces" && traceId.length > 2,
  });

  if (overview.isLoading) return <LoadingSkeleton variant="grid" />;
  if (overview.isError || !overview.data) {
    return (
      <ErrorState
        title={tx("Không thể tải bảng điều hành", "Unable to load operations")}
        description={tx("Thông tin sức khỏe Email Gateway tạm thời chưa sẵn sàng.", "Admin email intelligence health is unavailable.")}
        onRetry={() => void overview.refetch()}
      />
    );
  }
  const data = overview.data;
  const resource = tab === "queue" ? queue : tab === "schedulers" ? schedulers : reviews;

  const tabLabels: Record<string, string> = {
    overview: tx("Tổng quan", "Overview"),
    queue: tx("Hàng đợi (Queue)", "Queue"),
    schedulers: tx("Bộ lập lịch", "Schedulers"),
    reviews: tx("Phê duyệt", "Reviews"),
    traces: tx("Truy vết (Traces)", "Traces"),
  };

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Activity}
        title={dict.pages.emailGateway.title}
        description={dict.pages.emailGateway.description}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void overview.refetch();
              if (tab !== "overview" && tab !== "traces") void resource.refetch();
              if (tab === "traces" && traceId.length > 2) void traces.refetch();
            }}
            className="gap-2"
          >
            <RefreshCw className="h-4 w-4" />
            {tx("Làm mới", "Refresh")}
          </Button>
        }
      />

      {/* KPI Metrics Ribbon */}
      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
        <Metric
          icon={Database}
          label={tx("Kết nối Mail", "Connections")}
          value={`${data.connections.healthy}/${data.connections.total}`}
          detail={data.connections.unhealthy ? tx(`${data.connections.unhealthy} lỗi kết nối`, `${data.connections.unhealthy} unhealthy`) : tx("Hoạt động tốt", "Healthy")}
          danger={data.connections.unhealthy > 0}
        />
        <Metric
          icon={GitBranch}
          label={tx("Hàng đợi xử lý", "Queue")}
          value={`${data.queue.ready}`}
          detail={tx(`${data.queue.retrying} đang thử lại · ${data.queue.dead_letter} lỗi tồn`, `${data.queue.retrying} retrying · ${data.queue.dead_letter} dead-letter`)}
          danger={data.queue.dead_letter > 0}
        />
        <Metric
          icon={ShieldAlert}
          label={tx("Yêu cầu duyệt", "Reviews")}
          value={`${data.reviews.open}`}
          detail={tx(`${data.reviews.breached} vi phạm SLA`, `${data.reviews.breached} SLA breached`)}
          danger={data.reviews.breached > 0}
        />
        <Metric
          icon={Timer}
          label={tx("Bộ lập lịch", "Scheduler")}
          value={data.scheduler.healthy ? (tx("Hoạt động tốt", "Healthy")) : (tx("Suy giảm", "Degraded"))}
          detail={tx(`${data.scheduler.missed_occurrences} lượt bị trễ`, `${data.scheduler.missed_occurrences} missed occurrences`)}
          danger={!data.scheduler.healthy}
        />
      </div>

      {/* Segmented Navigation Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-border/70 pb-2" role="tablist" aria-label={tx("Các khu vực vận hành quản trị", "Admin operations sections")}>
        {["overview", "queue", "schedulers", "reviews", "traces"].map((value) => (
          <Button
            key={value}
            size="sm"
            variant={tab === value ? "secondary" : "ghost"}
            onClick={() => setTab(value)}
            role="tab"
            aria-selected={tab === value}
            className="font-medium"
          >
            {tabLabels[value]}
          </Button>
        ))}
      </div>

      {/* Tab Content */}
      {tab === "overview" && (
        <Card glass className="border-border/80 shadow-card">
          <CardHeader>
            <CardTitle className="text-base">{tx("Rào chắn Vận hành Doanh nghiệp", "Operational guardrails")}</CardTitle>
            <CardDescription className="text-xs leading-relaxed">
              {tx("Tất cả các hành động quản trị viên đều được kiểm soát nghiêm ngặt theo chính sách RBAC và chỉ đọc trừ khi được cấp quyền.", "Admin actions remain capability-gated and read-only until the corresponding backend policy is enabled.")}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-xs text-muted-foreground leading-relaxed">
            <p>
              {t("pages.emailIntelligence.correlationIdDesc", "Sử dụng Correlation ID để kiểm tra vòng đời xử lý sanitized. Không có payload bảo mật của nhà cung cấp nào bị lộ tại đây.")}
            </p>
          </CardContent>
        </Card>
      )}

      {tab !== "overview" && tab !== "traces" && (
        resource.isLoading ? (
          <LoadingSkeleton variant="table" />
        ) : resource.isError ? (
          <ErrorState
            title={tx("Không thể tải tài nguyên", "Unable to load resource")}
            description={tx("Vui lòng thử lại truy vấn.", "Retry the operation query.")}
            onRetry={() => void resource.refetch()}
          />
        ) : (
          <OperationsTable rows={resource.data || []} locale={locale} />
        )
      )}

      {tab === "traces" && (
        <Card glass className="border-border/80 shadow-card">
          <CardHeader>
            <CardTitle className="text-base">{tx("Truy vết Correlation ID", "Trace Explorer")}</CardTitle>
            <CardDescription className="text-xs">
              {tx("Nhập Correlation ID để tra cứu lịch sử sự kiện xử lý email", "Enter a correlation ID to inspect sanitized events")}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-2 max-w-md">
              <Input
                value={traceId}
                onChange={(event) => setTraceId(event.target.value)}
                placeholder={tx("Nhập Correlation ID...", "Correlation ID...")}
                aria-label="Correlation ID"
                className="text-xs font-mono"
              />
              <Button onClick={() => void traces.refetch()} disabled={traceId.length < 3} className="gap-1.5 font-medium">
                <Search className="h-3.5 w-3.5" />
                {tx("Tìm kiếm", "Search")}
              </Button>
            </div>
            {traces.data?.events?.length ? (
              <OperationsTable rows={traces.data.events} locale={locale} />
            ) : (
              <p className="text-xs text-muted-foreground">
                {tx("Nhập correlation ID hợp lệ để tra cứu luồng sự kiện.", "Enter a correlation ID to inspect sanitized events.")}
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Metric({ icon: Icon, label, value, detail, danger }: { icon: typeof Activity; label: string; value: string; detail: string; danger?: boolean }) {
  return (
    <Card className="shadow-card border-border/80">
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">{label}</span>
          <Icon className={danger ? "h-4 w-4 text-destructive" : "h-4 w-4 text-primary"} aria-hidden="true" />
        </div>
        <div className="mt-2 text-2xl font-bold tabular-nums text-foreground">{value}</div>
        <p className={danger ? "mt-1 text-xs text-destructive" : "mt-1 text-xs text-muted-foreground"}>{detail}</p>
      </CardContent>
    </Card>
  );
}

function OperationsTable({ rows, locale }: { rows: Array<Record<string, unknown>>; locale: string }) {
  const { tx } = useTranslation();
  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(10);

  const paginatedRows = React.useMemo(() => {
    const start = (page - 1) * pageSize;
    return rows.slice(start, start + pageSize);
  }, [rows, page, pageSize]);

  if (!rows.length) {
    return (
      <EmptyState
        icon={Activity}
        title={tx("Không có bản ghi nào cần chú ý", "No operational records require attention")}
        description={tx("Hệ thống đang vận hành bình thường không có cảnh báo.", "System is running smoothly with no active alerts.")}
      />
    );
  }

  return (
    <Card glass className="overflow-hidden shadow-card border-border/80">
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40">
              <TableHead className="text-xs font-semibold">{tx("Tài nguyên / Sự kiện", "Resource")}</TableHead>
              <TableHead className="text-xs font-semibold">{tx("Trạng thái", "Status")}</TableHead>
              <TableHead className="text-xs font-semibold">{tx("Thời gian", "Time")}</TableHead>
              <TableHead className="text-xs font-semibold">{tx("Mức độ rủi ro", "Risk")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {paginatedRows.map((row, index) => (
              <TableRow key={String(row.id || row.event_id || index)} className="hover:bg-muted/20 transition-colors">
                <TableCell className="max-w-xs truncate p-4 font-mono text-xs text-foreground font-medium">
                  {String(row.event_type || row.job_key || row.title || row.id || row.event_id)}
                </TableCell>
                <TableCell className="p-4">
                  <Badge variant={String(row.status || row.sla_status) === "BREACHED" || String(row.status) === "dead_letter" ? "destructive" : "outline"} className="text-[10px]">
                    {String(row.status || row.sla_status || "unknown")}
                  </Badge>
                </TableCell>
                <TableCell className="p-4 text-xs font-mono text-muted-foreground">
                  {String(row.created_at || row.scheduled_for || row.occurred_at || row.opened_at || "—")}
                </TableCell>
                <TableCell className="p-4 text-xs font-mono text-muted-foreground">
                  {String(row.risk_level || row.last_error_code || "—")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <div className="p-3 border-t border-border/60">
          <DataPagination
            page={page}
            pageSize={pageSize}
            totalItems={rows.length}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
            pageSizeOptions={[5, 10, 25, 50]}
          />
        </div>
      </CardContent>
    </Card>
  );
}
