"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import { Network, ShieldCheck, RefreshCw, CheckCircle2 } from "lucide-react";
import { useAgents, useUpdateAgent } from "@/hooks";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";

export default function AgentA2APage() {
  const params = useParams();
  const agentId = params.id as string;

  const { data: agents = [], isLoading } = useAgents();
  const updateAgent = useUpdateAgent();

  const agent = agents.find((a) => a.id === agentId);

  const [a2aExposed, setA2aExposed] = React.useState<boolean>(false);

  React.useEffect(() => {
    if (agent) {
      setA2aExposed(Boolean((agent as any).a2a_exposed));
    }
  }, [agent]);

  const handleToggleA2A = async () => {
    if (!agent) return;
    const nextState = !a2aExposed;
    try {
      await updateAgent.mutateAsync({
        id: agent.id,
        a2a_exposed: nextState,
      } as any);
      setA2aExposed(nextState);
      toast.success(
        nextState
          ? "Agent is now exposed via A2A protocol"
          : "Agent A2A exposure has been disabled"
      );
    } catch (err: any) {
      toast.error(err?.message || "Failed to update A2A exposure setting");
    }
  };

  if (isLoading) {
    return (
      <div className="p-6 space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (!agent) {
    return (
      <div className="p-6">
        <p className="text-muted-foreground">Agent not found.</p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl space-y-6">
      <PageHeader
        icon={Network}
        title={`A2A Settings — ${agent.name}`}
        description="Configure Agent-to-Agent (A2A) exposure and identity delegation policies."
      />

      <div className="rounded-xl border bg-card p-6 shadow-sm space-y-6">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Network className="h-5 w-5 text-primary" />
              <h3 className="text-lg font-semibold">Expose Agent via A2A</h3>
              <Badge variant={a2aExposed ? "default" : "outline"}>
                {a2aExposed ? "Exposed" : "Internal Only"}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground max-w-xl">
              When enabled, this agent will be listed in the organization&apos;s Agent Card
              (<code className="text-xs bg-muted px-1 py-0.5 rounded">/.well-known/agent-card.json</code>)
              and can be invoked by peer agents over the A2A protocol.
            </p>
          </div>

          <Button
            variant={a2aExposed ? "destructive" : "default"}
            onClick={handleToggleA2A}
            disabled={updateAgent.isPending}
          >
            {updateAgent.isPending && (
              <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
            )}
            {a2aExposed ? "Disable A2A Exposure" : "Enable A2A Exposure"}
          </Button>
        </div>

        <div className="border-t pt-6 space-y-4">
          <h4 className="font-medium text-sm flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-emerald-5-500" />
            A2A Security & Identity Policy
          </h4>
          <ul className="text-xs text-muted-foreground space-y-2 list-disc list-inside">
            <li>A2A requests pass through full authentication, quota, and guardrail enforcement.</li>
            <li>Effective permission is capped at the calling user&apos;s permission (User ∩ Agent Identity).</li>
            <li>RFC 8693 token exchange attaches delegation chain to all audit trail records.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
