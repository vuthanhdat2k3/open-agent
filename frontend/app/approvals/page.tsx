"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { CalendarDays, ChevronRight, Clock3, ShieldAlert, ShieldCheck } from "lucide-react";
import { useApprovals, useCurrentRole, useDecideApproval } from "@/hooks";
import { createServerClock, formatRemaining, remainingMs } from "@/lib/email-intelligence/server-time";
import { createIdempotencyKey } from "@/lib/email-intelligence/idempotency";
import type { ApprovalRequest } from "@/types";
import { PageHeader } from "@/components/page-header";
import { formatVietnamDateTime } from "@/lib/datetime";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { EmptyState, ErrorState, LoadingSkeleton, ConfirmDialog } from "@/components/shared";
import { approvalTitle } from "@/components/layout/approval-bell";

function ApprovalExpiry({ expiresAt, serverTime }: { expiresAt?: string | null; serverTime?: string | null }) {
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
  return <span className={remaining <= 15 * 60 * 1000 ? "font-semibold text-destructive" : "text-muted-foreground"}>{formatRemaining(remaining)}</span>;
}

function eventDetails(approval: ApprovalRequest) {
  const args = approval.args_snapshot || {};
  return {
    summary: String(args.summary || args.title || args.subject || "Requested action"),
    start: args.start ? String(args.start) : null,
    end: args.end ? String(args.end) : null,
    attendees: Array.isArray(args.attendees) ? args.attendees.map(String) : [],
    source: args.description ? String(args.description) : "OpenAgent generated this request from your workflow or email.",
  };
}

