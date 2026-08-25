"use client";

import * as React from "react";
import { Building2, Plus, Users, UserPlus, Trash2, Lock } from "lucide-react";
import { toast } from "sonner";
import { useCreateOrganization, useOrganizations, useCurrentRole, useMembers, useInviteMember, useRemoveMember } from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog, ErrorState, LoadingSkeleton } from "@/components/shared";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import type { Organization } from "@/types";

interface OrgMembersDialogProps {
  organization: Organization;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function OrgMembersDialog({ organization, open, onOpenChange }: OrgMembersDialogProps) {
  const members = useMembers(organization.id);
  const invite = useInviteMember(organization.id);
  const remove = useRemoveMember(organization.id);
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState("org_admin");

  async function handleAddMember(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    try {
      await invite.mutateAsync({ email: email.trim(), role });
      setEmail("");
      toast.success(`Member added to ${organization.name}`);
    } catch (err: any) {
      toast.error(err.message || "Failed to add member");
    }
  }

  const adminCount = members.data?.filter((m) => m.role === "org_admin" || m.role === "admin").length ?? 0;

  function canRemoveMember(member: { role: string; user_id: string }): boolean {
    if (member.role === "platform_admin") return false;
    const isAdminRole = member.role === "org_admin" || member.role === "admin";
    if (isAdminRole && adminCount <= 1) return false;
    return true;
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            Members of {organization.name}
          </DialogTitle>
          <DialogDescription>
            View members, appoint new Org Admins, or manage access for this tenant organization.
          </DialogDescription>
        </DialogHeader>

        {/* Add Member Form */}
        <form onSubmit={handleAddMember} className="grid gap-3 pt-2 sm:grid-cols-[1fr_140px_auto] sm:items-end">
          <div className="space-y-1.5">
            <Label htmlFor="new-member-email" className="text-xs">Email</Label>
            <Input
              id="new-member-email"
              type="email"
              placeholder="admin@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-member-role" className="text-xs">Role</Label>
            <Select id="new-member-role" value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="org_admin">org_admin</option>
              <option value="operator">operator</option>
              <option value="user">user</option>
            </Select>
          </div>
          <Button type="submit" loading={invite.isPending} disabled={!email.trim()} className="gap-1.5">
            <UserPlus className="h-4 w-4" /> Add
          </Button>
        </form>

        {/* Current Members List */}
        <div className="mt-3 space-y-2 border-t pt-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Current Members</h4>
          {members.isLoading ? (
            <LoadingSkeleton variant="table" />
          ) : members.isError ? (
            <ErrorState title="Unable to load members" description="Could not load member list." onRetry={() => void members.refetch()} />
          ) : members.data?.length ? (
            <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
              {members.data.map((m) => (
                <div key={m.user_id} className="flex items-center justify-between gap-3 rounded-lg border border-border/50 bg-background/60 p-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{m.email}</div>
                    <div className="truncate text-xs text-muted-foreground">{m.display_name}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="font-mono text-xs uppercase">{m.role}</Badge>
                    {canRemoveMember(m) ? (
                      <ConfirmDialog
                        trigger={
                          <Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-destructive" aria-label={`Remove ${m.email}`}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        }
                        title={`Remove ${m.email}?`}
                        description="This member will lose access to the organization."
                        confirmLabel="Remove member"
                        destructive
                        onConfirm={() => remove.mutateAsync(m.user_id).then(() => undefined)}
                      />
                    ) : (
                      <Lock className="h-4 w-4 text-muted-foreground/40" aria-label="Protected member" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">No members found.</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function OrganizationsPage() {
  const role = useCurrentRole();
  const organizations = useOrganizations(role === "platform_admin");
  const create = useCreateOrganization();
  const [name, setName] = React.useState("");
  const [adminEmail, setAdminEmail] = React.useState("");
  const [selectedOrg, setSelectedOrg] = React.useState<Organization | null>(null);

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
            <Card key={organization.id} glass>
              <CardContent className="flex items-center justify-between gap-4 p-5">
                <div className="min-w-0">
                  <div className="truncate font-semibold">{organization.name}</div>
                  <div className="truncate font-mono text-xs text-muted-foreground">{organization.slug}</div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1.5 text-xs"
                    onClick={() => setSelectedOrg(organization)}
                  >
                    <Users className="h-3.5 w-3.5" />
                    Members
                  </Button>
                  <Badge variant="outline">active</Badge>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {selectedOrg && (
        <OrgMembersDialog
          organization={selectedOrg}
          open={!!selectedOrg}
          onOpenChange={(open) => {
            if (!open) setSelectedOrg(null);
          }}
        />
      )}
    </div>
  );
}
