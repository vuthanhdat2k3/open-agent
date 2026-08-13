"use client";

import * as React from "react";
import { toast } from "sonner";
import { ShieldCheck } from "lucide-react";
import { useApprovals, useCurrentRole, useDecideApproval } from "@/hooks";
import { createServerClock, formatRemaining, remainingMs } from "@/lib/email-intelligence/server-time";
import { createIdempotencyKey } from "@/lib/email-intelligence/idempotency";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingSkeleton, ConfirmDialog } from "@/components/shared";

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
  return <span className={remaining === 0 ? "font-medium text-destructive" : "text-muted-foreground"}>{formatRemaining(remaining)}</span>;
}

export default function ApprovalsPage() {
  const approvals = useApprovals();
  const decide = useDecideApproval();
  const isAdmin = useCurrentRole() === "admin";

  async function submit(id: string, decision: "approved" | "rejected") {
    try {
      await decide.mutateAsync({ id, decision, idempotencyKey: createIdempotencyKey() });
      toast.success(decision === "approved" ? "Approved" : "Rejected");
    } catch (error: any) {
      toast.error(error.message);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader icon={ShieldCheck} title="Approvals" description={isAdmin ? "Review tool and workflow approval requests" : "Review and approve your pending requests"} />
      {approvals.isLoading ? <LoadingSkeleton variant="table" /> : approvals.isError ? <ErrorState title="Unable to load approvals" description="Approval requests could not be loaded." onRetry={() => void approvals.refetch()} /> : approvals.data?.length ? (
        <div className="space-y-4 stagger">
          {approvals.data.map((approval) => (
            <Card key={approval.id} glass className="card-lift">
              <CardContent className="space-y-4 p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-foreground">{approval.tool_name || approval.node_id || approval.run_type}</div>
                    <div className="font-mono text-xs text-muted-foreground">{approval.id}</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="font-mono text-[10px]">{approval.run_type}</Badge>
                    <Badge variant={approval.risk_level === "HIGH" ? "destructive" : "outline"}>{approval.risk_level || "MEDIUM"} risk</Badge>
                    <Badge variant="outline">{approval.approval_mode || "EXPLICIT"}</Badge>
                    <ApprovalExpiry expiresAt={approval.expires_at} serverTime={approval.server_time} />
                  </div>
                </div>
                <pre className="max-h-48 overflow-auto rounded-lg border border-border/80 bg-muted/30 p-3 font-mono text-xs text-foreground scrollbar-thin">
                  {JSON.stringify(approval.args_snapshot, null, 2)}
                </pre>
                <div className="flex justify-end gap-2">
                  <ConfirmDialog trigger={<Button variant="outline">Reject</Button>} title="Reject this approval?" description="The requested tool or workflow action will not run." confirmLabel="Reject" destructive onConfirm={() => submit(approval.id, "rejected")} />
                  <Button className="active-tactile transition-transform" onClick={() => submit(approval.id, "approved")} disabled={approval.expires_at ? Boolean(approval.server_time && remainingMs(approval.expires_at, createServerClock(approval.server_time)) === 0) : false}>Approve</Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState icon={ShieldCheck} title="No pending approvals" description="Tool and workflow execution requests requiring manual approval will appear here." />
      )}
    </div>
  );
}
