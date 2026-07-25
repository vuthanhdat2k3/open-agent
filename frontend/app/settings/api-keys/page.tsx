"use client";

import * as React from "react";
import { toast } from "sonner";
import { Copy, KeyRound, Trash2 } from "lucide-react";
import { useApiKeys, useCreateApiKey, useMe, useRevokeApiKey } from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { getActiveOrgId } from "@/lib/auth";

export default function ApiKeysPage() {
  const me = useMe();
  const activeOrgId = getActiveOrgId();
  const orgId = activeOrgId || me.data?.memberships?.[0]?.org_id;
  const keys = useApiKeys(orgId);
  const create = useCreateApiKey(orgId);
  const revoke = useRevokeApiKey(orgId);
  const [name, setName] = React.useState("");
  const [secret, setSecret] = React.useState<string | null>(null);

  async function submit() {
    try {
      const created = await create.mutateAsync({ name });
      setSecret(created.secret_key);
      setName("");
      toast.success("API key created");
    } catch (error: any) {
      toast.error(error.message);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader icon={KeyRound} title="API Keys" description="Create and revoke organization API keys" />
      <Card glass className="shadow-3d-card overflow-hidden">
        <CardContent className="grid gap-3 p-5 md:grid-cols-[1fr_auto]">
          <div className="space-y-1.5">
            <Label className="text-xs uppercase tracking-wider font-semibold text-muted-foreground/80">Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="automation" />
          </div>
          <Button className="mt-auto active-tactile transition-transform" onClick={submit} disabled={!name || create.isPending}>Create key</Button>
        </CardContent>
      </Card>
      {secret && (
        <Card className="border-warning/40 bg-warning/10 shadow-3d-card">
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-sm font-semibold text-warning-foreground">Copy this secret now. It will not be shown again.</div>
              <code className="break-all text-xs font-mono text-foreground font-medium">{secret}</code>
            </div>
            <Button variant="outline" className="gap-2 active-tactile transition-transform" onClick={() => navigator.clipboard.writeText(secret)}>
              <Copy className="h-4 w-4" /> Copy
            </Button>
          </CardContent>
        </Card>
      )}
      <div className="space-y-3 stagger">
        {keys.data?.map((key) => (
          <Card key={key.id} glass className="card-lift">
            <CardContent className="flex items-center justify-between gap-3 p-4">
              <div>
                <div className="text-sm font-semibold text-foreground">{key.name}</div>
                <div className="font-mono text-xs text-muted-foreground">{key.key_prefix}...</div>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="font-mono text-[10px]">{key.expires_at ? "expires" : "no expiry"}</Badge>
                <Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-destructive active-tactile transition-transform" onClick={() => revoke.mutate(key.id)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