function ApprovalCard({ approval, onOpen, onSubmit }: { approval: ApprovalRequest; onOpen: () => void; onSubmit: (decision: "approved" | "rejected") => Promise<void> }) {
  const details = eventDetails(approval);
  const highRisk = approval.risk_level === "HIGH";
  return (
    <Card className="border-border/80 bg-card transition-colors hover:border-primary/40">
      <CardContent className="space-y-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div className={`mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-xl ${highRisk ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary"}`}>
              {highRisk ? <ShieldAlert className="h-5 w-5" aria-hidden="true" /> : <CalendarDays className="h-5 w-5" aria-hidden="true" />}
            </div>
            <div className="min-w-0">
              <h2 className="text-base font-semibold text-foreground">{approvalTitle(approval)}</h2>
              <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{details.summary}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2 text-xs">
            <Badge variant={highRisk ? "destructive" : "outline"}>{highRisk ? "HIGH RISK" : "STANDARD"}</Badge>
            <Badge variant="outline">{approval.approval_mode || "EXPLICIT"}</Badge>
            <span className="flex items-center gap-1"><Clock3 className="h-3.5 w-3.5" aria-hidden="true" /><ApprovalExpiry expiresAt={approval.expires_at} serverTime={approval.server_time} /></span>
          </div>
        </div>
        <div className="grid gap-3 rounded-xl border border-border/70 bg-muted/20 p-4 text-sm sm:grid-cols-3">
          <div><dt className="text-xs font-medium text-muted-foreground">When</dt><dd className="mt-1 text-foreground">{details.start ? `${formatVietnamDateTime(details.start)} · Giờ Việt Nam` : "Not specified"}</dd></div>
          <div><dt className="text-xs font-medium text-muted-foreground">Attendees</dt><dd className="mt-1 truncate text-foreground">{details.attendees.length ? details.attendees.join(", ") : "Not specified"}</dd></div>
          <div><dt className="text-xs font-medium text-muted-foreground">Source</dt><dd className="mt-1 truncate text-foreground">{approval.run_type === "agent" ? "Agent workflow" : "Workflow run"}</dd></div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button variant="ghost" size="sm" className="gap-1" onClick={onOpen}>View details <ChevronRight className="h-4 w-4" aria-hidden="true" /></Button>
          <div className="flex gap-2">
            <ConfirmDialog trigger={<Button variant="outline" size="sm">Reject</Button>} title="Reject this approval?" description="The requested action will not run. This decision cannot be undone." confirmLabel="Reject" destructive onConfirm={() => onSubmit("rejected")} />
            <Button size="sm" onClick={() => void onSubmit("approved")} disabled={approval.expires_at ? Boolean(approval.server_time && remainingMs(approval.expires_at, createServerClock(approval.server_time)) === 0) : false}>Approve</Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ApprovalsPage() {
  const approvals = useApprovals();
  const decide = useDecideApproval();
  const role = useCurrentRole();
  const searchParams = useSearchParams();
  const [selected, setSelected] = React.useState<ApprovalRequest | null>(null);
  const pendingId = searchParams.get("approval_id");

  React.useEffect(() => {
    if (pendingId && approvals.data) setSelected(approvals.data.find((item) => item.id === pendingId) ?? null);
  }, [approvals.data, pendingId]);

  async function submit(id: string, decision: "approved" | "rejected") {
    try {
      const result = await decide.mutateAsync({ id, decision, idempotencyKey: createIdempotencyKey() });
      setSelected(null);
      toast.success(decision === "approved" ? "Approval accepted" : "Approval rejected");
      if (result.status !== decision) toast.info("The server returned the canonical approval state.");
    } catch (error: any) {
      toast.error(error?.status === 409 ? "This approval was already handled" : error?.status === 412 ? "Approval changed, reloading latest data" : error?.message || "Could not update approval");
      void approvals.refetch();
    }
  }

  const items = approvals.data ?? [];
  const urgent = items.filter((item) => item.risk_level === "HIGH").length;
  return (
    <div className="space-y-6">
      <PageHeader icon={ShieldCheck} title="Approvals" description={role === "admin" ? "Review actions across your organization" : "Review actions that need your decision"} />
      <div className="flex flex-wrap items-center gap-2" aria-label="Approval summary">
        {urgent > 0 && <Badge variant="destructive">{urgent} urgent</Badge>}
        <Badge variant="outline">{items.length} pending</Badge>
        <span className="ml-auto text-xs text-muted-foreground">Opening this page does not clear the notification.</span>
      </div>
      {approvals.isLoading ? <LoadingSkeleton variant="table" /> : approvals.isError ? <ErrorState title="Unable to load approvals" description="Approval requests could not be loaded." onRetry={() => void approvals.refetch()} /> : items.length ? (
        <div className="space-y-3" aria-label="Pending approvals">
          {items.map((approval) => <ApprovalCard key={approval.id} approval={approval} onOpen={() => setSelected(approval)} onSubmit={(decision) => submit(approval.id, decision)} />)}
        </div>
      ) : <EmptyState icon={ShieldCheck} title="All caught up" description="No actions currently need your approval." />}

      <Dialog open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-xl">
          {selected && (() => {
            const details = eventDetails(selected);
            return <>
              <DialogHeader>
                <DialogTitle>{approvalTitle(selected)}</DialogTitle>
                <DialogDescription>Review the action details before allowing OpenAgent to execute it.</DialogDescription>
              </DialogHeader>
              <div className="space-y-5" tabIndex={-1} autoFocus>
                <section><h3 className="text-sm font-semibold text-foreground">Why this needs approval</h3><p className="mt-1 text-sm text-muted-foreground">{details.source}</p></section>
                <section className="space-y-3 rounded-xl border border-border/70 bg-muted/20 p-4"><h3 className="text-sm font-semibold text-foreground">Action details</h3><div className="grid gap-3 text-sm"><div><span className="text-muted-foreground">Summary</span><p className="font-medium text-foreground">{details.summary}</p></div><div><span className="text-muted-foreground">When</span><p className="font-medium text-foreground">{details.start ? `${formatVietnamDateTime(details.start)} · Giờ Việt Nam` : "Not specified"}</p></div><div><span className="text-muted-foreground">Attendees</span><p className="break-words font-medium text-foreground">{details.attendees.length ? details.attendees.join(", ") : "Not specified"}</p></div></div></section>
                <section className="flex flex-wrap gap-2"><Badge variant={selected.risk_level === "HIGH" ? "destructive" : "outline"}>{selected.risk_level || "STANDARD"}</Badge><Badge variant="outline">{selected.approval_mode || "EXPLICIT APPROVAL"}</Badge><Badge variant="outline"><ApprovalExpiry expiresAt={selected.expires_at} serverTime={selected.server_time} /></Badge></section>
              </div>
              <DialogFooter><ConfirmDialog trigger={<Button variant="outline">Reject</Button>} title="Reject this approval?" description="The requested action will not run." confirmLabel="Reject" destructive onConfirm={() => submit(selected.id, "rejected")} /><Button onClick={() => void submit(selected.id, "approved")} disabled={selected.expires_at ? Boolean(selected.server_time && remainingMs(selected.expires_at, createServerClock(selected.server_time)) === 0) : false}>Approve</Button></DialogFooter>
            </>;
          })()}
        </DialogContent>
      </Dialog>
    </div>
  );
}
