"use client";

import * as React from "react";
import Link from "next/link";
import {
  Bell,
  Check,
  ChevronLeft,
  ChevronRight,
  Inbox,
  MailOpen,
  RefreshCw,
  Search,
  ShieldAlert,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared";
import {
  useCustomerIntelligenceNotifications,
  useMarkCustomerIntelligenceNotificationRead,
} from "@/hooks";

type DateRange = "all" | "today" | "7d" | "30d";

function dateRange(range: DateRange) {
  if (range === "all") return {};
  const now = new Date();
  const from = new Date(now);
  if (range === "today") from.setHours(0, 0, 0, 0);
  if (range === "7d") from.setDate(from.getDate() - 7);
  if (range === "30d") from.setDate(from.getDate() - 30);
  return { receivedAfter: from.toISOString() };
}

function relativeTime(value: string) {
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000);
  const absolute = Math.abs(seconds);
  const unit = absolute < 60 ? "second" : absolute < 3600 ? "minute" : absolute < 86400 ? "hour" : "day";
  const divisor = unit === "second" ? 1 : unit === "minute" ? 60 : unit === "hour" ? 3600 : 86400;
  return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(Math.round(seconds / divisor), unit);
}

function preview(body: string, subject: string) {
  const lines = body.split("\n");
  return lines[0].trim() === subject.trim() ? lines.slice(1).join(" ").trim() : body.replace(/\s+/g, " ").trim();
}

function initials(sender: string) {
  return sender.split("@")[0].slice(0, 2).toUpperCase();
}

