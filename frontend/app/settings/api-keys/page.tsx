"use client";

import * as React from "react";
import { toast } from "sonner";
import { Copy, KeyRound, Trash2 } from "lucide-react";
import { useApiKeys, useCreateApiKey, useMe, useRevokeApiKey } from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { ConfirmDialog, EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { getActiveOrgId } from "@/lib/auth";

export default function ApiKeysPage() {
  const me = useMe();
  const orgId = getActiveOrgId() || me.data?.memberships?.[0]?.org_id;
  const keys = useApiKeys(orgId);
  const create = useCreateApiKey(orgId);
  const revoke = useRevokeApiKey(orgId);
  const [name, setName] = React.useState("");
  const [secret, setSecret] = React.useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try { const created = await create.mutateAsync({ name }); setSecret(created.secret_key); setName(""); toast.success("API key created"); } catch (error: any) { toast.error(error.message); }
  }

  return <div className="space-y-6"><PageHeader icon={KeyRound} title="API Keys" description="Create and revoke organization API keys" /><Card glass><CardContent className="p-5"><form onSubmit={submit} className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-end"><div className="space-y-2"><Label htmlFor="api-key-name">Name</Label><Input id="api-key-name" name="name" value={name} onChange={(event) => setName(event.target.value)} placeholder="automation" required /></div><Button type="submit" loading={create.isPending} disabled={!name}>Create key</Button></form></CardContent></Card>{secret && <Card className="border-warning/40 bg-warning/10"><CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-sm font-semibold text-warning-foreground">Copy this secret now. It will not be shown again.</p><code className="break-all text-sm font-mono font-medium text-foreground">{secret}</code></div><Button type="button" variant="outline" className="gap-2" onClick={() => navigator.clipboard.writeText(secret)}><Copy className="h-4 w-4" aria-hidden="true" />Copy</Button></CardContent></Card>}{keys.isLoading ? <LoadingSkeleton variant="table" /> : keys.isError ? <ErrorState title="Unable to load API keys" description="Organization API keys could not be loaded." onRetry={() => void keys.refetch()} /> : keys.data?.length ? <div className="space-y-3">{keys.data.map((key) => <Card key={key.id} glass><CardContent className="flex items-center justify-between gap-3 p-4"><div className="min-w-0"><div className="truncate text-sm font-semibold text-foreground">{key.name}</div><div className="font-mono text-sm text-muted-foreground">{key.key_prefix}...</div></div><div className="flex items-center gap-2"><Badge variant="outline" className="font-mono text-xs">{key.expires_at ? "expires" : "no expiry"}</Badge><ConfirmDialog trigger={<Button size="icon" variant="ghost" className="h-10 w-10 text-muted-foreground hover:text-destructive" aria-label={`Revoke ${key.name}`}><Trash2 className="h-4 w-4" /></Button>} title={`Revoke ${key.name}?`} description="Any integration using this key will stop working immediately." confirmLabel="Revoke key" destructive onConfirm={() => revoke.mutateAsync(key.id).then(() => undefined)} /></div></CardContent></Card>)}</div> : <EmptyState icon={KeyRound} title="No API keys yet" description="Create an API key for an organization integration." />}</div>;
}
