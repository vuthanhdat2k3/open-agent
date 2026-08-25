"use client";

import * as React from "react";
import { Building2, Plus } from "lucide-react";
import { toast } from "sonner";
import { useCreateOrganization, useOrganizations, useCurrentRole } from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ErrorState, LoadingSkeleton } from "@/components/shared";

export default function OrganizationsPage() {
  const role = useCurrentRole();
  const organizations = useOrganizations(role === "platform_admin");
  const create = useCreateOrganization();
  const [name, setName] = React.useState("");
  const [adminEmail, setAdminEmail] = React.useState("");

  if (role !== "platform_admin") {
    return <ErrorState title="Access denied" description="Only platform administrators can manage organizations." />;
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      await create.mutateAsync({
        name: name.trim(),
        admin_email: adminEmail.trim() ? adminEmail.trim() : undefined,
      });
      setName("");
      setAdminEmail("");
      toast.success("Organization created");
    } catch (error: any) {
      toast.error(error.message || "Unable to create organization");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader icon={Building2} title="Organizations" description="Create and oversee tenant organizations" />
      <Card glass>
        <CardContent className="p-5">
          <form onSubmit={submit} className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
            <div className="space-y-2">
              <Label htmlFor="organization-name">Organization name</Label>
              <Input id="organization-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Acme Corporation" required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="admin-email">Initial Org Admin Email (optional)</Label>
              <Input id="admin-email" type="email" value={adminEmail} onChange={(event) => setAdminEmail(event.target.value)} placeholder="admin@acme.com" />
            </div>
            <Button type="submit" className="gap-2" loading={create.isPending} disabled={!name.trim()}><Plus className="h-4 w-4" />Create organization</Button>
          </form>
        </CardContent>
      </Card>
      {organizations.isLoading ? <LoadingSkeleton variant="table" /> : organizations.isError ? <ErrorState title="Unable to load organizations" description="Organization data could not be loaded." onRetry={() => void organizations.refetch()} /> : (
        <div className="grid gap-3 md:grid-cols-2">
          {organizations.data?.map((organization) => (
            <Card key={organization.id} glass><CardContent className="flex items-center justify-between gap-4 p-5"><div className="min-w-0"><div className="truncate font-semibold">{organization.name}</div><div className="truncate font-mono text-xs text-muted-foreground">{organization.slug}</div></div><Badge variant="outline">active</Badge></CardContent></Card>
          ))}
        </div>
      )}
    </div>
  );
}
