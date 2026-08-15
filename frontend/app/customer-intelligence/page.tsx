"use client";

import * as React from "react";
import { useDeferredValue, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Activity, Building2, CalendarClock, Clock3, HelpCircle, Link2, Pencil, Play, Plus, RefreshCw, Search, Trash2, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatVietnamDateTime } from "@/lib/datetime";
import { PageHeader } from "@/components/page-header";
import { useCiConnections, useCiSchedules, useCreateCiSchedule, useCreateManualCustomerIntelligenceCase, useCustomerIntelligenceCase, useCustomerIntelligenceCases, useDeleteCiSchedule, useDeleteCustomerIntelligenceCase, useResearchCustomerIntelligenceCase, useRetryCustomerIntelligenceCase, useRunCiScheduleNow, useUpdateCiSchedule } from "@/hooks";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { toast } from "sonner";
import type { CustomerIntelligenceSchedule } from "@/types";

function statusVariant(status: string) {
  if (["REPORT_READY", "COMPLETED"].includes(status)) return "success" as const;
  if (["RETRYING", "DEAD_LETTER", "REJECTED"].includes(status)) return "destructive" as const;
  if (["RESEARCHING", "EXECUTING"].includes(status)) return "info" as const;
  return "outline" as const;
}

function BriefingReport({
  report,
  sources,
  meetings,
}: {
  report: NonNullable<NonNullable<import("@/types").CustomerIntelligenceCaseDetail>["report"]>;
  sources: import("@/types").CustomerIntelligenceSource[];
  meetings: import("@/types").CustomerIntelligenceMeeting[];
}) {
  const data = report.rendering;
  if (!data || !("executive_summary" in data)) {
    return <article className="prose prose-sm max-w-none dark:prose-invert"><ReactMarkdown>{report.canonical_markdown}</ReactMarkdown></article>;
  }
  const companies = Array.isArray(data.company_overview) ? data.company_overview : [];
  const news = Array.isArray(data.recent_news) ? data.recent_news : [];
  const contacts = Array.isArray(data.contact_information) ? data.contact_information : [];
  const questions = Array.isArray(data.open_questions) ? data.open_questions : [];
  const reportMeetings = Array.isArray(data.upcoming_meetings) && data.upcoming_meetings.length ? data.upcoming_meetings : meetings;
  const reportSources = Array.isArray(data.sources) && data.sources.length ? data.sources : sources;
  const Section = ({ icon: Icon, title, count, children }: { icon: typeof Building2; title: string; count?: number; children: React.ReactNode }) => (
    <section className="rounded-xl border border-border/70 bg-card p-4 shadow-sm sm:p-5">
      <div className="mb-4 flex items-center gap-2 border-b border-border/60 pb-3">
        <Icon className="h-4 w-4 text-primary" aria-hidden="true" />
        <h3 className="font-semibold">{title}</h3>
        {typeof count === "number" && <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{count}</span>}
      </div>
      {children}
    </section>
  );
  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-primary/20 bg-primary/[0.04] p-4 sm:p-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-primary">Executive summary</p>
        <p className="mt-2 text-sm leading-6 text-foreground">{data.executive_summary || "No summary available."}</p>
      </section>
      <div className="grid gap-4 xl:grid-cols-2">
        <Section icon={Building2} title="Company overview" count={companies.length}>
          {companies.length ? <div className="space-y-3">{companies.map((company: any, index: number) => <div key={`${company.canonical_name || "company"}-${index}`} className="rounded-lg bg-muted/40 p-3"><p className="font-medium">{company.canonical_name || "Unknown company"}</p>{company.industry && <p className="mt-1 text-sm text-muted-foreground">{company.industry}</p>}{company.domain && <p className="mt-1 text-xs text-muted-foreground">{company.domain}</p>}</div>)}</div> : <p className="text-sm text-muted-foreground">No company matched.</p>}
        </Section>
        <Section icon={CalendarClock} title="Upcoming meetings" count={reportMeetings.length}>
          {reportMeetings.length ? <div className="space-y-3">{reportMeetings.map((meeting: any, index: number) => <div key={`${meeting.provider_event_id || meeting.title || "meeting"}-${index}`} className="rounded-lg bg-muted/40 p-3"><p className="font-medium">{meeting.title || "Meeting"}</p><p className="mt-1 text-sm text-muted-foreground">{meeting.start_at ? formatVietnamDateTime(meeting.start_at) : "Time not specified"} · Giờ Việt Nam</p>{meeting.attendees?.length ? <p className="mt-1 text-xs text-muted-foreground">{meeting.attendees.join(", ")}</p> : null}</div>)}</div> : <p className="text-sm text-muted-foreground">No upcoming meetings matched.</p>}
        </Section>
      </div>
      <Section icon={Link2} title="Recent news" count={news.length}>
        {news.length ? <div className="space-y-3">{news.map((item: any, index: number) => <a key={`${item.url || "news"}-${index}`} href={item.url} target="_blank" rel="noreferrer" className="block rounded-lg border border-border/60 p-3 transition-colors hover:bg-muted/40"><p className="font-medium">{item.title || item.url}</p><p className="mt-1 line-clamp-2 text-sm leading-5 text-muted-foreground">{item.excerpt || "Open source"}</p><p className="mt-2 text-xs text-primary">{item.publisher || item.domain || "External source"} · Open source</p></a>)}</div> : <p className="text-sm text-muted-foreground">No recent news found.</p>}
      </Section>
      <div className="grid gap-4 xl:grid-cols-2">
        <Section icon={Users} title="Contact information" count={contacts.length}>
          {contacts.length ? <div className="space-y-2">{contacts.map((contact: any, index: number) => <div key={`${contact.email || contact.name || "contact"}-${index}`} className="text-sm"><span className="font-medium">{contact.name || "Unknown"}</span>{contact.role && <span className="text-muted-foreground"> · {contact.role}</span>}{contact.email && <p className="text-xs text-muted-foreground">{contact.email}</p>}</div>)}</div> : <p className="text-sm text-muted-foreground">No contacts found.</p>}
        </Section>
        <Section icon={HelpCircle} title="Open questions" count={questions.length}>
          {questions.length ? <ul className="space-y-2 text-sm text-muted-foreground">{questions.map((question: string, index: number) => <li key={`${question}-${index}`} className="flex gap-2"><span className="text-primary">•</span><span>{question}</span></li>)}</ul> : <p className="text-sm text-muted-foreground">No open questions.</p>}
        </Section>
      </div>
      <Section icon={Link2} title="Sources" count={reportSources.length}>
        {reportSources.length ? <div className="grid gap-2 sm:grid-cols-2">{reportSources.map((source: any, index: number) => <a key={`${source.url || "source"}-${index}`} href={source.url} target="_blank" rel="noreferrer" className="rounded-lg border border-border/60 p-3 hover:bg-muted/40"><p className="line-clamp-2 text-sm font-medium">{source.title || source.url}</p><p className="mt-1 text-xs text-muted-foreground">{source.publisher || source.domain || "External source"}{source.published_date ? ` · ${source.published_date}` : ""}</p></a>)}</div> : <p className="text-sm text-muted-foreground">No sources.</p>}
      </Section>
    </div>
  );
}

