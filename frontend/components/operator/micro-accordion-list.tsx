"use client";

import * as React from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, ChevronLeft, ExternalLink, Mail, FileText, ArrowRight, Inbox, Sparkles } from "lucide-react";
import type { CustomerIntelligenceNotification, CustomerIntelligenceCase } from "@/types";
import { formatVietnamDateTime } from "@/lib/datetime";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";

const ITEMS_PER_PAGE = 5;

// Email Triage Accordion List with 5-item Pagination
export function EmailTriageAccordion({
  notifications,
  onOpenEmail,
}: {
  notifications: CustomerIntelligenceNotification[];
  onOpenEmail?: (notification: CustomerIntelligenceNotification) => void;
}) {
    const { locale, tx } = useTranslation();
  const [expandedId, setExpandedId] = React.useState<string | null>(null);
  const [page, setPage] = React.useState(0);

  if (notifications.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card/60 p-8 text-center">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-sky-500/10 text-sky-500">
          <Inbox className="h-5 w-5" />
        </div>
        <p className="mt-3 text-sm font-semibold text-foreground">{tx("All Caught Up", "All Caught Up")}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {tx("No new emails requiring classification or action.", "No new emails requiring classification or action.")}</p>
      </div>
    );
  }

  const totalPages = Math.ceil(notifications.length / ITEMS_PER_PAGE);
  const currentPageItems = notifications.slice(
    page * ITEMS_PER_PAGE,
    (page + 1) * ITEMS_PER_PAGE
  );

  return (
    <div className="flex flex-col gap-2.5">
      {/* Header with 5-item Pagination Controls */}
      <div className="flex items-center justify-between font-mono text-[10.5px] text-muted-foreground">
        <span>{tx("INBOUND EMAIL TRIAGE (", "INBOUND EMAIL TRIAGE (")}{notifications.length} {tx("NEW)", "NEW)")}</span>
        {totalPages > 1 && (
          <div className="flex items-center gap-1">
            <span>
              {page + 1} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="icon"
              className="h-5 w-5 rounded border-border bg-card text-muted-foreground hover:text-foreground"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              title={tx("Previous 5 items", "Previous 5 items")}
            >
              <ChevronLeft className="h-3 w-3" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="h-5 w-5 rounded border-border bg-card text-muted-foreground hover:text-foreground"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              title={tx("Next 5 items", "Next 5 items")}
            >
              <ChevronRight className="h-3 w-3" />
            </Button>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        {currentPageItems.map((n) => {
          const isExpanded = expandedId === n.id;
          const subject = n.subject || n.title || "(No subject)";
          const category = (n.classification || n.type || "GENERAL").toUpperCase();
          const isContract = category.includes("CONTRACT") || category.includes("URGENT");
          const isMeeting = category.includes("CALENDAR") || category.includes("MEETING");

          return (
            <div
              key={n.id}
              className="overflow-hidden rounded-xl border border-border/80 bg-card/60 transition-all hover:border-border hover:bg-card"
            >
              <button
                type="button"
                onClick={() => setExpandedId(isExpanded ? null : n.id)}
                className="flex w-full items-center justify-between gap-3 p-3 text-left"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <div
                    className={`grid h-6 w-6 shrink-0 place-items-center rounded-md ${
                      isContract
                        ? "bg-amber-500/10 text-amber-500"
                        : isMeeting
                          ? "bg-sky-500/10 text-sky-500"
                          : "bg-primary/10 text-primary"
                    }`}
                  >
                    <Mail className="h-3.5 w-3.5" />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold text-foreground">
                      {subject}
                    </p>
                    <p className="truncate text-[10.5px] text-muted-foreground">
                      {n.sender_email || "Client Email"} · {formatVietnamDateTime(n.created_at)}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <Badge variant="outline" className="text-[9.5px] uppercase font-mono">
                    {category}
                  </Badge>
                  <ChevronDown
                    className={`h-3.5 w-3.5 text-muted-foreground transition-transform duration-200 ${
                      isExpanded ? "rotate-180 text-foreground" : ""
                    }`}
                  />
                </div>
              </button>

              {isExpanded && (
                <div className="border-t border-border/60 bg-muted/40 p-3.5 text-xs">
                  <p className="line-clamp-4 leading-relaxed text-muted-foreground font-sans">
                    {n.body || "Email content scanned and classified by OpenAgent."}
                  </p>
                  <div className="mt-3 flex items-center justify-between border-t border-border/50 pt-2.5 text-[11px]">
                    <span className="font-mono text-muted-foreground">
                      {tx("Type:", "Type:")}{category}
                    </span>
                    {onOpenEmail && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-6 px-2 text-xs font-medium text-primary hover:text-primary hover:underline gap-1"
                        onClick={() => onOpenEmail(n)}
                      >
                        {tx("Inspect Full Email", "Inspect Full Email")}<ExternalLink className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="flex justify-center pt-1">
        <Link
          href="/email-intelligence"
          className="flex items-center gap-1 font-mono text-[11px] text-muted-foreground hover:text-primary hover:underline transition-colors"
        >
          {tx("View All", "View All")}{notifications.length} {tx("Emails in Smart Inbox (/email-intelligence)", "Emails in Smart Inbox (/email-intelligence)")}<ArrowRight className="h-3 w-3" />
        </Link>
      </div>
    </div>
  );
}

// Briefings Accordion List with 5-item Pagination
export function BriefingsAccordion({
  cases,
}: {
  cases: CustomerIntelligenceCase[];
}) {
    const { locale, tx } = useTranslation();
  const [page, setPage] = React.useState(0);

  if (cases.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card/60 p-8 text-center">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-500">
          <FileText className="h-5 w-5" />
        </div>
        <p className="mt-3 text-sm font-semibold text-foreground">{tx("No Briefings Available", "No Briefings Available")}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {tx("New company dossiers and meeting briefs will appear here after automated synthesis.", "New company dossiers and meeting briefs will appear here after automated synthesis.")}</p>
      </div>
    );
  }

  const totalPages = Math.ceil(cases.length / ITEMS_PER_PAGE);
  const currentPageItems = cases.slice(
    page * ITEMS_PER_PAGE,
    (page + 1) * ITEMS_PER_PAGE
  );

  return (
    <div className="flex flex-col gap-2.5">
      {/* Header with 5-item Pagination Controls */}
      <div className="flex items-center justify-between font-mono text-[10.5px] text-muted-foreground">
        <span>{tx("BRIEFINGS & DOSSIERS (", "BRIEFINGS & DOSSIERS (")}{cases.length} {tx("READY)", "READY)")}</span>
        {totalPages > 1 && (
          <div className="flex items-center gap-1">
            <span>
              {page + 1} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="icon"
              className="h-5 w-5 rounded border-border bg-card text-muted-foreground hover:text-foreground"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              title={tx("Previous 5 items", "Previous 5 items")}
            >
              <ChevronLeft className="h-3 w-3" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              className="h-5 w-5 rounded border-border bg-card text-muted-foreground hover:text-foreground"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              title={tx("Next 5 items", "Next 5 items")}
            >
              <ChevronRight className="h-3 w-3" />
            </Button>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        {currentPageItems.map((c) => (
          <Link
            key={c.id}
            href={`/customer-intelligence?case=${c.id}`}
            className="flex items-center justify-between rounded-xl border border-border/80 bg-card/60 p-3 transition-all hover:border-border hover:bg-card"
          >
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-emerald-500/10 text-emerald-500">
                <FileText className="h-3.5 w-3.5" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-foreground">
                  {c.company_name || c.company_domain || "Organization Dossier"}
                </p>
                <p className="truncate font-mono text-[10px] text-muted-foreground">
                  {c.company_domain ? `${c.company_domain} · ` : ""}
                  {formatVietnamDateTime(c.created_at)}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1 text-[11px] font-medium text-primary">
              <span>{tx("View Dossier", "View Dossier")}</span>
              <ChevronRight className="h-3.5 w-3.5" />
            </div>
          </Link>
        ))}
      </div>

      <div className="flex justify-center pt-1">
        <Link
          href="/customer-intelligence"
          className="flex items-center gap-1 font-mono text-[11px] text-muted-foreground hover:text-primary hover:underline transition-colors"
        >
          {tx("View All", "View All")}{cases.length} {tx("Dossiers in Client Intelligence (/customer-intelligence)", "Dossiers in Client Intelligence (/customer-intelligence)")}<ArrowRight className="h-3 w-3" />
        </Link>
      </div>
    </div>
  );
}
