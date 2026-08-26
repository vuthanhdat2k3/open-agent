"use client";

import * as React from "react";
import Link from "next/link";
import {
  Bell,
  Check,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Mail,
  MailOpen,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { PageHeader } from "@/components/page-header";
import { useTranslation } from "@/lib/i18n";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatVietnamDateTime, vietnamDateRangeStart } from "@/lib/datetime";
import {
  useCustomerIntelligenceNotifications,
  useMarkCustomerIntelligenceNotificationRead,
  useUrlSearchParam,
} from "@/hooks";
import { api } from "@/lib/api";
import { getActiveOrgId } from "@/lib/auth";
import { createIdempotencyKey } from "@/lib/email-intelligence/idempotency";
import { emailIntelligenceQueryKeys } from "@/lib/email-intelligence/query-keys";
import { toast } from "sonner";

type DateRange = "all" | "today" | "7d" | "30d";

type Rule = {
  id: string;
  name: string;
  status: string;
  match: { type: string; value: string };
  action: { type: string };
  conditions: Record<string, unknown>;
  capabilities: Record<string, boolean>;
  policy_version: string;
};

type RuleResponse = {
  items: Rule[];
  policy: Record<string, number | string>;
  meta: { server_time: string };
};

function dateRange(range: DateRange) {
  if (range === "all") return {};
  return { receivedAfter: vietnamDateRangeStart(range) };
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
  const { t, dict, locale } = useTranslation();
  const [tabParam, setTabParam] = useUrlSearchParam("tab");
  const activeTab = (tabParam as "inbox" | "rules") || "inbox";

  const [unreadOnly, setUnreadOnly] = React.useState(false);
  const [range, setRange] = React.useState<DateRange>("all");
  const [notificationType, setNotificationType] = React.useState("");
  const [searchInput, setSearchInput] = React.useState("");
  const [query, setQuery] = React.useState("");
  const [pageSize, setPageSize] = React.useState(6);
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
      toast.success("Trusted calendar rule created");
      void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).rules() });
    },
    onError: (value) => setRuleError(value instanceof Error ? value.message : "Failed to create rule"),
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

  const totalNotifications = notifications.data?.total ?? items.length;
  const unreadCount = notifications.data?.unread ?? 0;
  const totalRules = rules.data?.items?.length ?? 0;

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

  return (
    <div className="space-y-6">
      {/* 1. Header with Merged Title */}
      <PageHeader
        icon={Bell}
        title={dict.pages.emailIntelligence.title}
        description="AI-classified email inbox, meeting extraction signals, and auto-dispatch rules."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              void notifications.refetch();
              void rules.refetch();
            }}
            disabled={notifications.isFetching || rules.isFetching}
            className="gap-1.5"
          >
            <RefreshCw className={notifications.isFetching || rules.isFetching ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"} />
            Refresh
          </Button>
        }
      />

      {/* 2. Metrics Ribbon */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <Inbox className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{totalNotifications}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">Triage Queue</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sky-500/10 text-sky-500">
            <Mail className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{unreadCount}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">Unread Items</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-500/10 text-emerald-500">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{totalRules}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">Trusted Rules</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-500/10 text-amber-500">
            <Sparkles className="h-5 w-5" />
          </div>
          <div>
            <p className="text-lg font-bold leading-none capitalize text-foreground">Active</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">Classifier Status</p>
          </div>
        </Card>
      </div>

      {/* 3. Navigation Segmented Tabs */}
      <div className="flex gap-2 border-b border-border/70 pb-2">
        <Button
          type="button"
          variant={activeTab === "inbox" ? "secondary" : "ghost"}
          onClick={() => setTabParam("inbox")}
          className="gap-2 font-medium"
        >
          <Inbox className="h-4 w-4" />
          Inbox
          <Badge variant="outline" className="ml-1 text-[10px] font-mono">
            {totalNotifications}
          </Badge>
        </Button>

        <Button
          type="button"
          variant={activeTab === "rules" ? "secondary" : "ghost"}
          onClick={() => setTabParam("rules")}
          className="gap-2 font-medium"
        >
          <ShieldCheck className="h-4 w-4" />
          Rules
          <Badge variant="outline" className="ml-1 text-[10px] font-mono">
            {totalRules}
          </Badge>
        </Button>
      </div>

      {/* 4. Tab 1: Smart Inbox View */}
      {activeTab === "inbox" && (
        <div className="space-y-4">
          {/* Search & Filters */}
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="relative flex-1 max-w-md">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search subject, sender, or content..."
                className="pl-9 text-xs"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className="flex rounded-lg border border-border bg-muted/30 p-0.5">
                <Button
                  size="sm"
                  variant={!unreadOnly ? "secondary" : "ghost"}
                  className="h-7 text-xs font-medium"
                  onClick={() => changeUnread(false)}
                >
                  All
                </Button>
                <Button
                  size="sm"
                  variant={unreadOnly ? "secondary" : "ghost"}
                  className="h-7 text-xs font-medium"
                  onClick={() => changeUnread(true)}
                >
                  Unread
                </Button>
              </div>

              <select
                value={range}
                onChange={(e) => changeRange(e.target.value as DateRange)}
                className="flex h-8 cursor-pointer rounded-lg border border-border bg-background px-2.5 py-1 text-xs text-foreground shadow-sm hover:border-primary/40 focus-visible:outline-none"
              >
                <option value="all">All Time</option>
                <option value="today">Today</option>
                <option value="7d">Last 7 Days</option>
                <option value="30d">Last 30 Days</option>
              </select>

              <select
                value={notificationType}
                onChange={(e) => changeType(e.target.value)}
                className="flex h-8 cursor-pointer rounded-lg border border-border bg-background px-2.5 py-1 text-xs text-foreground shadow-sm hover:border-primary/40 focus-visible:outline-none"
              >
                <option value="">All Categories</option>
                <option value="CONTRACT_UPDATE">Contract Updates</option>
                <option value="CALENDAR_INVITE">Calendar Invites</option>
                <option value="GENERAL">General</option>
              </select>
            </div>
          </div>

          {/* Inbox List */}
          {notifications.isLoading ? (
            <LoadingSkeleton variant="table" />
          ) : notifications.isError ? (
            <ErrorState
              title="Unable to load notifications"
              description="Email triage feed could not be retrieved."
              onRetry={() => void notifications.refetch()}
            />
          ) : items.length ? (
            <div className="space-y-2.5">
              {items.map((n) => (
                <Card
                  key={n.id}
                  className={`shadow-card border-border/80 p-4 transition-all hover:border-primary/40 ${
                    !n.read_at ? "bg-primary/[0.02] border-primary/30 ring-1 ring-primary/10" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-border bg-muted/40 font-semibold text-primary text-xs">
                        {initials(n.sender_email || "Client")}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="truncate text-sm font-semibold text-foreground">
                            {n.subject || "(No subject)"}
                          </p>
                          {!n.read_at && (
                            <span className="h-2 w-2 rounded-full bg-primary shrink-0" />
                          )}
                        </div>
                        <p className="truncate text-xs text-muted-foreground mt-0.5">
                          {n.sender_name ? `${n.sender_name} <${n.sender_email}>` : n.sender_email} · {formatVietnamDateTime(n.received_at)} ({relativeTime(n.received_at)})
                        </p>
                        <p className="line-clamp-2 text-xs text-muted-foreground mt-2 leading-relaxed font-sans">
                          {preview(n.body, n.subject)}
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-col items-end gap-2 shrink-0">
                      <Badge variant="outline" className="text-[9.5px] uppercase font-mono">
                        {n.classification || n.type || "GENERAL"}
                      </Badge>
                      {!n.read_at && (
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground gap-1"
                          onClick={() => markRead.mutate(n.id)}
                        >
                          <Check className="h-3.5 w-3.5" /> Mark read
                        </Button>
                      )}
                    </div>
                  </div>
                </Card>
              ))}

              {/* Pagination Controls */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-border/60 pt-4 text-xs text-muted-foreground">
                <div className="flex items-center gap-3">
                  <span className="font-mono">
                    Page {pageIndex + 1} ({items.length} items)
                  </span>
                  <div className="flex items-center gap-1.5 font-sans">
                    <span className="text-[11px] text-muted-foreground">Per page:</span>
                    <select
                      value={pageSize}
                      onChange={(e) => {
                        setPageSize(Number(e.target.value));
                        resetPaging();
                      }}
                      className="h-7 rounded-md border border-border bg-background px-2 text-xs text-foreground cursor-pointer hover:border-primary/40 focus:outline-none"
                    >
                      <option value={5}>5</option>
                      <option value={6}>6</option>
                      <option value={8}>8</option>
                      <option value={10}>10</option>
                    </select>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 gap-1 text-xs"
                    disabled={pageIndex === 0 || notifications.isLoading}
                    onClick={() => setPageIndex((p) => Math.max(0, p - 1))}
                  >
                    <ChevronLeft className="h-4 w-4" /> Previous
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-8 gap-1 text-xs"
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
                    Next <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <EmptyState
              icon={Inbox}
              title="All caught up in your inbox"
              description="No incoming emails matched your active filters."
            />
          )}
        </div>
      )}

      {/* 5. Tab 2: Trusted Rules View */}
      {activeTab === "rules" && (
        <div className="space-y-4">
          <Card className="border-amber-500/30 bg-amber-500/[0.04] shadow-card">
            <CardContent className="space-y-1.5 p-4 text-xs">
              <p className="font-semibold text-amber-500 flex items-center gap-1.5">
                <ShieldCheck className="h-4 w-4" /> Production Safety Policy Defaults
              </p>
              <p className="text-muted-foreground leading-relaxed">
                Rules currently operate with strict safety boundaries (CALENDAR_AUTO_CREATE). Rules require a verified exact company domain, expiration date, daily execution caps, and SPF/DKIM/DMARC authentication.
              </p>
            </CardContent>
          </Card>

          <Card className="shadow-card border-border/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-foreground">Create Trusted Calendar Rule</CardTitle>
              <CardDescription className="text-xs">
                Auto-approve calendar invites from trusted partner domains that satisfy strict verification policies.
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
                <div className="space-y-1.5">
                  <Label htmlFor="rule-name" className="text-xs font-medium">Rule Name</Label>
                  <Input
                    id="rule-name"
                    placeholder="e.g. Acme Corp Auto-Meeting"
                    value={ruleName}
                    onChange={(e) => setRuleName(e.target.value)}
                    required
                    className="text-xs"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="rule-domain" className="text-xs font-medium">Trusted Domain</Label>
                  <Input
                    id="rule-domain"
                    placeholder="customer.example.com"
                    value={ruleDomain}
                    onChange={(e) => setRuleDomain(e.target.value)}
                    required
                    className="text-xs font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="rule-cal-id" className="text-xs font-medium">Calendar Connection ID</Label>
                  <Input
                    id="rule-cal-id"
                    placeholder="e.g. primary-google-cal"
                    value={calendarConnectionId}
                    onChange={(e) => setCalendarConnectionId(e.target.value)}
                    required
                    className="text-xs font-mono"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="rule-expiry" className="text-xs font-medium">Expiry Date & Time</Label>
                  <Input
                    id="rule-expiry"
                    type="datetime-local"
                    value={ruleExpiry}
                    onChange={(e) => setRuleExpiry(e.target.value)}
                    required
                    className="text-xs"
                  />
                </div>

                <div className="sm:col-span-2 lg:col-span-4 pt-1 flex items-center justify-between">
                  {ruleError ? (
                    <p className="text-xs text-destructive">{ruleError}</p>
                  ) : <span />}
                  <Button
                    type="submit"
                    loading={createRule.isPending}
                    disabled={!ruleName || !ruleDomain || !calendarConnectionId || !ruleExpiry}
                    className="gap-1.5 font-semibold text-xs h-9"
                  >
                    <Plus className="h-4 w-4" /> Create Trusted Rule
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          {rules.isLoading ? (
            <LoadingSkeleton variant="table" />
          ) : rules.isError ? (
            <ErrorState
              title="Unable to load rules"
              description="Trusted automation rules could not be loaded."
              onRetry={() => void rules.refetch()}
            />
          ) : rules.data?.items?.length ? (
            <div className="space-y-2.5">
              {rules.data.items.map((rule) => (
                <Card key={rule.id} className="shadow-card border-border/80 p-4 transition-colors hover:border-primary/40">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-sm text-foreground">{rule.name}</span>
                        <Badge variant={rule.status === "ACTIVE" ? "default" : "outline"} className="text-[9.5px]">
                          {rule.status}
                        </Badge>
                        <Badge variant="outline" className="text-[9.5px] font-mono">
                          Shadow Policy
                        </Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {rule.match.type}: <span className="font-mono text-primary">{rule.match.value}</span> · Action: {rule.action.type}
                      </p>
                      <p className="mt-0.5 text-[10px] text-muted-foreground font-mono">
                        Policy version: {rule.policy_version}
                      </p>
                    </div>

                    <div className="text-right text-xs text-muted-foreground font-mono">
                      <span>Daily Cap: {String(rule.conditions.maximum_events_per_day || 0)} events</span>
                      <br />
                      <span>Min Confidence: {String(rule.conditions.minimum_classification_confidence || 0)}</span>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <EmptyState
              icon={ShieldCheck}
              title="No automation rules configured"
              description="Create a trusted domain rule to enable automatic scheduling for key partners."
            />
          )}
        </div>
      )}
    </div>
  );
}
