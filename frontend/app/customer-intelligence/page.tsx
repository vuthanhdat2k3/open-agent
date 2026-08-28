"use client";

import React, { useState, useEffect, useDeferredValue } from "react";
import ReactMarkdown from "react-markdown";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Building2,
  Calendar,
  ChevronDown,
  ChevronRight,
  Clock,
  Clock3,
  Download,
  ExternalLink,
  FileCheck2,
  FileText,
  Flame,
  Globe,
  Layers,
  LayoutGrid,
  List,
  Mail,
  Newspaper,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Share2,
  Sparkles,
  Trash2,
  TrendingUp,
  UserCheck,
  Users,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/page-header";
import { DataPagination } from "@/components/shared";
import { useTranslation } from "@/lib/i18n";
import { getAccessToken } from "@/lib/auth";
import { formatVietnamDateTime } from "@/lib/datetime";
import {
  useCiConnections,
  useCiSchedules,
  useCreateCiSchedule,
  useCreateManualCustomerIntelligenceCase,
  useCustomerIntelligenceCase,
  useCustomerIntelligenceCases,
  useDeleteCiSchedule,
  useDeleteCustomerIntelligenceCase,
  useResearchCustomerIntelligenceCase,
  useRetryCustomerIntelligenceCase,
  useRunCiScheduleNow,
  useUpdateCiSchedule,
  useUrlSearchParam,
} from "@/hooks";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { toast } from "sonner";
import type { CustomerIntelligenceSchedule, CustomerIntelligenceCase } from "@/types";

