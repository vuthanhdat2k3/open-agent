"use client";

import * as React from "react";
import {
  Activity,
  Bug,
  Coins,
  GitBranch,
  MessageSquare,
  RefreshCw,
  Search,
  Zap,
  BarChart3,
  Bot,
} from "lucide-react";
import {
  useDebugSessions,
  useUsageSummary,
  useSessionTree,
  useTaskTree,
  useWorkflowRun,
  useUrlSearchParam,
} from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState, ErrorState, LoadingSkeleton, DataPagination } from "@/components/shared";
import { useTranslation } from "@/lib/i18n";

export default function DebugPage() {
  const { t, dict, locale } = useTranslation();
  const [tabParam, setTabParam] = useUrlSearchParam("tab");
  const activeTab = (tabParam as "usage" | "sessions" | "tasks") || "usage";

  const sessions = useDebugSessions();
  const usage = useUsageSummary();
  const [selSession, setSelSession] = useUrlSearchParam("session");
  const [rootRunParam, setRootRunParam] = useUrlSearchParam("root_run");
  const [runParam, setRunParam] = useUrlSearchParam("run");
  const [rootRunDraft, setRootRunDraft] = React.useState(rootRunParam ?? "");
  const [workflowRunDraft, setWorkflowRunDraft] = React.useState(runParam ?? "");
  const [usageSearch, setUsageSearch] = React.useState("");

  React.useEffect(() => setRootRunDraft(rootRunParam ?? ""), [rootRunParam]);
  React.useEffect(() => setWorkflowRunDraft(runParam ?? ""), [runParam]);

  const tree = useSessionTree(selSession);
  const taskTree = useTaskTree(rootRunParam || null);
  const workflowRun = useWorkflowRun(runParam || null);

  // Compute aggregated totals
  const totalCost = usage.data?.reduce((acc, curr) => acc + curr.cost_usd, 0) ?? 0;
  const totalCalls = usage.data?.reduce((acc, curr) => acc + curr.calls, 0) ?? 0;
  const totalInputTokens = usage.data?.reduce((acc, curr) => acc + curr.input_tokens, 0) ?? 0;
  const totalOutputTokens = usage.data?.reduce((acc, curr) => acc + curr.output_tokens, 0) ?? 0;
  const totalTokens = totalInputTokens + totalOutputTokens;

  const filteredUsage = React.useMemo(() => {
    if (!usage.data) return [];
    if (!usageSearch.trim()) return usage.data;
    const q = usageSearch.toLowerCase();
    return usage.data.filter(
      (u) =>
        u.agent_name.toLowerCase().includes(q) ||
        u.model_name.toLowerCase().includes(q),
    );
  }, [usage.data, usageSearch]);

  const [usagePage, setUsagePage] = React.useState(1);
  const [usagePageSize, setUsagePageSize] = React.useState(10);
  React.useEffect(() => {
    setUsagePage(1);
  }, [usageSearch]);
  const paginatedUsage = React.useMemo(() => {
    const start = (usagePage - 1) * usagePageSize;
    return filteredUsage.slice(start, start + usagePageSize);
  }, [filteredUsage, usagePage, usagePageSize]);

  const [sessionPage, setSessionPage] = React.useState(1);
  const [sessionPageSize, setSessionPageSize] = React.useState(8);
  const paginatedSessions = React.useMemo(() => {
    const start = (sessionPage - 1) * sessionPageSize;
    return (sessions.data ?? []).slice(start, start + sessionPageSize);
  }, [sessions.data, sessionPage, sessionPageSize]);

  return (
    <div className="space-y-6">
      {/* 1. Page Header */}
      <PageHeader
        icon={Bug}
        title={dict.pages.debug.title}
        description={dict.pages.debug.description}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void usage.refetch();
              void sessions.refetch();
              if (selSession) void tree.refetch();
              if (rootRunParam) void taskTree.refetch();
            }}
            disabled={usage.isFetching || sessions.isFetching}
            className="gap-1.5"
          >
            <RefreshCw className={usage.isFetching || sessions.isFetching ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
            {locale === "vi" ? "Làm mới" : "Refresh"}
          </Button>
        }
      />

      {/* 2. Executive Analytics Metric Ribbon */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-500/10 text-emerald-500">
            <Coins className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">
              ${totalCost.toFixed(4)}
            </p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">
              {locale === "vi" ? "Chi phí LLM (USD)" : "Total LLM Spend (USD)"}
            </p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <Activity className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">
              {totalCalls.toLocaleString()}
            </p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">
              {locale === "vi" ? "Lượt gọi AI" : "Total AI Invocations"}
            </p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sky-500/10 text-sky-500">
            <Zap className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">
              {totalTokens > 1_000_000
                ? `${(totalTokens / 1_000_000).toFixed(2)}M`
                : `${(totalTokens / 1_000).toFixed(1)}k`}
            </p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">
              {locale === "vi" ? "Tokens tiêu thụ" : "Tokens Burned"}
            </p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-500/10 text-amber-500">
            <MessageSquare className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">
              {sessions.data?.length ?? 0}
            </p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">
              {locale === "vi" ? "Phiên hội thoại" : "Recorded Sessions"}
            </p>
          </div>
        </Card>
      </div>

      {/* 3. Segmented Navigation Tabs */}
      <div className="flex gap-2 border-b border-border/70 pb-2">
        <Button
          type="button"
          variant={activeTab === "usage" ? "secondary" : "ghost"}
          onClick={() => setTabParam("usage")}
          className="gap-2 font-medium"
        >
          <BarChart3 className="h-4 w-4 text-primary" />
          {locale === "vi" ? "Phân tích Chi phí" : "Cost Analytics"}
        </Button>

        <Button
          type="button"
          variant={activeTab === "sessions" ? "secondary" : "ghost"}
          onClick={() => setTabParam("sessions")}
          className="gap-2 font-medium"
        >
          <MessageSquare className="h-4 w-4 text-primary" />
          {locale === "vi" ? "Lịch sử Phiên" : "Session Audit"}
        </Button>

        <Button
          type="button"
          variant={activeTab === "tasks" ? "secondary" : "ghost"}
          onClick={() => setTabParam("tasks")}
          className="gap-2 font-medium"
        >
          <GitBranch className="h-4 w-4 text-primary" />
          {locale === "vi" ? "Cây Tác vụ" : "Task Graph"}
        </Button>
      </div>

      {/* 4. Tab 1: Cost & Token Analytics */}
      {activeTab === "usage" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div className="relative flex-1 max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={usageSearch}
                onChange={(e) => setUsageSearch(e.target.value)}
                placeholder={locale === "vi" ? "Lọc theo agent hoặc model..." : "Filter by agent or model..."}
                className="pl-9 text-xs"
              />
            </div>
            <p className="text-xs text-muted-foreground font-mono">
              {locale === "vi" ? `Hiển thị ${filteredUsage.length} bản ghi chi tiết` : `Showing ${filteredUsage.length} breakdown records`}
            </p>
          </div>

          <Card className="shadow-card border-border/80 overflow-hidden">
            {usage.isLoading ? (
              <LoadingSkeleton variant="table" />
            ) : usage.isError ? (
              <ErrorState
                title={locale === "vi" ? "Không thể tải phân tích chi phí" : "Unable to load usage analytics"}
                description={locale === "vi" ? "Dữ liệu đo lường chi phí chưa sẵn sàng." : "Usage telemetry data could not be retrieved."}
                onRetry={() => void usage.refetch()}
              />
            ) : filteredUsage.length ? (
              <div>
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40">
                      <TableHead className="text-xs font-semibold">{locale === "vi" ? "Tên Agent" : "Agent Name"}</TableHead>
                      <TableHead className="text-xs font-semibold">{locale === "vi" ? "Mô hình" : "Model Provider"}</TableHead>
                      <TableHead className="text-right text-xs font-semibold">{locale === "vi" ? "Lượt gọi" : "Calls"}</TableHead>
                      <TableHead className="text-right text-xs font-semibold">{locale === "vi" ? "Tokens Đầu vào" : "Prompt In"}</TableHead>
                      <TableHead className="text-right text-xs font-semibold">{locale === "vi" ? "Tokens Đầu ra" : "Completion Out"}</TableHead>
                      <TableHead className="text-right text-xs font-semibold">{locale === "vi" ? "Tổng Chi phí" : "Total Cost"}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedUsage.map((u, i) => (
                      <TableRow key={i} className="hover:bg-muted/20 transition-colors">
                        <TableCell className="font-medium text-xs text-foreground flex items-center gap-2">
                          <Bot className="h-3.5 w-3.5 text-primary shrink-0" />
                          {u.agent_name}
                        </TableCell>
                        <TableCell className="text-muted-foreground text-xs font-mono">
                          <Badge variant="outline" className="font-mono text-[10px]">
                            {u.model_name}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right tabular-nums text-xs font-mono">
                          {u.calls.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right tabular-nums font-mono text-xs text-muted-foreground">
                          {u.input_tokens.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right tabular-nums font-mono text-xs text-muted-foreground">
                          {u.output_tokens.toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right tabular-nums font-mono text-xs font-semibold text-emerald-500">
                          ${u.cost_usd.toFixed(6)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <div className="p-3 border-t border-border/60">
                  <DataPagination
                    page={usagePage}
                    pageSize={usagePageSize}
                    totalItems={filteredUsage.length}
                    onPageChange={setUsagePage}
                    onPageSizeChange={setUsagePageSize}
                    pageSizeOptions={[5, 10, 25, 50]}
                  />
                </div>
              </div>
            ) : (
              <EmptyState
                icon={BarChart3}
                title={locale === "vi" ? "Không tìm thấy dữ liệu tiêu thụ" : "No usage data found"}
                description={locale === "vi" ? "Thực hiện các cuộc trò chuyện AI để xem phân tích chi phí." : "Perform AI interactions to inspect token telemetry."}
              />
            )}
          </Card>
        </div>
      )}

      {/* 5. Tab 2: Session Audit & Message Traces */}
      {activeTab === "sessions" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Left Column: Session Selector */}
          <Card className="shadow-card border-border/80 lg:col-span-1 flex flex-col">
            <CardHeader className="border-b border-border/60 pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-primary" /> {locale === "vi" ? "Chọn Phiên kiểm toán" : "Select Audit Session"}
              </CardTitle>
              <CardDescription className="text-xs">
                {locale === "vi"
                  ? "Kiểm tra raw prompt messages và tool calls của từng hội thoại."
                  : "Inspect raw prompt messages and tool calls for any chat conversation."}
              </CardDescription>
            </CardHeader>
            <CardContent className="p-3 flex-1 flex flex-col justify-between">
              {sessions.isLoading ? (
                <LoadingSkeleton variant="table" />
              ) : sessions.isError ? (
                <ErrorState
                  title={locale === "vi" ? "Không thể tải danh sách phiên" : "Unable to load sessions"}
                  description={locale === "vi" ? "Danh sách phiên chưa sẵn sàng." : "Session list could not be loaded."}
                  onRetry={() => void sessions.refetch()}
                />
              ) : sessions.data?.length ? (
                <div className="space-y-3">
                  <div className="space-y-1.5 max-h-[50vh] overflow-y-auto pr-1">
                    {paginatedSessions.map((s) => {
                      const isSelected = selSession === s.id;
                      return (
                        <button
                          key={s.id}
                          type="button"
                          onClick={() => setSelSession(s.id)}
                          className={`w-full text-left rounded-lg p-3 transition-all flex flex-col gap-1 border ${
                            isSelected
                              ? "border-primary bg-primary/10 text-foreground shadow-sm"
                              : "border-border/60 hover:bg-muted/40 text-muted-foreground"
                          }`}
                        >
                          <p className={`text-xs font-semibold truncate ${isSelected ? "text-primary" : "text-foreground"}`}>
                            {s.title || (locale === "vi" ? "Hội thoại không tên" : "Untitled Conversation")}
                          </p>
                          <p className="font-mono text-[10px] text-muted-foreground truncate">
                            {locale === "vi" ? "ID:" : "ID:"}{s.id}
                          </p>
                        </button>
                      );
                    })}
                  </div>
                  <DataPagination
                    page={sessionPage}
                    pageSize={sessionPageSize}
                    totalItems={sessions.data.length}
                    onPageChange={setSessionPage}
                    onPageSizeChange={setSessionPageSize}
                    pageSizeOptions={[5, 10, 20]}
                    compact
                  />
                </div>
              ) : (
                <EmptyState
                  icon={MessageSquare}
                  title={locale === "vi" ? "Không có phiên nào được ghi lại" : "No recorded sessions"}
                />
              )}
            </CardContent>
          </Card>

          {/* Right Column: Message Stream Inspection */}
          <Card className="shadow-card border-border/80 lg:col-span-2 flex flex-col">
            <CardHeader className="border-b border-border/60 pb-3">
              <CardTitle className="text-sm font-semibold flex items-center justify-between">
                <span>{locale === "vi" ? "Luồng Tin nhắn & Truy vết Thực thi" : "Message Stream & Execution Trace"}</span>
                {tree.data && (
                  <Badge variant="outline" className="font-mono text-[10px]">
                    {tree.data.messages.length} {locale === "vi" ? "tin nhắn" : "messages"}
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 flex-1">
              {!selSession ? (
                <div className="py-16 text-center text-xs text-muted-foreground">
                  {locale === "vi"
                    ? "Chọn một phiên hội thoại từ danh sách bên trái để kiểm tra chi tiết."
                    : "Select a session from the list on the left to inspect its messages."}
                </div>
              ) : tree.isLoading ? (
                <LoadingSkeleton variant="table" />
              ) : tree.isError ? (
                <ErrorState
                  title={locale === "vi" ? "Không thể tải truy vết phiên" : "Unable to load session trace"}
                  description={locale === "vi" ? "Phiên được chọn không thể kiểm tra." : "Selected session could not be inspected."}
                  onRetry={() => void tree.refetch()}
                />
              ) : tree.data?.messages.length ? (
                <div className="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
                  {tree.data.messages.map((m: any) => (
                    <div
                      key={m.id}
                      className="rounded-xl border border-border/80 bg-card p-4 text-xs shadow-card space-y-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <Badge
                          variant={m.role === "user" ? "default" : "outline"}
                          className="text-[10px] uppercase font-mono"
                        >
                          {m.role}
                        </Badge>
                        {m.meta?.cost_usd != null && (
                          <span className="font-mono text-[10.5px] text-muted-foreground bg-muted/40 px-2 py-0.5 rounded border border-border/40">
                            ${Number(m.meta.cost_usd).toFixed(6)} · {m.meta.latency_ms || 0}{locale === "vi" ? "ms" : "ms"}</span>
                        )}
                      </div>

                      <div className="whitespace-pre-wrap leading-relaxed select-text font-sans text-foreground">
                        {m.content}
                      </div>

                      {m.meta?.tools?.length > 0 && (
                        <div className="mt-2.5 pt-2 border-t border-border/50 text-[11px] text-muted-foreground flex flex-wrap items-center gap-1.5">
                          <span className="font-semibold text-foreground">{locale === "vi" ? "Công cụ đã gọi:" : "Tools Dispatched:"}</span>
                          {m.meta.tools.map((t: any, idx: number) => (
                            <Badge key={idx} variant="outline" className="font-mono text-[10px] bg-primary/5 text-primary border-primary/30">
                              {t.name}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={MessageSquare}
                  title={locale === "vi" ? "Không có tin nhắn nào trong phiên" : "No messages in session"}
                />
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* 6. Tab 3: Task Graph & Execution Tree */}
      {activeTab === "tasks" && (
        <div className="space-y-4">
          <Card className="shadow-card border-border/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold">
                {locale === "vi" ? "Kiểm tra Cây Thực thi Tác vụ" : "Inspect Task Execution Tree"}
              </CardTitle>
              <CardDescription className="text-xs">
                {locale === "vi"
                  ? "Nhập ID lượt chạy gốc (root run ID) để xem cây phân cấp subagent và trạng thái phụ thuộc."
                  : "Enter a root run ID to inspect hierarchical subagent execution trees and dependency statuses."}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3 max-w-xl">
                <Input
                  id="debug-root-run"
                  name="root_run_id"
                  value={rootRunDraft}
                  onChange={(e) => setRootRunDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") setRootRunParam(rootRunDraft.trim() || null);
                  }}
                  placeholder={locale === "vi" ? "Nhập root_run_id (ví dụ: run-98a72...)" : "Enter root_run_id (e.g. run-98a72...)"}
                  className="font-mono text-xs"
                />
                <Button
                  size="sm"
                  onClick={() => setRootRunParam(rootRunDraft.trim() || null)}
                  className="font-semibold text-xs"
                >
                  {locale === "vi" ? "Kiểm tra" : "Inspect Run"}
                </Button>
              </div>
            </CardContent>
          </Card>

          {taskTree.isLoading ? (
            <LoadingSkeleton variant="table" />
          ) : taskTree.isError ? (
            <ErrorState
              title={locale === "vi" ? "Không thể tải cây tác vụ" : "Unable to load task tree"}
              description={locale === "vi" ? "Cây tác vụ không khả dụng." : "Task graph could not be retrieved."}
              onRetry={() => void taskTree.refetch()}
            />
          ) : taskTree.data?.tasks?.length ? (
            <div className="space-y-3">
              {taskTree.data.tasks.map((node) => (
                <Card key={node.id} className="shadow-card border-border/80 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <GitBranch className="h-4 w-4 text-primary" />
                      <span className="font-semibold text-sm text-foreground">{node.goal}</span>
                    </div>
                    <Badge variant={node.status === "completed" ? "default" : "outline"} className="text-[10px] font-mono uppercase">
                      {node.status}
                    </Badge>
                  </div>
                  <div className="mt-2 text-xs font-mono text-muted-foreground flex items-center gap-4">
                    <span>{locale === "vi" ? "Task ID:" : "Task ID:"}{node.id}</span>
                    <span>{locale === "vi" ? "Tác vụ cha:" : "Parent:"} {node.parent_task_id || "Root"}</span>
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={GitBranch}
              title={locale === "vi" ? "Chưa tải cây tác vụ nào" : "No task tree loaded"}
              description={locale === "vi" ? "Cung cấp root run ID đang chạy hoặc đã hoàn tất để hiển thị biểu đồ." : "Provide an active or completed root run ID to visualize its execution graph."}
            />
          )}
        </div>
      )}
    </div>
  );
}
