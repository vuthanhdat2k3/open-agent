"use client";

import * as React from "react";
import { CalendarDays, CheckCircle2, HardDrive, Loader2, Mail, Unplug } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Connection {
  id: string;
  provider: string;
  account_email: string;
  status: string;
  has_credentials: boolean;
}

const providerLabel: Record<string, string> = {
  google: "Google",
};

export default function IntegrationsPage() {
  const [email, setEmail] = React.useState<Connection[]>([]);
  const [calendar, setCalendar] = React.useState<Connection[]>([]);
  const [drive, setDrive] = React.useState<Connection[]>([]);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [error, setError] = React.useState("");

  const load = React.useCallback(async () => {
    const [mail, dates, drives] = await Promise.all([
      api.get<Connection[]>("/api/customer-intelligence/connections"),
      api.get<Connection[]>("/api/customer-intelligence/calendar-connections"),
      api.get<Connection[]>("/api/customer-intelligence/drive-connections"),
    ]);
    setEmail(mail);
    setCalendar(dates);
    setDrive(drives);
  }, []);

  React.useEffect(() => {
    load().catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not load connections"));
  }, [load]);

  async function connect(kind: "email" | "calendar" | "drive", provider: "google") {
    const key = `${kind}:${provider}`;
    setBusy(key);
    setError("");
    try {
      const result = await api.get<{ url: string }>(`/api/customer-intelligence/oauth/${kind}/${provider}/start`);
      window.location.assign(result.url);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not start OAuth");
      setBusy(null);
    }
  }

  async function disconnect(kind: "email" | "calendar" | "drive", id: string) {
    setBusy(id);
    try {
      const resource = kind === "email" ? "connections" : kind === "calendar" ? "calendar-connections" : "drive-connections";
      await api.delete(`/api/customer-intelligence/${resource}/${id}`);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not disconnect");
    } finally {
      setBusy(null);
    }
  }

  function ConnectionCard({ kind, item }: { kind: "email" | "calendar" | "drive"; item: Connection }) {
    return (
      <div className="flex items-center justify-between rounded-xl border border-border/70 bg-background/40 p-4">
        <div className="flex min-w-0 items-center gap-3">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-500" />
          <div className="min-w-0">
            <p className="truncate font-medium">{providerLabel[item.provider] ?? item.provider}</p>
            <p className="truncate text-sm text-muted-foreground">{item.account_email}</p>
          </div>
          <Badge variant="outline">{item.status}</Badge>
        </div>
        <Button variant="ghost" size="sm" onClick={() => disconnect(kind, item.id)} disabled={busy === item.id}>
          {busy === item.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Unplug className="h-4 w-4" />}
          <span className="sr-only">Disconnect</span>
        </Button>
      </div>
    );
  }

  function ConnectCard({ kind, provider }: { kind: "email" | "calendar" | "drive"; provider: "google" }) {
    const key = `${kind}:${provider}`;
    return (
      <Button variant="outline" className="h-auto justify-start gap-3 p-4 text-left" onClick={() => connect(kind, provider)} disabled={busy === key}>
        {busy === key ? <Loader2 className="h-5 w-5 animate-spin" /> : kind === "email" ? <Mail className="h-5 w-5" /> : kind === "calendar" ? <CalendarDays className="h-5 w-5" /> : <HardDrive className="h-5 w-5" />}
        <span>Connect {providerLabel[provider]}</span>
      </Button>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary">Integrations</p>
        <h2 className="mt-2 text-3xl font-bold tracking-tight">Connect your work accounts</h2>
        <p className="mt-2 max-w-2xl text-muted-foreground">OAuth stays with OpenAgent. Tokens are encrypted and passed to the stateless MCP connector only when a tool runs.</p>
      </div>
      {error && <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Mail className="h-5 w-5 text-primary" />Email accounts</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {email.map((item) => <ConnectionCard key={item.id} kind="email" item={item} />)}
            <ConnectCard kind="email" provider="google" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><CalendarDays className="h-5 w-5 text-primary" />Calendar accounts</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {calendar.map((item) => <ConnectionCard key={item.id} kind="calendar" item={item} />)}
            <ConnectCard kind="calendar" provider="google" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><HardDrive className="h-5 w-5 text-primary" />Google Drive</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">List, read, create, update and delete files through the approval-gated Drive connector.</p>
            {drive.map((item) => <ConnectionCard key={item.id} kind="drive" item={item} />)}
            <ConnectCard kind="drive" provider="google" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
