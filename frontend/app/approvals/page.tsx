"use client";

import * as React from "react";
import { toast } from "sonner";
import { ShieldCheck } from "lucide-react";
import { useApprovals, useDecideApproval } from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";

export default function ApprovalsPage() {
  const approvals = useApprovals();
  const decide = useDecideApproval();
  const [reason, setReason] = React.useState<Record<string, string>>({});

  async function submit(id: string, decision: "approved" | "rejected") {
    try {
      await decide.mutateAsync({ id, decision, reason: reason[id] || "" });
      toast.success(decision === "approved" ? "Approved" : "Rejected");
    } catch (error: any) {
      toast.error(error.message);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader icon={ShieldCheck} title="Approvals" description="Review tool and workflow approval requests" />
      {approvals.data?.length ? (
        <div className="space-y-3">
          {approvals.data.map((approval) => (
            <Card key={approval.id} glass>
              <CardContent className="space-y-4 p-5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold">{approval.tool_name || approval.node_id || approval.run_type}</div>
                    <div className="font-mono text-xs text-muted-foreground">{approval.id}</div>
                  </div>
                  <Badge variant="outline">{approval.run_type}</Badge>
                </div>
                <pre className="max-h-48 overflow-auto rounded-lg border border-border bg-muted/30 p-3 text-xs">
                  {JSON.stringify(approval.args_snapshot, null, 2)}
                </pre>
                <Textarea
                  value={reason[approval.id] || ""}
                  onChange={(e) => setReason((cur) => ({ ...cur, [approval.id]: e.target.value }))}
                  placeholder="Decision reason"
                />
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => submit(approval.id, "rejected")}>Reject</Button>
                  <Button onClick={() => submit(approval.id, "approved")}>Approve</Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <EmptyState icon={ShieldCheck} title="No pending approvals" />
      )}
    </div>
  );
}

