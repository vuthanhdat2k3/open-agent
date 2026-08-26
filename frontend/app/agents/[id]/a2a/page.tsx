"use client";

import * as React from "react";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import { CheckCircle2, Network, ShieldCheck } from "lucide-react";
import { useAgents, useUpdateAgent } from "@/hooks";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared";
import { useTranslation } from "@/lib/i18n";

export default function AgentA2APage() {
    const { locale } = useTranslation();
  const params = useParams();
  const agentId = params.id as string;
  const agents = useAgents();
  const updateAgent = useUpdateAgent();
  const agent = agents.data?.find((item) => item.id === agentId);
  const [a2aExposed, setA2aExposed] = React.useState(false);

  React.useEffect(() => {
    if (agent) setA2aExposed(Boolean((agent as any).a2a_exposed));
  }, [agent]);

  async function handleToggleA2A() {
    if (!agent) return;
    const nextState = !a2aExposed;
    try {
      await updateAgent.mutateAsync({ id: agent.id, a2a_exposed: nextState } as any);
      setA2aExposed(nextState);
      toast.success(nextState ? "Agent is now exposed via A2A protocol" : "Agent A2A exposure has been disabled");
    } catch (error: any) { toast.error(error?.message || "Failed to update A2A exposure setting"); }
  }

  if (agents.isLoading) return <LoadingSkeleton />;
  if (agents.isError) return <div className="space-y-6"><PageHeader icon={Network} title={locale === "vi" ? "A2A Settings" : "A2A Settings"} description={locale === "vi" ? "Configure Agent-to-Agent exposure." : "Configure Agent-to-Agent exposure."} /><ErrorState title={locale === "vi" ? "Unable to load agent" : "Unable to load agent"} description={locale === "vi" ? "The agent could not be loaded." : "The agent could not be loaded."} onRetry={() => void agents.refetch()} /></div>;
  if (!agent) return <EmptyState icon={Network} title={locale === "vi" ? "Agent not found" : "Agent not found"} description={locale === "vi" ? "This agent may have been removed or you may not have access to it." : "This agent may have been removed or you may not have access to it."} />;

  return <div className="space-y-6"><PageHeader icon={Network} title={`A2A Settings — ${agent.name}`} description={locale === "vi" ? "Configure Agent-to-Agent exposure and identity delegation policies." : "Configure Agent-to-Agent exposure and identity delegation policies."} /><Card><CardContent className="space-y-8 p-6"><div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between"><div className="max-w-2xl space-y-3"><div className="flex flex-wrap items-center gap-2"><Network className="h-5 w-5 text-primary" aria-hidden="true" /><h2 className="text-lg font-semibold">{locale === "vi" ? "Expose Agent via A2A" : "Expose Agent via A2A"}</h2><Badge variant={a2aExposed ? "success" : "outline"}>{a2aExposed ? "Exposed" : "Internal Only"}</Badge></div><p className="text-sm leading-relaxed text-muted-foreground">{locale === "vi" ? "When enabled, this agent will be listed in the organization&apos;s Agent Card (" : "When enabled, this agent will be listed in the organization&apos;s Agent Card ("}<code className="rounded bg-muted px-1 py-0.5 text-xs">{locale === "vi" ? "/.well-known/agent-card.json" : "/.well-known/agent-card.json"}</code>{locale === "vi" ? ") and can be invoked by peer agents over the A2A protocol." : ") and can be invoked by peer agents over the A2A protocol."}</p></div><Button variant={a2aExposed ? "destructive" : "default"} onClick={handleToggleA2A} loading={updateAgent.isPending}>{a2aExposed ? "Disable A2A Exposure" : "Enable A2A Exposure"}</Button></div><div className="border-t border-border/70 pt-6"><h3 className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />{locale === "vi" ? "A2A Security &amp; Identity Policy" : "A2A Security &amp; Identity Policy"}</h3><ul className="mt-3 space-y-2 text-sm leading-relaxed text-muted-foreground"><li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />{locale === "vi" ? "A2A requests pass through full authentication, quota, and guardrail enforcement." : "A2A requests pass through full authentication, quota, and guardrail enforcement."}</li><li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />{locale === "vi" ? "Effective permission is capped at the calling user&apos;s permission." : "Effective permission is capped at the calling user&apos;s permission."}</li><li className="flex gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />{locale === "vi" ? "Delegation chain is attached to audit records." : "Delegation chain is attached to audit records."}</li></ul></div></CardContent></Card></div>;
}
