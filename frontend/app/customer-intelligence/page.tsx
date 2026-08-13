"use client";

import * as React from "react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Activity, ExternalLink, RefreshCw, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/page-header";
import { useCreateManualCustomerIntelligenceCase, useCustomerIntelligenceCase, useCustomerIntelligenceCases, useResearchCustomerIntelligenceCase, useRetryCustomerIntelligenceCase } from "@/hooks";
import { Input } from "@/components/ui/input";

function statusVariant(status: string) {
  if (["REPORT_READY", "COMPLETED"].includes(status)) return "success" as const;
  if (["RETRYING", "DEAD_LETTER", "REJECTED"].includes(status)) return "destructive" as const;
  if (["RESEARCHING", "EXECUTING"].includes(status)) return "info" as const;
  return "outline" as const;
}

export default function CustomerIntelligencePage() {
  const [selected, setSelected] = useState<string | null>(null);
  const cases = useCustomerIntelligenceCases();
  const detail = useCustomerIntelligenceCase(selected);
  const research = useResearchCustomerIntelligenceCase();
  const retry = useRetryCustomerIntelligenceCase();
  const manual = useCreateManualCustomerIntelligenceCase();
  const [companyName, setCompanyName] = useState("");
  const [companyDomain, setCompanyDomain] = useState("");
  const [question, setQuestion] = useState("");

  async function createManualCase(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!companyName.trim()) return;
    await manual.mutateAsync({
      company_name: companyName.trim(),
      ...(companyDomain.trim() ? { company_domain: companyDomain.trim() } : {}),
      ...(question.trim() ? { question: question.trim() } : {}),
    });
    setCompanyName("");
    setCompanyDomain("");
    setQuestion("");
  }

  return (
    <div className="space-y-6">
      <PageHeader icon={Activity} title="Research Cases" description="Automated customer and partner briefings with traceable sources and human-controlled delivery." />
      <Card>
        <CardHeader><CardTitle>Start a manual research</CardTitle><CardDescription>Research a company without connecting email. The request stays private to your account.</CardDescription></CardHeader>
        <CardContent><form onSubmit={(event) => void createManualCase(event)} className="grid gap-3 md:grid-cols-[1fr_1fr_2fr_auto]"><Input aria-label="Company name" placeholder="Company name" value={companyName} onChange={(event) => setCompanyName(event.target.value)} required /><Input aria-label="Company domain" placeholder="company.com (optional)" value={companyDomain} onChange={(event) => setCompanyDomain(event.target.value)} /><Input aria-label="Research question" placeholder="Research question (optional)" value={question} onChange={(event) => setQuestion(event.target.value)} /><Button type="submit" loading={manual.isPending} disabled={!companyName.trim()}>Research</Button></form></CardContent>
      </Card>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.5fr)]">
        <Card>
          <CardHeader><CardTitle>Cases</CardTitle><CardDescription>{cases.data?.length ?? 0} research cases</CardDescription></CardHeader>
          <CardContent className="space-y-2">
            {cases.isLoading && <p className="text-sm text-muted-foreground">Loading cases…</p>}
            {cases.data?.map((item) => (
              <button key={item.id} type="button" onClick={() => setSelected(item.id)} className={`w-full rounded-lg border p-3 text-left transition-colors hover:bg-muted/50 ${selected === item.id ? "border-primary bg-primary/5" : "border-border/60"}`}>
                <div className="flex items-center justify-between gap-2"><span className="truncate font-medium">{item.company_name || item.company_domain || "Unmatched sender"}</span><Badge variant={statusVariant(item.status)}>{item.status}</Badge></div>
                <p className="mt-1 text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString()} · {item.trigger || "manual"}</p>
              </button>
            ))}
            {!cases.isLoading && !cases.data?.length && <p className="text-sm text-muted-foreground">No cases yet. Connect email and run a sync to start research.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>{detail.data?.company_name || "Case details"}</CardTitle><CardDescription>{detail.data?.company_domain || "Select a case to inspect its briefing and provenance."}</CardDescription></CardHeader>
          <CardContent className="space-y-5">
            {!selected && <div className="flex min-h-48 items-center justify-center text-sm text-muted-foreground"><Search className="mr-2 h-4 w-4" />Select a case</div>}
            {detail.data && <>
              <div className="flex flex-wrap items-center gap-2"><Badge variant={statusVariant(detail.data.status)}>{detail.data.status}</Badge>{detail.data.error && <span className="text-sm text-destructive">{detail.data.error}</span>}<div className="ml-auto flex gap-2">{["INGESTED", "RESEARCHING"].includes(detail.data.status) && <Button size="sm" onClick={() => research.mutate(detail.data!.id)} disabled={research.isPending}><Search className="mr-1 h-3.5 w-3.5" />Research</Button>}{["RETRYING", "DEAD_LETTER"].includes(detail.data.status) && <Button size="sm" variant="outline" onClick={() => retry.mutate(detail.data!.id)} disabled={retry.isPending}><RefreshCw className="mr-1 h-3.5 w-3.5" />Retry</Button>}</div></div>
              {detail.data.report ? <article className="prose prose-sm max-w-none dark:prose-invert"><ReactMarkdown>{detail.data.report.canonical_markdown}</ReactMarkdown></article> : <p className="text-sm text-muted-foreground">No briefing report yet.</p>}
              {detail.data.sources.length > 0 && <div><h3 className="mb-2 font-semibold">Sources ({detail.data.sources.length})</h3><div className="space-y-2">{detail.data.sources.map((source) => <a key={source.id} href={source.url} target="_blank" rel="noreferrer" className="block rounded-lg border border-border/60 p-3 hover:bg-muted/40"><div className="flex items-center gap-2 text-sm font-medium"><span className="truncate">{source.title}</span><ExternalLink className="h-3.5 w-3.5 shrink-0" /></div><p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{source.excerpt}</p></a>)}</div></div>}
            </>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