async function downloadCiReport(caseId: string, format: "html" | "pdf" | "docx") {
  const token = getAccessToken();
  const res = await fetch(`/api/customer-intelligence/cases/${caseId}/report/${format}`, {
    credentials: "include",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new Error(`download failed: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `dossier-${caseId}.${format}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function statusBadgeInfo(status: string, locale: string) {
  const s = (status || "").toUpperCase();
  const vi = locale === "vi";
  if (["COMPLETED", "REPORT_READY"].includes(s)) {
    return { label: vi ? "Bản tóm tắt sẵn sàng" : "Briefing Ready", variant: "default" as const, color: "text-emerald-500 border-emerald-500/30 bg-emerald-500/10" };
  }
  if (["RESEARCHING", "EXECUTING", "INGESTED"].includes(s)) {
    return { label: vi ? "Đang nghiên cứu" : "Researching", variant: "outline" as const, color: "text-sky-500 border-sky-500/30 bg-sky-500/10" };
  }
  if (["NEEDS_REVIEW", "RETRYING", "DEAD_LETTER", "REJECTED"].includes(s)) {
    return { label: vi ? "Cần hành động" : "Action Needed", variant: "destructive" as const, color: "text-amber-500 border-amber-500/30 bg-amber-500/10" };
  }
  return { label: status, variant: "outline" as const, color: "text-muted-foreground border-border bg-muted/40" };
}

function DetailedDossierView({
  report,
  sources,
  meetings,
  companyName,
  companyDomain,
}: {
  report: NonNullable<NonNullable<import("@/types").CustomerIntelligenceCaseDetail>["report"]>;
  sources: import("@/types").CustomerIntelligenceSource[];
  meetings: import("@/types").CustomerIntelligenceMeeting[];
  companyName?: string | null;
  companyDomain?: string | null;
}) {
    const { locale, tx } = useTranslation();
  const data = report.rendering;

  if (!data || !("executive_summary" in data)) {
    return (
      <article className="prose prose-sm max-w-none rounded-xl border border-border/80 bg-card p-6 shadow-sm dark:prose-invert">
        <ReactMarkdown>{report.canonical_markdown}</ReactMarkdown>
      </article>
    );
  }

  const companies = Array.isArray(data.company_overview) ? data.company_overview : [];
  const news = Array.isArray(data.recent_news) ? data.recent_news : [];
  const contacts = Array.isArray(data.contact_information) ? data.contact_information : [];
  const questions = Array.isArray(data.open_questions) ? data.open_questions : [];
  const reportMeetings = Array.isArray(data.upcoming_meetings) && data.upcoming_meetings.length ? data.upcoming_meetings : meetings;
  const reportSources = Array.isArray(data.sources) && data.sources.length ? data.sources : sources;

  return (
    <div className="space-y-6">
      {/* 1. Executive Summary Hero Box */}
      {data.executive_summary && (
        <section className="rounded-xl border border-primary/25 bg-gradient-to-br from-primary/[0.07] via-card to-background p-5 shadow-card">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold uppercase tracking-wider text-primary">
              {tx("Tóm tắt thông báo điều hành", "Executive Briefing Summary")}</h3>
          </div>
          <p className="text-sm leading-relaxed text-foreground whitespace-pre-wrap font-sans font-medium">
            {data.executive_summary}
          </p>
        </section>
      )}

      {/* 2. Upcoming Meetings Context */}
      {reportMeetings.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <Calendar className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">{tx("Lịch họp sắp tới", "Upcoming Meeting Schedule")}</h3>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {reportMeetings.map((m: any, idx: number) => (
              <Card key={idx} className="p-4 border-border/80 bg-card/60 shadow-sm">
                <p className="font-semibold text-sm text-foreground">{m.title || tx("Thảo luận chiến lược khách hàng", "Client Strategy Discussion")}</p>
                <div className="mt-2 space-y-1 text-xs text-muted-foreground font-mono">
                  {m.start_time && (
                    <p className="flex items-center gap-1.5 text-primary">
                      <Clock className="h-3.5 w-3.5" />
                      {formatVietnamDateTime(m.start_time)}
                    </p>
                  )}
                  {m.organizer && <p className="truncate">{tx("Người tổ chức:", "Organizer:")}{m.organizer}</p>}
                </div>
                {m.participants?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {m.participants.slice(0, 3).map((p: string, pIdx: number) => (
                      <Badge key={pIdx} variant="outline" className="text-[10px] truncate max-w-[140px]">
                        {p}
                      </Badge>
                    ))}
                    {m.participants.length > 3 && (
                      <Badge variant="outline" className="text-[10px]">
                        +{m.participants.length - 3}
                      </Badge>
                    )}
                  </div>
                )}
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* 3. Company Overview & Industry Highlights */}
      {companies.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <Building2 className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">{tx("Thông tin doanh nghiệp", "Company Intelligence")}</h3>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {companies.map((c, idx) => (
              <Card key={idx} className="p-4 border-border/80 bg-card/60 shadow-sm">
                <p className="font-semibold text-sm text-foreground">{c.name || companyName || tx("Hồ sơ tổ chức", "Organization Profile")}</p>
                <p className="mt-1 text-xs text-muted-foreground leading-relaxed font-sans">{c.summary}</p>
                {c.industry && (
                  <Badge variant="outline" className="mt-2.5 text-[10px] font-mono">
                    {c.industry}
                  </Badge>
                )}
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* 4. Recent Market News & Strategic Signals */}
      {news.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <Newspaper className="h-4 w-4 text-sky-500" />
            <h3 className="text-sm font-semibold text-foreground">{tx("Tin tức thị trường & tín hiệu công khai gần đây", "Recent Market News & Public Signals")}</h3>
          </div>
          <div className="space-y-2.5">
            {news.map((item, idx) => (
              <Card key={idx} className="p-3.5 border-border/80 bg-card/60 hover:border-primary/40 transition-colors shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <a
                      href={item.url || "#"}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs font-semibold text-foreground hover:text-primary transition-colors flex items-center gap-1.5"
                    >
                      {item.headline || item.title || tx("Cập nhật thông tin thị trường", "Market Intelligence Update")}
                      {item.url && <ExternalLink className="h-3 w-3 text-muted-foreground shrink-0" />}
                    </a>
                    {item.summary && (
                      <p className="mt-1 text-xs text-muted-foreground leading-relaxed font-sans">{item.summary}</p>
                    )}
                  </div>
                  {item.published_at && (
                    <span className="shrink-0 text-[10px] font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                      {item.published_at}
                    </span>
                  )}
                </div>
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* 5. Key Stakeholders & Verified Contacts */}
      {contacts.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4 text-emerald-500" />
            <h3 className="text-sm font-semibold text-foreground">{tx("Bên liên quan & liên hệ chính", "Key Stakeholders & Contacts")}</h3>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {contacts.map((contact, idx) => (
              <Card key={idx} className="p-3.5 border-border/80 bg-card/60 shadow-sm">
                <p className="font-semibold text-xs text-foreground">{contact.name}</p>
                {contact.role && <p className="text-[11px] text-primary font-medium">{contact.role}</p>}
                {contact.email && (
                  <p className="mt-1.5 text-[11px] font-mono text-muted-foreground truncate">{contact.email}</p>
                )}
                {contact.notes && <p className="mt-1 text-[11px] text-muted-foreground line-clamp-2">{contact.notes}</p>}
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* 6. Deal Risks & Open Discovery Questions */}
      {questions.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            <h3 className="text-sm font-semibold text-foreground">{tx("Câu hỏi thăm dò & rủi ro thỏa thuận", "Discovery Questions & Deal Risks")}</h3>
          </div>
          <Card className="border-amber-500/30 bg-amber-500/[0.03] p-4 shadow-sm">
            <ul className="space-y-2 text-xs text-muted-foreground">
              {questions.map((q, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="font-mono text-amber-500 font-bold shrink-0">{idx + 1}.</span>
                  <span className="text-foreground/90 font-medium leading-relaxed">{q}</span>
                </li>
              ))}
            </ul>
          </Card>
        </section>
      )}

      {/* 7. Verified Sources & Web Citations */}
      {reportSources.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <Globe className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold text-foreground">{tx("Trích dẫn có kiểm chứng", "Verified Grounded Citations")}</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {reportSources.map((s, idx) => (
              <a
                key={idx}
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-border/80 bg-muted/30 px-2.5 py-1 text-xs text-muted-foreground hover:border-primary/40 hover:text-foreground transition-colors"
              >
                <span className="font-medium truncate max-w-[200px]">{s.title || s.url}</span>
                <ExternalLink className="h-3 w-3 shrink-0 opacity-60" />
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

const SCHEDULE_TIMEZONES = [
  "Asia/Ho_Chi_Minh",
  "Asia/Singapore",
  "Asia/Bangkok",
  "Asia/Tokyo",
  "UTC",
  "America/New_York",
  "America/Los_Angeles",
  "Europe/London",
];

function SchedulesTabContent() {
    const { locale, tx } = useTranslation();
  const connections = useCiConnections();
  const schedules = useCiSchedules();
  const create = useCreateCiSchedule();
  const update = useUpdateCiSchedule();
  const remove = useDeleteCiSchedule();
  const runNow = useRunCiScheduleNow();

  const [editing, setEditing] = useState<CustomerIntelligenceSchedule | null>(null);
  const [connectionId, setConnectionId] = useState("");
  const [runTime, setRunTime] = useState("06:30");
  const [timezone, setTimezone] = useState("Asia/Ho_Chi_Minh");
  const [enabled, setEnabled] = useState(true);

  const connected = connections.data?.filter((c) => c.status === "connected") || [];

  useEffect(() => {
    if (editing) {
      setConnectionId(editing.connection_id);
      setRunTime(editing.run_time);
      setTimezone(editing.timezone);
      setEnabled(editing.enabled);
    } else {
      setConnectionId(connected[0]?.id || "");
      setRunTime("06:30");
      setTimezone("Asia/Ho_Chi_Minh");
      setEnabled(true);
    }
  }, [editing, connected.length]);

  async function submitSchedule(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!connectionId) return;
    try {
      if (editing) {
        await update.mutateAsync({
          id: editing.id,
          body: {
            run_time: runTime,
            timezone,
            enabled,
          },
        });
        toast.success(tx("Đã cập nhật lịch đồng bộ", "Schedule updated successfully"));
        setEditing(null);
      } else {
        await create.mutateAsync({
          connection_id: connectionId,
          run_time: runTime,
          timezone,
          enabled,
        });
        toast.success(tx("Đã tạo lịch đồng bộ", "Schedule created successfully"));
      }
    } catch (err: any) {
      toast.error(err.message || tx("Không thể lưu lịch đồng bộ", "Failed to save schedule"));
    }
  }

  async function deleteSchedule(id: string) {
    if (!window.confirm(tx("Bạn có chắc chắn muốn xóa lịch đồng bộ này?", "Are you sure you want to delete this schedule?"))) return;
    try {
      await remove.mutateAsync(id);
      toast.success(tx("Đã xóa lịch đồng bộ", "Schedule removed"));
    } catch (err: any) {
      toast.error(err.message || tx("Không thể xóa lịch đồng bộ", "Failed to remove schedule"));
    }
  }

  async function runSchedule(id: string) {
    try {
      await runNow.mutateAsync(id);
      toast.success(tx("Đã kích hoạt thực thi trong nền", "Schedule execution triggered in background"));
    } catch (err: any) {
      toast.error(err.message || tx("Không thể kích hoạt lịch đồng bộ", "Failed to trigger schedule"));
    }
  }

  const saving = create.isPending || update.isPending;

  function connectionLabel(connId: string) {
    const found = connections.data?.find((c) => c.id === connId);
    return found ? `${found.account_email} (${found.provider})` : connId;
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="shadow-card">
          <CardHeader>
            <CardTitle className="text-base font-semibold text-foreground">
              {editing ? tx("Sửa lịch đồng bộ", "Edit Schedule") : tx("Thiết lập đồng bộ hàng ngày mới", "New Daily Sync Routine")}
            </CardTitle>
            <CardDescription className="text-xs">
              {tx("Cấu hình quét nền tự động hàng ngày cho lời mời lịch và email.", "Configure daily automatic background scan of calendar invites and emails.")}</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submitSchedule} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="ci-schedule-conn" className="text-xs font-medium">{tx("Kết nối Mail / Lịch", "Mail / Calendar Connection")}</Label>
                <Select
                  id="ci-schedule-conn"
                  value={connectionId}
                  onChange={(event) => setConnectionId(event.target.value)}
                  disabled={Boolean(editing)}
                >
                  {connected.map((item) => (
                    <option key={item.id} value={item.id}>{item.account_email}</option>
                  ))}
                </Select>
                {!connected.length && (
                  <p className="text-xs text-muted-foreground">{tx("Không tìm thấy tài khoản Gmail nào đã kết nối. Hãy kết nối trong Tích hợp trước.", "No connected Gmail accounts found. Connect one in Integrations first.")}</p>
                )}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="ci-schedule-time" className="text-xs font-medium">{tx("Thời gian chạy", "Run Time")}</Label>
                  <Input id="ci-schedule-time" type="time" value={runTime} onChange={(event) => setRunTime(event.target.value)} required />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="ci-schedule-timezone" className="text-xs font-medium">{tx("Múi giờ", "Timezone")}</Label>
                  <Select id="ci-schedule-timezone" value={timezone} onChange={(event) => setTimezone(event.target.value)}>
                    {SCHEDULE_TIMEZONES.map((item) => (
                      <option key={item} value={item}>{item}</option>
                    ))}
                  </Select>
                </div>
              </div>
              <label className="flex items-center gap-2 text-xs font-medium text-foreground cursor-pointer">
                <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} className="h-4 w-4 rounded border-border text-primary focus:ring-primary" />
                {tx("Bật", "Enabled")}</label>
              <Button type="submit" loading={saving} disabled={!editing && !connected.length} className="w-full sm:w-auto font-semibold">
                <Plus className="mr-1 h-4 w-4" />
                {editing ? tx("Lưu thay đổi", "Save Changes") : tx("Tạo lịch đồng bộ", "Create Schedule")}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card className="shadow-card">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base font-semibold text-foreground">{tx("Lịch đã cấu hình", "Configured Schedules")}</CardTitle>
                <CardDescription className="text-xs">
                  {schedules.data?.length ?? 0} {tx("lịch đồng bộ thường lệ đang hoạt động", "active routine sync schedules")}</CardDescription>
              </div>
              <Button variant="ghost" size="sm" onClick={() => void schedules.refetch()} disabled={schedules.isFetching}>
                <RefreshCw className={schedules.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {schedules.isLoading && <p className="text-xs text-muted-foreground">{tx("Đang tải lịch...", "Loading schedules...")}</p>}
            {schedules.data?.map((schedule) => (
              <div key={schedule.id} className="rounded-xl border border-border/80 bg-card p-4 transition-colors hover:border-primary/40">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Clock3 className="h-4 w-4 text-primary" />
                      <span className="font-semibold text-sm text-foreground">{tx("Hàng ngày lúc", "Daily at")}{schedule.run_time}</span>
                      <Badge variant={schedule.enabled ? "default" : "outline"} className="text-[9.5px]">
                        {schedule.enabled ? "Active" : "Paused"}
                      </Badge>
                    </div>
                    <p className="mt-1 truncate text-xs text-muted-foreground">
                      {connectionLabel(schedule.connection_id)} · {schedule.timezone}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button variant="ghost" size="sm" onClick={() => setEditing(schedule)}>
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => void deleteSchedule(schedule.id)} disabled={remove.isPending}>
                      <Trash2 className="h-3.5 w-3.5 text-destructive" />
                    </Button>
                  </div>
                </div>
                <div className="mt-3 flex items-center justify-between border-t border-border/50 pt-2 text-[11px] text-muted-foreground">
                  <span>{tx("Chạy lần cuối:", "Last run:")}{schedule.last_run_at ? formatVietnamDateTime(schedule.last_run_at) : "Not run yet"}</span>
                  <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => void runSchedule(schedule.id)} loading={runNow.isPending}>
                    <Play className="mr-1 h-3 w-3" /> {tx("Chạy ngay", "Run Now")}</Button>
                </div>
              </div>
            ))}
            {!schedules.isLoading && !schedules.data?.length && (
              <div className="rounded-xl border border-dashed border-border p-8 text-center">
                <Clock3 className="mx-auto h-8 w-8 text-muted-foreground" />
                <p className="mt-2 text-sm font-semibold text-foreground">{tx("Chưa có lịch đồng bộ", "No sync schedules yet")}</p>
                <p className="mt-1 text-xs text-muted-foreground">{tx("Tạo lịch để tự động đồng bộ email khách hàng và tạo hồ sơ.", "Create one to automatically sync client emails and generate dossiers.")}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

type BusinessFilter = "action_required" | "pre_meeting" | "ready" | "all";

export default function CustomerIntelligencePage() {
  const { t, dict, locale, tx } = useTranslation();
  const [selected, setSelected] = useUrlSearchParam("case");
  const [query, setQuery] = useState("");
  const [businessFilter, setBusinessFilter] = useState<BusinessFilter>("all");
  const [viewMode, setViewMode] = useState<"compact" | "card">("compact");
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({
    earlier: false,
  });
  const [offset, setOffset] = useState(0);
  const deferredQuery = useDeferredValue(query);
  const pageSize = 50;

  const cases = useCustomerIntelligenceCases({
    category: businessFilter === "action_required" ? "review" : "briefings",
    query: deferredQuery,
    limit: pageSize,
    offset,
  });

  const schedules = useCiSchedules();
  const detail = useCustomerIntelligenceCase(selected);
  const research = useResearchCustomerIntelligenceCase();
  const retry = useRetryCustomerIntelligenceCase();
  const remove = useDeleteCustomerIntelligenceCase();
  const manual = useCreateManualCustomerIntelligenceCase();

  const [activeTab, setActiveTab] = useState<"cases" | "schedules">("cases");
  const [isNewModalOpen, setIsNewModalOpen] = useState(false);
  const [companyName, setCompanyName] = useState("");
  const [companyDomain, setCompanyDomain] = useState("");
  const [casePage, setCasePage] = useState(1);
  const [casePageSize, setCasePageSize] = useState(8);
  const [question, setQuestion] = useState("");

  useEffect(() => {
    setOffset(0);
    setCasePage(1);
  }, [deferredQuery, businessFilter]);

  // Filter cases based on business role
  const displayCases = React.useMemo(() => {
    const raw = cases.data || [];
    if (businessFilter === "ready") {
      return raw.filter((c) => ["COMPLETED", "REPORT_READY"].includes((c.status || "").toUpperCase()));
    }
    if (businessFilter === "pre_meeting") {
      return raw.filter((c) => c.trigger === "calendar" || c.status === "COMPLETED");
    }
    if (businessFilter === "action_required") {
      return raw.filter((c) => ["NEEDS_REVIEW", "RETRYING", "DEAD_LETTER", "REJECTED"].includes((c.status || "").toUpperCase()));
    }
    return raw;
  }, [cases.data, businessFilter]);

  // Group cases into Smart Timeline Buckets
  const timelineBuckets = React.useMemo(() => {
    const now = Date.now();
    const oneDay = 24 * 60 * 60 * 1000;
    const sevenDays = 7 * oneDay;

    const todayList: CustomerIntelligenceCase[] = [];
    const thisWeekList: CustomerIntelligenceCase[] = [];
    const earlierList: CustomerIntelligenceCase[] = [];

    displayCases.forEach((c) => {
      const itemTime = new Date(c.created_at).getTime();
      const diff = now - itemTime;
      if (diff <= oneDay || c.trigger === "calendar") {
        todayList.push(c);
      } else if (diff <= sevenDays) {
        thisWeekList.push(c);
      } else {
        earlierList.push(c);
      }
    });

    return {
      today: todayList,
      thisWeek: thisWeekList,
      earlier: earlierList,
    };
  }, [displayCases]);

  const toggleSection = (section: string) => {
    setCollapsedSections((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  async function createManualCase(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!companyName.trim()) return;
    try {
      await manual.mutateAsync({
        company_name: companyName.trim(),
        ...(companyDomain.trim() ? { company_domain: companyDomain.trim() } : {}),
        ...(question.trim() ? { question: question.trim() } : {}),
      });
      toast.success(tx(`Đã kích hoạt nghiên cứu "${companyName.trim()}"`, `Research initiated for "${companyName.trim()}"`));
      setCompanyName("");
      setCompanyDomain("");
      setQuestion("");
      setIsNewModalOpen(false);
    } catch (err: any) {
      toast.error(err.message || tx("Không thể tạo hồ sơ doanh nghiệp", "Failed to create dossier"));
    }
  }

  async function deleteSelectedCase() {
    if (!selected || !window.confirm(tx("Xóa hồ sơ doanh nghiệp này? Email nguồn sẽ được giữ nguyên.", "Delete this client dossier? The source email will be preserved."))) return;
    await remove.mutateAsync(selected);
    setSelected(null);
    toast.success(tx("Đã xóa hồ sơ doanh nghiệp", "Dossier deleted successfully"));
  }

  const totalCount = cases.data?.length ?? 0;
  const readyCount = cases.data?.filter((c) => ["COMPLETED", "REPORT_READY"].includes((c.status || "").toUpperCase())).length ?? 0;
  const actionRequiredCount = cases.data?.filter((c) => ["NEEDS_REVIEW", "RETRYING", "DEAD_LETTER", "REJECTED"].includes((c.status || "").toUpperCase())).length ?? 0;

  const renderCaseItem = (item: CustomerIntelligenceCase) => {
    const isSelected = selected === item.id;
    const badge = statusBadgeInfo(item.status, locale);
    const title = item.company_name || item.company_domain || tx("Bản tóm tắt khách hàng", "Client Briefing");

    if (viewMode === "compact") {
      return (
        <button
          key={item.id}
          type="button"
          onClick={() => setSelected(item.id)}
          className={`w-full rounded-lg border px-3 py-2 text-left transition-all flex items-center justify-between gap-3 ${
            isSelected
              ? "border-primary bg-primary/10 shadow-sm ring-1 ring-primary/25"
              : "border-border/70 bg-card hover:border-border hover:bg-muted/40"
          }`}
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="grid h-7 w-7 shrink-0 place-items-center rounded-md border border-border/80 bg-muted font-bold text-primary text-[11px]">
              {title.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className={`truncate text-xs font-semibold ${isSelected ? "text-primary" : "text-foreground"}`}>
                {title}
              </p>
              {item.company_domain && (
                <p className="truncate font-mono text-[10px] text-muted-foreground">{item.company_domain}</p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Badge variant="outline" className={`text-[9.5px] px-1.5 py-0 ${badge.color}`}>
              {badge.label}
            </Badge>
            <span className="font-mono text-[10px] text-muted-foreground hidden sm:inline">
              {formatVietnamDateTime(item.created_at).split(" ")[0]}
            </span>
          </div>
        </button>
      );
    }

    return (
      <button
        key={item.id}
        type="button"
        onClick={() => setSelected(item.id)}
        className={`w-full rounded-xl border p-3.5 text-left transition-all ${
          isSelected
            ? "border-primary bg-primary/5 shadow-sm ring-1 ring-primary/20"
            : "border-border/80 bg-card hover:border-border hover:bg-muted/30"
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-start gap-2.5 min-w-0">
            <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-border/80 bg-muted/40 text-primary font-semibold text-xs">
              {title.charAt(0).toUpperCase()}
            </div>
            <div className="min-w-0">
              <p className="truncate font-semibold text-sm text-foreground">{title}</p>
              {item.company_domain && (
                <p className="truncate font-mono text-[11px] text-muted-foreground">{item.company_domain}</p>
              )}
            </div>
          </div>
          <Badge variant="outline" className={`shrink-0 text-[10px] ${badge.color}`}>
            {badge.label}
          </Badge>
        </div>

        <div className="mt-2.5 flex items-center justify-between border-t border-border/40 pt-2 text-[11px] text-muted-foreground">
          <span className="font-mono">{formatVietnamDateTime(item.created_at)}</span>
          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase font-mono">
            {item.trigger || "manual"}
          </span>
        </div>
      </button>
    );
  };

  return (
    <div className="space-y-6">
      {/* 1. Page Header */}
      <PageHeader
        icon={Building2}
        title={dict.pages.customerIntelligence.title}
        description={tx("Tự động nghiên cứu nền doanh nghiệp, thông báo thị trường và hồ sơ trước cuộc họp.", "Automated company background research, market briefings, and pre-meeting dossiers.")}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void cases.refetch()}
              disabled={cases.isFetching}
              className="h-9 gap-1.5"
            >
              <RefreshCw className={cases.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
              {tx("Làm mới", "Refresh")}</Button>
            <Button
              size="sm"
              onClick={() => setIsNewModalOpen(true)}
              className="h-9 gap-1.5 font-semibold"
            >
              <Plus className="h-4 w-4" />
              {tx("Nghiên cứu doanh nghiệp mới", "Research New Company")}</Button>
          </div>
        }
      />

      {/* 2. Executive Summary Metrics Cards */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <Building2 className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{totalCount}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Tổng cộng", "Total")}{tx("Hồ sơ Khách hàng", "Dossiers")}</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-500/10 text-emerald-500">
            <FileCheck2 className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{readyCount}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Thông báo sẵn sàng", "Briefings Ready")}</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-500/10 text-amber-500">
            <Flame className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{actionRequiredCount}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Cần hành động", "Action Required")}</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sky-500/10 text-sky-500">
            <Clock3 className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{schedules.data?.length ?? 0}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Đồng bộ lịch", "Sync Schedules")}</p>
          </div>
        </Card>
      </div>

      {/* 3. Navigation Tabs */}
      <div className="flex gap-2 border-b border-border/70 pb-2">
        <Button
          type="button"
          variant={activeTab === "cases" ? "secondary" : "ghost"}
          onClick={() => setActiveTab("cases")}
          className="gap-2 font-medium"
        >
          <FileText className="h-4 w-4" />
          {tx("Hồ sơ", "Dossiers")}</Button>
        <Button
          type="button"
          variant={activeTab === "schedules" ? "secondary" : "ghost"}
          onClick={() => setActiveTab("schedules")}
          className="gap-2 font-medium"
        >
          <Clock3 className="h-4 w-4" />
          {tx("Lịch", "Schedules")}</Button>
      </div>

      {/* 4. Main Body */}
      {activeTab === "cases" ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
          {/* Left Master List */}
          <Card className="shadow-card flex flex-col h-full">
            <CardHeader className="pb-3 space-y-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base font-semibold text-foreground">{tx("Luồng Hồ sơ Tình báo", "Briefing Stream")}</CardTitle>
                <div className="flex items-center gap-1.5">
                  <div className="flex rounded-md border border-border bg-muted/40 p-0.5">
                    <button
                      type="button"
                      onClick={() => setViewMode("compact")}
                      className={`p-1 rounded text-xs transition-colors ${
                        viewMode === "compact" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                      }`}
                      title={tx("Danh sách gọn", "Compact List")}
                    >
                      <List className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setViewMode("card")}
                      className={`p-1 rounded text-xs transition-colors ${
                        viewMode === "card" ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                      }`}
                      title={tx("Lưới thẻ", "Card Grid")}
                    >
                      <LayoutGrid className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <Badge variant="outline" className="font-mono text-[10.5px]">
                    {displayCases.length}
                  </Badge>
                </div>
              </div>

              {/* Business Focus Smart Filter Tabs */}
              <div className="flex rounded-lg border border-border/70 bg-muted/40 p-1 gap-1">
                <button
                  type="button"
                  onClick={() => setBusinessFilter("all")}
                  className={`flex-1 rounded-md py-1 text-xs font-medium transition-all ${
                    businessFilter === "all" ? "bg-card text-foreground font-semibold shadow-sm border border-border/40" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tx("Tất cả", "All")}</button>
                <button
                  type="button"
                  onClick={() => setBusinessFilter("action_required")}
                  className={`flex-1 rounded-md py-1 text-xs font-medium transition-all ${
                    businessFilter === "action_required" ? "bg-card text-foreground font-semibold shadow-sm border border-border/40" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tx("🔥 Cần xử lý", "🔥 Action")}
                </button>
                <button
                  type="button"
                  onClick={() => setBusinessFilter("pre_meeting")}
                  className={`flex-1 rounded-md py-1 text-xs font-medium transition-all ${
                    businessFilter === "pre_meeting" ? "bg-card text-foreground font-semibold shadow-sm border border-border/40" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tx("📅 Trước cuộc họp", "📅 Pre-Meeting")}
                </button>
                <button
                  type="button"
                  onClick={() => setBusinessFilter("ready")}
                  className={`flex-1 rounded-md py-1 text-xs font-medium transition-all ${
                    businessFilter === "ready" ? "bg-card text-foreground font-semibold shadow-sm border border-border/40" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tx("✅ Sẵn sàng", "✅ Ready")}
                </button>
              </div>

              {/* Search Bar */}
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder={tx("Tìm theo tên công ty hoặc domain...", "Search company or domain...")}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="pl-9 text-xs"
                />
              </div>
            </CardHeader>

            <CardContent className="space-y-4 flex-1 overflow-y-auto max-h-[calc(100vh-360px)] pr-2">
              {cases.isLoading && (
                <div className="space-y-2 py-4">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-12 rounded-lg bg-muted/40 animate-pulse" />
                  ))}
                </div>
              )}

              {/* Smart Timeline Bucket 1: Today & Next 24h */}
              {timelineBuckets.today.length > 0 && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs font-semibold text-primary">
                    <span className="flex items-center gap-1.5">
                      <Sparkles className="h-3.5 w-3.5" /> {tx("Họp hôm nay & sắp tới (", "Today & Upcoming Meetings (")}{timelineBuckets.today.length})
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    {timelineBuckets.today.map(renderCaseItem)}
                  </div>
                </div>
              )}

              {/* Smart Timeline Bucket 2: This Week */}
              {timelineBuckets.thisWeek.length > 0 && (
                <div className="space-y-2 pt-2 border-t border-border/40">
                  <div className="flex items-center justify-between text-xs font-semibold text-muted-foreground">
                    <span className="flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5" /> {tx("Tuần này (", "This Week (")}{timelineBuckets.thisWeek.length})
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    {timelineBuckets.thisWeek.map(renderCaseItem)}
                  </div>
                </div>
              )}

              {/* Smart Timeline Bucket 3: Earlier Archives (Collapsible) */}
              {timelineBuckets.earlier.length > 0 && (
                <div className="space-y-2 pt-2 border-t border-border/40">
                  <button
                    type="button"
                    onClick={() => toggleSection("earlier")}
                    className="flex w-full items-center justify-between text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <span className="flex items-center gap-1.5">
                      <Layers className="h-3.5 w-3.5" /> {tx("Lưu trữ trước đó (", "Earlier Archives (")}{timelineBuckets.earlier.length})
                    </span>
                    {collapsedSections.earlier ? (
                      <ChevronRight className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronDown className="h-3.5 w-3.5" />
                    )}
                  </button>
                  {!collapsedSections.earlier && (
                    <div className="space-y-1.5">
                      {timelineBuckets.earlier.map(renderCaseItem)}
                    </div>
                  )}
                </div>
              )}

              <div className="pt-2">
                <DataPagination
                  page={casePage}
                  pageSize={casePageSize}
                  totalItems={displayCases.length}
                  onPageChange={setCasePage}
                  onPageSizeChange={setCasePageSize}
                  pageSizeOptions={[4, 8, 16]}
                  compact
                />
              </div>
              {!cases.isLoading && !displayCases.length && (
                <div className="rounded-xl border border-dashed border-border p-8 text-center text-xs text-muted-foreground">
                  <Building2 className="mx-auto h-8 w-8 text-muted-foreground mb-2" />
                  <p className="font-semibold text-foreground">{tx("Không có hồ sơ khách hàng trong mục này", "No client dossiers in this category")}</p>
                  <p className="mt-1">{tx("Thử chuyển tab lọc hoặc tạo ca nghiên cứu mới.", "Try switching filter tabs or create a new research case.")}</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Right Detail Dossier Panel */}
          <Card className="shadow-card">
            <CardHeader className="border-b border-border/70 pb-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <CardTitle className="text-lg font-bold tracking-tight text-foreground">
                      {detail.data?.company_name || tx("Chi tiết hồ sơ khách hàng", "Client Dossier Details")}
                    </CardTitle>
                    {detail.data && (
                      <Badge variant="outline" className={`text-xs ${statusBadgeInfo(detail.data.status, locale).color}`}>
                        {statusBadgeInfo(detail.data.status, locale).label}
                      </Badge>
                    )}
                  </div>
                  {detail.data?.company_domain && (
                    <p className="text-xs text-muted-foreground font-mono mt-1">
                      {tx("Tên miền:", "Domain:")}{detail.data.company_domain}
                    </p>
                  )}
                </div>

                {detail.data && (
                  <div className="flex items-center gap-2">
                    {detail.data.report && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1 text-xs"
                        onClick={() => void downloadCiReport(detail.data!.id, "pdf")}
                      >
                        <Download className="h-3.5 w-3.5" /> {tx("PDF", "PDF")}</Button>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1 text-xs"
                      onClick={() => void research.mutateAsync(detail.data!.id)}
                      loading={research.isPending}
                    >
                      <RefreshCw className="h-3.5 w-3.5" /> {tx("Nghiên cứu lại", "Re-research")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-destructive hover:bg-destructive/10 text-xs"
                      onClick={deleteSelectedCase}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                )}
              </div>
            </CardHeader>

            <CardContent className="p-6">
              {!selected ? (
                <div className="py-24 text-center">
                  <FileText className="mx-auto h-12 w-12 text-muted-foreground/50 mb-3" />
                  <h3 className="text-base font-semibold text-foreground">{tx("Chưa chọn hồ sơ nào", "No Dossier Selected")}</h3>
                  <p className="mt-1 text-xs text-muted-foreground max-w-sm mx-auto">
                    {tx("Chọn một khách hàng từ luồng bên trái để xem thông báo nền tổng hợp, tín hiệu doanh nghiệp và chuẩn bị họp.", "Select a client from the stream on the left to view synthesized background briefings, company signals, and meeting preparation.")}</p>
                </div>
              ) : detail.isLoading ? (
                <div className="space-y-4 py-8">
                  <div className="h-8 w-1/3 rounded-lg bg-muted/40 animate-pulse" />
                  <div className="h-32 rounded-xl bg-muted/30 animate-pulse" />
                  <div className="h-48 rounded-xl bg-muted/20 animate-pulse" />
                </div>
              ) : detail.data?.report ? (
                <DetailedDossierView
                  report={detail.data.report}
                  sources={detail.data.sources}
                  meetings={detail.data.meetings}
                  companyName={detail.data.company_name}
                  companyDomain={detail.data.company_domain}
                />
              ) : (
                <div className="py-16 text-center">
                  <Activity className="mx-auto h-10 w-10 text-sky-500 animate-spin mb-3" />
                  <h3 className="text-base font-semibold text-foreground">{tx("Đang tổng hợp hồ sơ...", "Synthesizing Dossier...")}</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {tx("Nghiên cứu đang tổng hợp trao đổi email, hồ sơ doanh nghiệp và tin tức thị trường.", "Research is actively compiling email exchanges, company profiles, and market news.")}</p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-4"
                    onClick={() => void retry.mutateAsync(selected)}
                    loading={retry.isPending}
                  >
                    {tx("Thử tổng hợp lại", "Retry Synthesis")}</Button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      ) : (
        <SchedulesTabContent />
      )}

      {/* Manual Research Modal Dialog */}
      {isNewModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-md shadow-2xl border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base font-semibold text-foreground">
                {tx("Tổng hợp hồ sơ khách hàng", "Synthesize Client Dossier")}</CardTitle>
              <CardDescription className="text-xs">
                {tx("Kích hoạt nghiên cứu đa nguồn nền cho thông báo điều hành.", "Trigger background multi-source research for an executive briefing.")}</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={createManualCase} className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="manual-comp-name" className="text-xs font-medium">{tx("Tên doanh nghiệp *", "Company Name *")}</Label>
                  <Input
                    id="manual-comp-name"
                    placeholder={tx("VD: OpenAI, Stripe, FPT Software", "e.g. OpenAI, Stripe, FPT Software")}
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    required
                    className="text-xs"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="manual-comp-domain" className="text-xs font-medium">{tx("Website / Tên miền doanh nghiệp", "Company Website / Domain")}</Label>
                  <Input
                    id="manual-comp-domain"
                    placeholder={tx("VD: stripe.com", "e.g. stripe.com")}
                    value={companyDomain}
                    onChange={(e) => setCompanyDomain(e.target.value)}
                    className="text-xs font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="manual-comp-q" className="text-xs font-medium">{tx("Mục tiêu nghiên cứu cụ thể", "Specific Research Objective")}</Label>
                  <Input
                    id="manual-comp-q"
                    placeholder={tx("VD: Các sáng kiến mở rộng gần đây và lãnh đạo chủ chốt của họ là gì?", "e.g. What are their recent expansion initiatives and key executives?")}
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    className="text-xs"
                  />
                </div>
                <div className="flex justify-end gap-2 pt-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setIsNewModalOpen(false)}
                    className="text-xs"
                  >
                    {tx("Hủy", "Cancel")}</Button>
                  <Button
                    type="submit"
                    size="sm"
                    loading={manual.isPending}
                    disabled={!companyName.trim()}
                    className="text-xs font-semibold"
                  >
                    {tx("Bắt đầu nghiên cứu", "Start Research")}</Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
