"use client";

import * as React from "react";
import { toast } from "sonner";
import { UserPlus, Trash2, Users, Lock } from "lucide-react";
import { useCan, useInviteMember, useMe, useMembers, useRemoveMember } from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { ConfirmDialog, EmptyState, ErrorState, LoadingSkeleton } from "@/components/shared";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { getActiveOrgId } from "@/lib/auth";

export default function MembersPage() {
  const me = useMe();
  const orgId = me.data?.active_org_id || getActiveOrgId() || me.data?.memberships?.[0]?.org_id;
  const members = useMembers(orgId);
  const invite = useInviteMember(orgId);
  const remove = useRemoveMember(orgId);
  const canManage = useCan("orgs:manage");
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState("user");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await invite.mutateAsync({ email, role });
      toast.success("Member added");
      setEmail("");
    } catch (error: any) {
      toast.error(error.message || "Unable to add member");
    }
  }

  const adminCount = members.data?.filter((m) => m.role === "org_admin" || m.role === "admin").length ?? 0;
  function canRemoveMember(member: { role: string; user_id: string }): boolean {
    if (member.role === "platform_admin") return false;
    if (me.data?.id === member.user_id) return false;
    const isAdminRole = member.role === "org_admin" || member.role === "admin";
    if (isAdminRole && adminCount <= 1) return false;
    return true;
  }

  return (
    <div className="space-y-6">
      <PageHeader icon={Users} title="Members & roles" description="Manage access in the active organization" />
      {!canManage ? <ErrorState title="Read-only access" description="Only organization administrators can manage members and roles." /> : <>
        <Card glass><CardContent className="space-y-4 p-5"><p className="text-sm text-muted-foreground">Add the email first. The user must then be created by an administrator in ZITADEL and sign in through SSO; the first verified login activates this membership.</p><form onSubmit={submit} className="grid gap-4 md:grid-cols-[minmax(0,1fr)_180px_auto] md:items-end">
          <div className="space-y-2"><Label htmlFor="member-email">Email</Label><Input id="member-email" name="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="teammate@example.com" required /></div>
          <div className="space-y-2"><Label htmlFor="member-role">Role</Label><Select id="member-role" value={role} onChange={(event) => setRole(event.target.value)}><option value="user">user</option><option value="operator">operator</option><option value="org_admin">org_admin</option></Select></div>
          <Button type="submit" className="gap-2" loading={invite.isPending} disabled={!email}><UserPlus className="h-4 w-4" aria-hidden="true" />Add member</Button>
        </form></CardContent></Card>
        {members.isLoading ? <LoadingSkeleton variant="table" /> : members.isError ? <ErrorState title="Unable to load members" description="Organization member data could not be loaded." onRetry={() => void members.refetch()} /> : members.data?.length ? <div className="space-y-3">{members.data.map((member) => <Card key={member.user_id} glass><CardContent className="flex items-center justify-between gap-3 p-4"><div className="min-w-0"><div className="truncate text-sm font-semibold text-foreground">{member.email}</div><div className="truncate text-sm text-muted-foreground">{member.display_name}</div></div><div className="flex items-center gap-2"><Badge variant="outline" className="font-mono text-xs uppercase">{member.role}</Badge>{canRemoveMember(member) ? <ConfirmDialog trigger={<Button size="icon" variant="ghost" className="h-10 w-10 text-muted-foreground hover:text-destructive" aria-label={`Remove ${member.email}`}><Trash2 className="h-4 w-4" /></Button>} title={`Remove ${member.email}?`} description="This member will lose access to the organization. This action cannot be undone." confirmLabel="Remove member" destructive onConfirm={() => remove.mutateAsync(member.user_id).then(() => undefined)} /> : <Lock className="h-4 w-4 text-muted-foreground/40" aria-label={`${member.email} is a protected member`} />}</div></CardContent></Card>)}</div> : <EmptyState icon={Users} title="No members yet" description="Add a provisioned teammate to collaborate in this organization." />}
      </>}
    </div>
  );
}
