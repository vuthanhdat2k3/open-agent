"use client";

import * as React from "react";
import { Plus, ShieldCheck } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { getActiveOrgId } from "@/lib/auth";
import { createIdempotencyKey } from "@/lib/email-intelligence/idempotency";
import { emailIntelligenceQueryKeys } from "@/lib/email-intelligence/query-keys";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared";

type Rule = { id: string; name: string; status: string; match: { type: string; value: string }; action: { type: string }; conditions: Record<string, unknown>; capabilities: Record<string, boolean>; policy_version: string };
type RuleResponse = { items: Rule[]; policy: Record<string, number | string>; meta: { server_time: string } };

export default function AutomationRulesPage() {
  const orgId = getActiveOrgId();
  const qc = useQueryClient();
  const rules = useQuery({ queryKey: emailIntelligenceQueryKeys(orgId).rules(), queryFn: () => api.get<RuleResponse>("/api/email-intelligence/trusted-rules") });
  const [name, setName] = React.useState("");
  const [domain, setDomain] = React.useState("");
  const [calendarConnectionId, setCalendarConnectionId] = React.useState("");
  const [expiry, setExpiry] = React.useState("");
  const [error, setError] = React.useState("");
  const create = useMutation({
    mutationFn: () => api.post<Rule>("/api/email-intelligence/trusted-rules", { name, match_type: "DOMAIN", match_value: domain, calendar_connection_id: calendarConnectionId, minimum_classification_confidence: 0.95, maximum_events_per_day: 3, expires_at: new Date(expiry).toISOString() }, { headers: { "Idempotency-Key": createIdempotencyKey() } }),
    onSuccess: () => { setName(""); setDomain(""); setCalendarConnectionId(""); setExpiry(""); void qc.invalidateQueries({ queryKey: emailIntelligenceQueryKeys(orgId).rules() }); },
    onError: (value) => setError(value instanceof Error ? value.message : "Không thể tạo rule"),
  });

  return <div className="space-y-6"><PageHeader icon={ShieldCheck} title="Automation Rules" description="Trusted calendar rules run in shadow mode first and never bypass server policy." /><Card className="border-warning/40 bg-warning/5"><CardContent className="space-y-2 p-5 text-sm"><p className="font-semibold">Production safety defaults</p><p className="text-muted-foreground">Chỉ hỗ trợ CALENDAR_AUTO_CREATE. Rule phải có domain cụ thể, expiry, daily cap, confidence cao, guard PASS và SPF/DKIM/DMARC aligned. Email domain công cộng không được dùng cho rule theo domain.</p></CardContent></Card><Card><CardHeader><CardTitle className="flex items-center gap-2"><Plus className="h-4 w-4" />Create calendar rule</CardTitle><CardDescription>Preview hiện là read-only shadow mode; chưa tạo lịch thật.</CardDescription></CardHeader><CardContent><form className="grid gap-3 md:grid-cols-4" onSubmit={(event) => { event.preventDefault(); setError(""); create.mutate(); }}><Input aria-label="Rule name" placeholder="Rule name" value={name} onChange={(event) => setName(event.target.value)} required /><Input aria-label="Trusted domain" placeholder="customer.example.com" value={domain} onChange={(event) => setDomain(event.target.value)} required /><Input aria-label="Calendar connection ID" placeholder="Calendar connection ID" value={calendarConnectionId} onChange={(event) => setCalendarConnectionId(event.target.value)} required /><Input aria-label="Expiry" type="datetime-local" value={expiry} onChange={(event) => setExpiry(event.target.value)} required /><Button type="submit" loading={create.isPending} disabled={!name || !domain || !calendarConnectionId || !expiry}>Create shadow rule</Button></form>{error && <p className="mt-3 text-sm text-destructive" role="alert">{error}</p>}</CardContent></Card>{rules.isLoading ? <LoadingSkeleton variant="table" /> : rules.isError ? <ErrorState title="Unable to load rules" description="Trusted rules could not be loaded." onRetry={() => void rules.refetch()} /> : rules.data?.items.length ? <div className="space-y-3">{rules.data.items.map((rule) => <Card key={rule.id}><CardContent className="flex flex-wrap items-center justify-between gap-4 p-4"><div><div className="flex items-center gap-2"><span className="font-semibold">{rule.name}</span><Badge variant={rule.status === "ACTIVE" ? "success" : "outline"}>{rule.status}</Badge><Badge variant="outline">Shadow</Badge></div><p className="mt-1 text-sm text-muted-foreground">{rule.match.type}: {rule.match.value} · {rule.action.type}</p><p className="mt-1 text-xs text-muted-foreground">Policy {rule.policy_version}</p></div><div className="text-right text-xs text-muted-foreground">Daily cap {String(rule.conditions.maximum_events_per_day || 0)}<br />Confidence {String(rule.conditions.minimum_classification_confidence || 0)}</div></CardContent></Card>)}</div> : <EmptyState icon={ShieldCheck} title="No automation rules" description="Create an exact-domain rule only when the server policy allows it." />}</div>;
}