const SCHEDULE_TIMEZONES = [
  "UTC",
  "Asia/Ho_Chi_Minh",
  "Asia/Bangkok",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
  "Europe/London",
  "Europe/Berlin",
  "America/New_York",
  "America/Los_Angeles",
];

function scheduleDate(value: string | null) {
  return value ? formatVietnamDateTime(value) : "Not run yet";
}

function SchedulesPanel() {
  const connections = useCiConnections();
  const schedules = useCiSchedules();
  const create = useCreateCiSchedule();
  const update = useUpdateCiSchedule();
  const runNow = useRunCiScheduleNow();
  const remove = useDeleteCiSchedule();
  const [editing, setEditing] = useState<CustomerIntelligenceSchedule | null>(null);
  const [connectionId, setConnectionId] = useState("");
  const [runTime, setRunTime] = useState("06:00");
  const [timezone, setTimezone] = useState("Asia/Ho_Chi_Minh");
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    if (!editing) {
      setConnectionId((current) => current || connections.data?.find((item) => item.status === "connected" && item.has_credentials)?.id || "");
      return;
    }
    setConnectionId(editing.connection_id);
    setRunTime(editing.run_time);
    setTimezone(editing.timezone);
    setEnabled(editing.enabled);
  }, [connections.data, editing]);

  function resetForm() {
    setEditing(null);
    setRunTime("06:00");
    setTimezone("Asia/Ho_Chi_Minh");
    setEnabled(true);
    setConnectionId(connections.data?.find((item) => item.status === "connected" && item.has_credentials)?.id || "");
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      if (editing) {
        await update.mutateAsync({ id: editing.id, body: { run_time: runTime, timezone, enabled } });
        toast.success("Schedule updated");
      } else {
        if (!connectionId) {
          toast.error("Connect a Gmail account before creating a schedule");
          return;
        }
        await create.mutateAsync({ connection_id: connectionId, run_time: runTime, timezone, enabled });
        toast.success("Schedule created");
      }
      resetForm();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save schedule");
    }
  }

  async function runSchedule(id: string) {
    try {
      const result = await runNow.mutateAsync(id) as { new_cases?: number };
      toast.success(`Schedule ran${result.new_cases ? ` and found ${result.new_cases} new case${result.new_cases === 1 ? "" : "s"}` : ""}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not run schedule");
    }
  }

  async function deleteSchedule(id: string) {
    if (!window.confirm("Delete this schedule?")) return;
    try {
      await remove.mutateAsync(id);
      if (editing?.id === id) resetForm();
      toast.success("Schedule deleted");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete schedule");
    }
  }

  const connected = (connections.data || []).filter((item) => item.status === "connected" && item.has_credentials);
  const connectionLabel = (id: string) => connections.data?.find((item) => item.id === id)?.account_email || "Unknown Gmail account";
  const saving = create.isPending || update.isPending;

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.4fr)]">
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle>{editing ? "Edit schedule" : "Create a schedule"}</CardTitle>
                <CardDescription>Run Gmail sync automatically in the timezone you choose.</CardDescription>
              </div>
              {editing && <Button variant="ghost" size="sm" onClick={resetForm}>Cancel</Button>}
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={(event) => void submit(event)} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="ci-schedule-connection">Connected Gmail account</Label>
                <Select id="ci-schedule-connection" value={connectionId} onChange={(event) => setConnectionId(event.target.value)} disabled={Boolean(editing) || !connected.length} required>
                  <option value="">Select an account</option>
                  {connected.map((item) => <option key={item.id} value={item.id}>{item.account_email}</option>)}
                </Select>
                {!connected.length && <p className="text-xs text-muted-foreground">Connect a Gmail account in Integrations first.</p>}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="ci-schedule-time">Run time</Label>
                  <Input id="ci-schedule-time" type="time" value={runTime} onChange={(event) => setRunTime(event.target.value)} required />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="ci-schedule-timezone">Timezone</Label>
                  <Select id="ci-schedule-timezone" value={timezone} onChange={(event) => setTimezone(event.target.value)}>
                    {SCHEDULE_TIMEZONES.map((item) => <option key={item} value={item}>{item}</option>)}
                  </Select>
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm text-foreground">
                <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} className="h-4 w-4 rounded border-border text-primary focus:ring-primary" />
                Enabled
              </label>
              <Button type="submit" loading={saving} disabled={!editing && !connected.length}><Plus className="h-4 w-4" />{editing ? "Save changes" : "Create schedule"}</Button>
            </form>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-3"><div><CardTitle>Schedules</CardTitle><CardDescription>{schedules.data?.length ?? 0} configured daily syncs</CardDescription></div><Button variant="ghost" size="sm" onClick={() => void schedules.refetch()} disabled={schedules.isFetching}><RefreshCw className={schedules.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} /></Button></div>
          </CardHeader>
          <CardContent className="space-y-3">
            {schedules.isLoading && <p className="text-sm text-muted-foreground">Loading schedules…</p>}
            {schedules.data?.map((schedule) => (
              <div key={schedule.id} className="rounded-xl border border-border/70 bg-background/30 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2"><Clock3 className="h-4 w-4 text-primary" /><span className="font-semibold">Daily at {schedule.run_time}</span><Badge variant={schedule.enabled ? "success" : "outline"}>{schedule.enabled ? "Enabled" : "Disabled"}</Badge></div>
                    <p className="mt-1 truncate text-sm text-muted-foreground">{connectionLabel(schedule.connection_id)} · {schedule.timezone}</p>
                  </div>
                  <div className="flex shrink-0 gap-1"><Button variant="ghost" size="sm" onClick={() => setEditing(schedule)} aria-label={`Edit schedule at ${schedule.run_time}`}><Pencil className="h-4 w-4" /></Button><Button variant="ghost" size="sm" onClick={() => void deleteSchedule(schedule.id)} disabled={remove.isPending} aria-label={`Delete schedule at ${schedule.run_time}`}><Trash2 className="h-4 w-4 text-destructive" /></Button></div>
                </div>
                <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2"><span>Last run: {scheduleDate(schedule.last_run_at)}</span><span>Next run: {scheduleDate(schedule.next_run_at)}</span></div>
                <Button variant="outline" size="sm" className="mt-3" onClick={() => void runSchedule(schedule.id)} loading={runNow.isPending}><Play className="h-3.5 w-3.5" />Run now</Button>
              </div>
            ))}
            {!schedules.isLoading && !schedules.data?.length && <div className="rounded-xl border border-dashed p-8 text-center"><Clock3 className="mx-auto h-8 w-8 text-muted-foreground" /><p className="mt-2 text-sm font-medium">No schedules yet</p><p className="mt-1 text-xs text-muted-foreground">Create one to sync new customer email automatically.</p></div>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}


export default function CustomerIntelligencePage() {
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [showReview, setShowReview] = useState(false);
  const [offset, setOffset] = useState(0);
  const deferredQuery = useDeferredValue(query);
  const pageSize = 25;
  const cases = useCustomerIntelligenceCases({
    category: showReview ? "review" : "briefings",
    query: deferredQuery,
    limit: pageSize,
    offset,
  });
  const detail = useCustomerIntelligenceCase(selected);
  const research = useResearchCustomerIntelligenceCase();
  const retry = useRetryCustomerIntelligenceCase();
  const remove = useDeleteCustomerIntelligenceCase();
  const manual = useCreateManualCustomerIntelligenceCase();
  const [activeTab, setActiveTab] = useState<"cases" | "schedules">("cases");
  const [companyName, setCompanyName] = useState("");
  const [companyDomain, setCompanyDomain] = useState("");
  const [question, setQuestion] = useState("");
  useEffect(() => setOffset(0), [deferredQuery, showReview]);

  async function createManualCase(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!companyName.trim()) return;
    await manual.mutateAsync({
      company_name: companyName.trim(),
      ...(companyDomain.trim() ? { company_domain: companyDomain.trim() } : {}),
      ...(question.trim() ? { question: question.trim() } : {}),
    });
    setCompanyName("");
    setCompanyDomain("");
    setQuestion("");
  }

  async function deleteSelectedCase() {
    if (!selected || !window.confirm("Delete this research case? The source email will be kept.")) return;
    await remove.mutateAsync(selected);
    setSelected(null);
  }

  return (
    <div className="space-y-6">
      <PageHeader icon={Activity} title="Research Cases" description="Automated customer and partner briefings with traceable sources and human-controlled delivery." />
      <div className="flex gap-2 border-b border-border/70 pb-2" role="tablist" aria-label="Customer Intelligence workspace">
        <Button type="button" variant={activeTab === "cases" ? "secondary" : "ghost"} role="tab" aria-selected={activeTab === "cases"} onClick={() => setActiveTab("cases")}><Search className="h-4 w-4" />Cases</Button>
        <Button type="button" variant={activeTab === "schedules" ? "secondary" : "ghost"} role="tab" aria-selected={activeTab === "schedules"} onClick={() => setActiveTab("schedules")}><Clock3 className="h-4 w-4" />Schedules</Button>
      </div>
      {activeTab === "cases" ? <>
      <Card>
        <CardHeader><CardTitle>Start a manual research</CardTitle><CardDescription>Research a company without connecting email. The request stays private to your account.</CardDescription></CardHeader>
        <CardContent><form onSubmit={(event) => void createManualCase(event)} className="grid gap-3 md:grid-cols-[1fr_1fr_2fr_auto]"><Input aria-label="Company name" placeholder="Company name" value={companyName} onChange={(event) => setCompanyName(event.target.value)} required /><Input aria-label="Company domain" placeholder="company.com (optional)" value={companyDomain} onChange={(event) => setCompanyDomain(event.target.value)} /><Input aria-label="Research question" placeholder="Research question (optional)" value={question} onChange={(event) => setQuestion(event.target.value)} /><Button type="submit" loading={manual.isPending} disabled={!companyName.trim()}>Research</Button></form></CardContent>
      </Card>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.5fr)]">
        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-3"><div><CardTitle>{showReview ? "Needs review" : "Research cases"}</CardTitle><CardDescription>{cases.data?.length ?? 0} {showReview ? "items on this page" : "company briefings on this page"}</CardDescription></div><Button variant="ghost" size="sm" onClick={() => void cases.refetch()} disabled={cases.isFetching}><RefreshCw className={cases.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} /></Button></div>
            <div className="flex gap-2 pt-2"><div className="relative flex-1"><Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" /><Input aria-label="Search research cases" placeholder="Search company or domain" value={query} onChange={(event) => setQuery(event.target.value)} className="pl-8" /></div><Button type="button" variant={showReview ? "secondary" : "outline"} onClick={() => { setShowReview((value) => !value); setSelected(null); }}>{showReview ? "Show briefings" : "Needs review"}</Button></div>
          </CardHeader>
          <CardContent className="space-y-2">
            {cases.isLoading && <p className="text-sm text-muted-foreground">Loading cases…</p>}
            {cases.data?.map((item) => (
              <button key={item.id} type="button" onClick={() => setSelected(item.id)} className={`w-full rounded-lg border p-3 text-left transition-colors hover:bg-muted/50 ${selected === item.id ? "border-primary bg-primary/5" : "border-border/60"}`}>
                <div className="flex items-center justify-between gap-2"><span className="truncate font-medium">{item.company_name || item.company_domain || "Unmatched sender"}</span><Badge variant={statusVariant(item.status)}>{item.status}</Badge></div>
                <p className="mt-1 text-xs text-muted-foreground">{formatVietnamDateTime(item.created_at)} · Giờ Việt Nam · {item.trigger || "manual"}</p>
              </button>
            ))}
            {!cases.isLoading && !cases.data?.length && <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">{showReview ? "No emails need review." : "No company briefings yet. New customer emails will appear here after agent classification."}</p>}
            {(offset > 0 || (cases.data?.length ?? 0) === pageSize) && <div className="flex justify-between pt-2"><Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - pageSize))}>Previous</Button><Button variant="outline" size="sm" disabled={(cases.data?.length ?? 0) < pageSize} onClick={() => setOffset((value) => value + pageSize)}>Next</Button></div>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>{detail.data?.company_name || "Case details"}</CardTitle><CardDescription>{detail.data?.company_domain || "Select a case to inspect its briefing and provenance."}</CardDescription></CardHeader>
          <CardContent className="space-y-5">
            {!selected && <div className="flex min-h-48 items-center justify-center text-sm text-muted-foreground"><Search className="mr-2 h-4 w-4" />Select a case</div>}
              {detail.data && <>
              <div className="flex flex-wrap items-center gap-2"><Badge variant={statusVariant(detail.data.status)}>{detail.data.status}</Badge>{detail.data.error && <span className="text-sm text-destructive">{detail.data.error}</span>}<div className="ml-auto flex gap-2">{["INGESTED", "RESEARCHING"].includes(detail.data.status) && <Button size="sm" onClick={() => research.mutate(detail.data!.id)} disabled={research.isPending}><Search className="mr-1 h-3.5 w-3.5" />Research</Button>}{["RETRYING", "DEAD_LETTER", "NEEDS_REVIEW"].includes(detail.data.status) && <Button size="sm" variant="outline" onClick={() => retry.mutate(detail.data!.id)} disabled={retry.isPending}><RefreshCw className="mr-1 h-3.5 w-3.5" />Retry</Button>}{!["ACTION_PROPOSED", "AWAITING_APPROVAL", "APPROVED", "EXECUTING"].includes(detail.data.status) && <Button size="sm" variant="outline" onClick={() => void deleteSelectedCase()} disabled={remove.isPending}><Trash2 className="mr-1 h-3.5 w-3.5" />Delete</Button>}</div></div>
              {detail.data.report ? <BriefingReport report={detail.data.report} sources={detail.data.sources} meetings={detail.data.meetings} /> : <p className="text-sm text-muted-foreground">No briefing report yet.</p>}
            </>}
          </CardContent>
        </Card>
      </div>
      </> : <SchedulesPanel />}
    </div>
  );
}
