"use client";

import * as React from "react";
import { CalendarDays, CheckCircle2, HardDrive, Loader2, Mail, Unplug } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { PageHeader } from "@/components/page-header";
import { LoadingSkeleton } from "@/components/shared";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";

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

// Connect/disconnect Google Drive, Calendar, and Email OAuth connectors.
// `withHeader` is off when embedded in a panel (e.g. the chat sidebar's
// Integrations sheet already has its own title) and on for the standalone
// `/integrations` route.
export function IntegrationsPanel({ withHeader = true }: { withHeader?: boolean }) {
  const [email, setEmail] = React.useState<Connection[]>([]);
  const [calendar, setCalendar] = React.useState<Connection[]>([]);
  const [drive, setDrive] = React.useState<Connection[]>([]);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState("");
  const [disconnectRequest, setDisconnectRequest] = React.useState<{ kind: "email" | "calendar" | "drive"; id: string; label: string } | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    try {
      const [mail, dates, drives] = await Promise.all([
        api.get<Connection[]>("/api/customer-intelligence/connections"),
        api.get<Connection[]>("/api/customer-intelligence/calendar-connections"),
        api.get<Connection[]>("/api/customer-intelligence/drive-connections"),
      ]);
      setEmail(mail);
      setCalendar(dates);
      setDrive(drives);
      setError("");
    } finally {
      setLoading(false);
    }
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

  async function performDisconnect(kind: "email" | "calendar" | "drive", id: string) {
    setBusy(id);
    try {
      const resource = kind === "email" ? "connections" : kind === "calendar" ? "calendar-connections" : "drive-connections";
      await api.delete(`/api/customer-intelligence/${resource}/${id}`);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not disconnect");
    } finally {
      setBusy(null);
      setDisconnectRequest(null);
    }
  }

  function ConnectionCard({ kind, item }: { kind: "email" | "calendar" | "drive"; item: Connection }) {
    return (
      <div className="flex items-center justify-between rounded-xl border border-border/70 bg-background/40 p-4">
        <div className="flex min-w-0 items-center gap-3">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-success" />
          <div className="min-w-0">
            <p className="truncate font-medium">{providerLabel[item.provider] ?? item.provider}</p>
            <p className="truncate text-sm text-muted-foreground">{item.account_email}</p>
          </div>
          <Badge variant="outline">{item.status}</Badge>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setDisconnectRequest({ kind, id: item.id, label: item.account_email })} disabled={busy === item.id} aria-label={`Disconnect ${item.account_email}`}>
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

  const connectedEmail = email.find((item) => item.status === "connected");
  const connectedCalendar = calendar.find((item) => item.status === "connected");
  const connectedDrive = drive.find((item) => item.status === "connected");

  return (
    <div className="space-y-8">
      {withHeader && <PageHeader icon={CalendarDays} title="Integrations" description="Connect work accounts through encrypted, approval-aware OAuth connectors." />}
      {error && <Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert>}
      {loading ? <LoadingSkeleton variant="grid" /> : <div className="grid gap-6 lg:grid-cols-2">
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><Mail className="h-5 w-5 text-primary" aria-hidden="true" />Email accounts</CardTitle></CardHeader><CardContent className="space-y-3">{connectedEmail ? <ConnectionCard kind="email" item={connectedEmail} /> : <ConnectCard kind="email" provider="google" />}</CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><CalendarDays className="h-5 w-5 text-primary" aria-hidden="true" />Calendar accounts</CardTitle></CardHeader><CardContent className="space-y-3">{connectedCalendar ? <ConnectionCard kind="calendar" item={connectedCalendar} /> : <ConnectCard kind="calendar" provider="google" />}</CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><HardDrive className="h-5 w-5 text-primary" aria-hidden="true" />Google Drive</CardTitle></CardHeader><CardContent className="space-y-3"><p className="text-sm leading-relaxed text-muted-foreground">List, read, create, update and delete files through the approval-gated Drive connector.</p>{connectedDrive ? <ConnectionCard kind="drive" item={connectedDrive} /> : <ConnectCard kind="drive" provider="google" />}</CardContent></Card>
      </div>}
      <AlertDialog open={Boolean(disconnectRequest)} onOpenChange={(open) => !open && setDisconnectRequest(null)}>
        <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>Disconnect {disconnectRequest?.label}?</AlertDialogTitle><AlertDialogDescription>OpenAgent will stop using this account for the selected connector. You can reconnect it later.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={() => disconnectRequest && void performDisconnect(disconnectRequest.kind, disconnectRequest.id)}>Disconnect</AlertDialogAction></AlertDialogFooter></AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
