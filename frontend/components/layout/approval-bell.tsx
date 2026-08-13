"use client";

import * as React from "react";
import Link from "next/link";
import { Bell, ChevronRight, Clock3, ShieldAlert } from "lucide-react";
import { toast } from "sonner";
import { useApprovals, useEmailIntelligenceNavigationSummary } from "@/hooks";
import type { ApprovalRequest } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

function approvalTitle(item: ApprovalRequest) {
  const args = item.args_snapshot || {};
  if (item.tool_name === "calendar_create_event" || args.start || args.attendees) return "Create calendar event";
  if (item.tool_name === "drive_create_file") return "Save research briefing";
  return item.action || item.tool_name || item.node_id || "Review requested action";
}

function expiry(expiresAt?: string | null) {
  if (!expiresAt) return "No expiry";
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return "Expired";
  const minutes = Math.ceil(ms / 60000);
  return minutes < 60 ? `Expires in ${minutes} minute${minutes === 1 ? "" : "s"}` : `Expires in ${Math.ceil(minutes / 60)} hour${minutes < 120 ? "" : "s"}`;
}

export function ApprovalBell() {
  const summary = useEmailIntelligenceNavigationSummary();
  const approvals = useApprovals(true);
  const previousIds = React.useRef<Set<string> | null>(null);
  const pending = summary.data?.user_workspace.approvals.pending ?? approvals.data?.length ?? 0;
  const urgent = summary.data?.user_workspace.approvals.urgent ?? approvals.data?.filter((item) => item.risk_level === "HIGH").length ?? 0;

  React.useEffect(() => {
    const current = new Set((approvals.data ?? []).map((item) => item.id));
    if (previousIds.current) {
      const fresh = (approvals.data ?? []).find((item) => !previousIds.current?.has(item.id));
      if (fresh) {
        toast("Approval required", {
          description: approvalTitle(fresh),
          duration: 5000,
          action: { label: "Review now", onClick: () => { window.location.href = `/approvals?approval_id=${encodeURIComponent(fresh.id)}`; } },
        });
      }
    }
    previousIds.current = current;
  }, [approvals.data]);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative h-10 w-10 rounded-xl" aria-label={`${pending} pending approvals${urgent ? `, ${urgent} urgent` : ""}`}>
          <Bell className="h-4 w-4" aria-hidden="true" />
          {pending > 0 && <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-foreground px-1 text-[10px] font-bold text-background">{pending > 99 ? "99+" : pending}</span>}
          {urgent > 0 && <span className="absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full bg-destructive ring-2 ring-background" aria-hidden="true" />}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[min(24rem,calc(100vw-2rem))] p-2">
        <DropdownMenuLabel className="flex items-center justify-between px-3 py-2">
          <span>Needs your attention</span>
          {urgent > 0 && <span className="text-xs font-semibold text-destructive">{urgent} urgent</span>}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {(approvals.data ?? []).slice(0, 5).map((item) => (
          <DropdownMenuItem key={item.id} asChild className="block cursor-pointer rounded-xl p-3">
            <Link href={`/approvals?approval_id=${encodeURIComponent(item.id)}`}>
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide">
                {item.risk_level === "HIGH" && <ShieldAlert className="h-3.5 w-3.5 text-destructive" aria-hidden="true" />}
                <span className={item.risk_level === "HIGH" ? "text-destructive" : "text-muted-foreground"}>{item.risk_level || "STANDARD"} · {item.approval_mode || "EXPLICIT"}</span>
              </div>
              <div className="mt-1 truncate text-sm font-semibold text-foreground">{approvalTitle(item)}</div>
              <div className="mt-1 flex items-center justify-between gap-2 text-xs text-muted-foreground">
                <span className="flex items-center gap-1"><Clock3 className="h-3 w-3" aria-hidden="true" />{expiry(item.expires_at)}</span>
                <span className="flex items-center gap-1 text-primary">Review <ChevronRight className="h-3 w-3" aria-hidden="true" /></span>
              </div>
            </Link>
          </DropdownMenuItem>
        ))}
        {!approvals.isLoading && !approvals.data?.length && <div className="px-3 py-6 text-center text-sm text-muted-foreground">All caught up</div>}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild className="justify-center font-semibold text-primary">
          <Link href="/approvals">View all approvals</Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export { approvalTitle, expiry };
