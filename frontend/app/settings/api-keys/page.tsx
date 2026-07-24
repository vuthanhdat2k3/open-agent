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
      <Card glass>
        <CardContent className="grid gap-3 p-5 md:grid-cols-[1fr_auto]">
          <div className="space-y-1.5">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="automation" />
          </div>
          <Button className="mt-auto" onClick={submit} disabled={!name || create.isPending}>Create key</Button>
        </CardContent>
      </Card>
      {secret && (
        <Card className="border-warning/40 bg-warning/10">
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-sm font-semibold">Copy this secret now. It will not be shown again.</div>
              <code className="break-all text-xs">{secret}</code>
            </div>
            <Button variant="outline" className="gap-2" onClick={() => navigator.clipboard.writeText(secret)}>
              <Copy className="h-4 w-4" /> Copy
            </Button>
          </CardContent>
        </Card>
      )}
      <div className="space-y-2">
        {keys.data?.map((key) => (
          <Card key={key.id} glass>
            <CardContent className="flex items-center justify-between gap-3 p-4">
              <div>
                <div className="text-sm font-semibold">{key.name}</div>
                <div className="font-mono text-xs text-muted-foreground">{key.key_prefix}...</div>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="outline">{key.expires_at ? "expires" : "no expiry"}</Badge>
                <Button size="icon" variant="ghost" onClick={() => revoke.mutate(key.id)}>
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