export default function EmailIntelligencePage() {
  const [unreadOnly, setUnreadOnly] = React.useState(false);
  const [range, setRange] = React.useState<DateRange>("all");
  const [notificationType, setNotificationType] = React.useState("");
  const [searchInput, setSearchInput] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [pageIndex, setPageIndex] = React.useState(0);
  const [pageCursors, setPageCursors] = React.useState<(string | null)[]>([null]);
  const markRead = useMarkCustomerIntelligenceNotificationRead();

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
      query,
      notificationType,
      ...dateRange(range),
    }),
    [notificationType, pageCursors, pageIndex, query, range, unreadOnly],
  );
  const notifications = useCustomerIntelligenceNotifications(filters);
  const items = React.useMemo(
    () => [...(notifications.data?.items ?? [])].sort((a, b) => new Date(b.received_at).getTime() - new Date(a.received_at).getTime()),
    [notifications.data?.items],
  );

  function changeUnread(value: boolean) {
    setUnreadOnly(value);
    resetPaging();
  }

  function changeRange(value: DateRange) {
    setRange(value);
    resetPaging();
  }

  function changeType(value: string) {
    setNotificationType(value);
    resetPaging();
  }

  function nextPage() {
    if (!notifications.data?.next_cursor) return;
    setPageCursors((current) => [...current.slice(0, pageIndex + 1), notifications.data!.next_cursor]);
    setPageIndex((current) => current + 1);
  }

  function previousPage() {
    if (pageIndex === 0) return;
    setPageIndex((current) => current - 1);
  }

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      <PageHeader icon={Bell} title="Smart Inbox" description="A focused view of routed email and safe next steps." />

      <section className="space-y-3" aria-label="Inbox controls">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input
              value={searchInput}
              onChange={(event) => { setSearchInput(event.target.value); resetPaging(); }}
              placeholder="Search sender, subject, or email content"
              aria-label="Search inbox"
              className="h-11 pl-9"
            />
          </div>
          <Button variant="outline" size="icon" onClick={() => void notifications.refetch()} aria-label="Refresh inbox" disabled={notifications.isFetching}>
            <RefreshCw className={notifications.isFetching ? "h-4 w-4 animate-spin" : "h-4 w-4"} aria-hidden="true" />
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-lg border border-border bg-card p-1" role="tablist" aria-label="Read status">
            <Button variant={!unreadOnly ? "default" : "ghost"} size="sm" role="tab" aria-selected={!unreadOnly} onClick={() => changeUnread(false)}>All mail</Button>
            <Button variant={unreadOnly ? "default" : "ghost"} size="sm" role="tab" aria-selected={unreadOnly} onClick={() => changeUnread(true)}>Unread</Button>
          </div>
          <select aria-label="Filter by date" value={range} onChange={(event) => changeRange(event.target.value as DateRange)} className="h-9 rounded-lg border border-border bg-card px-3 text-xs font-medium text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <option value="all">All time</option>
            <option value="today">Today</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
          <select aria-label="Filter by type" value={notificationType} onChange={(event) => changeType(event.target.value)} className="h-9 rounded-lg border border-border bg-card px-3 text-xs font-medium text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <option value="">All types</option>
            <option value="email_received">Email received</option>
          </select>
          <div className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
            <Inbox className="h-3.5 w-3.5" aria-hidden="true" />
            {notifications.data?.total ?? 0} messages
            {(notifications.data?.unread ?? 0) > 0 && <Badge variant="info">{notifications.data?.unread} unread</Badge>}
          </div>
        </div>
      </section>

      {notifications.isLoading ? <LoadingSkeleton variant="table" /> : notifications.isError ? (
        <ErrorState title="Unable to load inbox" description="Notifications could not be loaded." onRetry={() => void notifications.refetch()} />
      ) : items.length ? (
        <section className="overflow-hidden rounded-xl border border-border bg-card" aria-label="Email notifications" aria-live="polite">
          {items.map((item) => {
            const unread = !item.read_at;
            const isSecurity = item.type.includes("security") || item.type.includes("quarantine");
            return (
              <article key={item.id} className={`group border-b border-border px-4 py-4 last:border-b-0 sm:px-5 ${unread ? "bg-primary/[0.035]" : "bg-card"}`}>
                <div className="flex items-start gap-3 sm:gap-4">
                  <div className={`mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full text-xs font-bold ${isSecurity ? "bg-destructive/10 text-destructive" : unread ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"}`} aria-hidden="true">
                    {isSecurity ? <ShieldAlert className="h-4 w-4" /> : initials(item.sender_email)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-start gap-x-2 gap-y-1">
                      <h2 className={`min-w-0 truncate text-sm ${unread ? "font-bold text-foreground" : "font-semibold text-foreground/85"}`} title={item.sender_email}>{item.sender_name || item.sender_email}</h2>
                      {item.sender_name && <span className="max-w-full truncate text-xs text-muted-foreground">&lt;{item.sender_email}&gt;</span>}
                      {unread && <Badge variant="info" className="ml-auto">Unread</Badge>}
                    </div>
                    <div className="mt-1 flex items-baseline justify-between gap-3">
                      <p className={`truncate text-sm ${unread ? "font-semibold" : "font-medium text-foreground/80"}`}>{item.subject || "(No subject)"}</p>
                      <time className="shrink-0 text-xs text-muted-foreground" dateTime={item.received_at} title={new Date(item.received_at).toLocaleString()}>{relativeTime(item.received_at)}</time>
                    </div>
                    <p className="mt-1 line-clamp-2 break-words text-sm leading-5 text-muted-foreground" title={preview(item.body, item.subject)}>{preview(item.body, item.subject) || "No preview available"}</p>
                    <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
                      <Link href={`/customer-intelligence?email_id=${encodeURIComponent(item.email_id)}`} className="text-xs font-semibold text-primary hover:underline">Open related research</Link>
                      {unread && <Button size="sm" variant="outline" onClick={() => markRead.mutate(item.id)} disabled={markRead.isPending}><Check className="h-3.5 w-3.5" aria-hidden="true" />Mark read</Button>}
                      <Badge variant="outline" className="ml-auto hidden sm:inline-flex">{item.type.replaceAll("_", " ")}</Badge>
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
        </section>
      ) : (
        <div className="rounded-xl border border-dashed border-border bg-card px-6 py-14 text-center">
          {query || unreadOnly || range !== "all" ? <>
            <MailOpen className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden="true" />
            <h2 className="mt-3 font-semibold">No matching emails</h2>
            <p className="mt-1 text-sm text-muted-foreground">Try a broader search or clear one of the filters.</p>
            <Button variant="outline" size="sm" className="mt-4" onClick={() => { setSearchInput(""); setQuery(""); setUnreadOnly(false); setRange("all"); setNotificationType(""); resetPaging(); }}>Clear filters</Button>
          </> : <EmptyState icon={Bell} title="Your inbox is clear" description="Connect Gmail to receive routed email summaries and customer research updates." />}
        </div>
      )}

      {(notifications.data?.has_more || pageIndex > 0) && (
        <nav className="flex items-center justify-between border-t border-border pt-4" aria-label="Inbox pagination">
          <Button variant="outline" size="sm" onClick={previousPage} disabled={pageIndex === 0 || notifications.isFetching}><ChevronLeft className="h-4 w-4" aria-hidden="true" />Newer</Button>
          <span className="text-xs text-muted-foreground">Page {pageIndex + 1} · 25 per page</span>
          <Button variant="outline" size="sm" onClick={nextPage} disabled={!notifications.data?.has_more || notifications.isFetching}>Older<ChevronRight className="h-4 w-4" aria-hidden="true" /></Button>
        </nav>
      )}
    </div>
  );
}
