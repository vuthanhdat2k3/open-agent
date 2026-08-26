"use client";

import * as React from "react";
import { CalendarDays, HardDrive, Loader2, Mail, Plug, Unplug } from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { PageHeader } from "@/components/page-header";
import { useTranslation } from "@/lib/i18n";
import { LoadingSkeleton } from "@/components/shared";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";

interface Connection {
  id: string;
  provider: string;
  account_email: string;
  status: string;
  has_credentials: boolean;
}

// Backend providers: "google" for calendar/drive, "gmail" for email
// specifically (future-proofed for other email providers). Both map to a
// proper-cased display label here.
const providerLabel: Record<string, string> = {
  google: "Google",
  gmail: "Gmail",
};

// Connect/disconnect Google Drive, Calendar, and Email OAuth connectors.
// `withHeader` is off when embedded in a panel (e.g. the chat sidebar's
// Integrations sheet already has its own title) and on for the standalone
// `/integrations` route.
export function IntegrationsPanel({ withHeader = true }: { withHeader?: boolean }) {
  const { t, dict, locale } = useTranslation();
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
      <div className="flex flex-col gap-3 rounded-xl border border-border/70 bg-background/40 p-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-success/10 text-success">
            <Plug className="h-4 w-4" aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="font-medium">{providerLabel[item.provider] ?? item.provider}</p>
            <p className="truncate text-sm text-muted-foreground" title={item.account_email}>{item.account_email}</p>
          </div>
        </div>
        <div className="flex items-center justify-between gap-2">
          <Badge variant="outline" className="border-success/40 text-success">{locale === "vi" ? "Connected" : "Connected"}</Badge>
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5 text-muted-foreground hover:text-destructive"
            onClick={() => setDisconnectRequest({ kind, id: item.id, label: item.account_email })}
            disabled={busy === item.id}
          >
            {busy === item.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Unplug className="h-4 w-4" />}
            {locale === "vi" ? "Disconnect" : "Disconnect"}</Button>
        </div>
      </div>
    );
  }

  function ConnectCard({ kind, provider }: { kind: "email" | "calendar" | "drive"; provider: "google" }) {
    const key = `${kind}:${provider}`;
    return (
      <Button variant="outline" className="h-auto w-full justify-start gap-3 p-4 text-left" onClick={() => connect(kind, provider)} disabled={busy === key}>
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground">
          {busy === key ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plug className="h-4 w-4" />}
        </div>
        <div>
          <p className="font-medium text-foreground">{locale === "vi" ? "Connect" : "Connect"}{providerLabel[provider]}</p>
          <p className="text-sm text-muted-foreground">{locale === "vi" ? "Not connected" : "Not connected"}</p>
        </div>
      </Button>
    );
  }

  const connectedEmail = email.find((item) => item.status === "connected");
  const connectedCalendar = calendar.find((item) => item.status === "connected");
  const connectedDrive = drive.find((item) => item.status === "connected");

  return (
    <div className="space-y-8">
      {withHeader && (
        <PageHeader
          icon={Plug}
          title={dict.pages.integrations.title}
          description={locale === "vi" ? "Connect work accounts (Gmail, Google Calendar, Google Drive) via secure OAuth connectors." : "Connect work accounts (Gmail, Google Calendar, Google Drive) via secure OAuth connectors."}
        />
      )}
      {error && <Alert variant="destructive" role="alert"><AlertDescription>{error}</AlertDescription></Alert>}
      {loading ? <LoadingSkeleton variant="grid" /> : <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Mail className="h-5 w-5 text-primary" aria-hidden="true" />{locale === "vi" ? "Email" : "Email"}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm leading-relaxed text-muted-foreground">{locale === "vi" ? "Read and organize inbound email through the approval-gated connector." : "Read and organize inbound email through the approval-gated connector."}</p>
            {connectedEmail ? <ConnectionCard kind="email" item={connectedEmail} /> : <ConnectCard kind="email" provider="google" />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><CalendarDays className="h-5 w-5 text-primary" aria-hidden="true" />{locale === "vi" ? "Calendar" : "Calendar"}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm leading-relaxed text-muted-foreground">{locale === "vi" ? "Read upcoming events and match them to customers or partners." : "Read upcoming events and match them to customers or partners."}</p>
            {connectedCalendar ? <ConnectionCard kind="calendar" item={connectedCalendar} /> : <ConnectCard kind="calendar" provider="google" />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><HardDrive className="h-5 w-5 text-primary" aria-hidden="true" />{locale === "vi" ? "Google Drive" : "Google Drive"}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm leading-relaxed text-muted-foreground">{locale === "vi" ? "List, read, create, update and delete files through the approval-gated connector." : "List, read, create, update and delete files through the approval-gated connector."}</p>
            {connectedDrive ? <ConnectionCard kind="drive" item={connectedDrive} /> : <ConnectCard kind="drive" provider="google" />}
          </CardContent>
        </Card>
      </div>}
      <AlertDialog open={Boolean(disconnectRequest)} onOpenChange={(open) => !open && setDisconnectRequest(null)}>
        <AlertDialogContent><AlertDialogHeader><AlertDialogTitle>{locale === "vi" ? "Disconnect" : "Disconnect"}{disconnectRequest?.label}?</AlertDialogTitle><AlertDialogDescription>{locale === "vi" ? "OpenAgent will stop using this account for the selected connector. You can reconnect it later." : "OpenAgent will stop using this account for the selected connector. You can reconnect it later."}</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>{locale === "vi" ? "Hủy" : "Cancel"}</AlertDialogCancel><AlertDialogAction className="bg-destructive text-destructive-foreground hover:bg-destructive/90" onClick={() => disconnectRequest && void performDisconnect(disconnectRequest.kind, disconnectRequest.id)}>{locale === "vi" ? "Disconnect" : "Disconnect"}</AlertDialogAction></AlertDialogFooter></AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
