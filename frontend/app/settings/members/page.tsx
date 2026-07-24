"use client";

import * as React from "react";
import { toast } from "sonner";
import { Users, Trash2, UserPlus } from "lucide-react";
import { useInviteMember, useMe, useMembers, useRemoveMember } from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";

import { getActiveOrgId } from "@/lib/auth";

export default function MembersPage() {
  const me = useMe();
  const activeOrgId = getActiveOrgId();
  const orgId = activeOrgId || me.data?.memberships?.[0]?.org_id;
  const members = useMembers(orgId);
  const invite = useInviteMember(orgId);
  const remove = useRemoveMember(orgId);
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState("developer");

  async function submit() {
    try {
      await invite.mutateAsync({ email, role });
      toast.success("Member added");
      setEmail("");
    } catch (error: any) {
      toast.error(error.message);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader icon={Users} title="Members" description="Invite and remove organization members" />
      <Card glass>
        <CardContent className="grid gap-3 p-5 md:grid-cols-[1fr_180px_auto]">
          <div className="space-y-1.5">
            <Label>Email</Label>
            <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@example.com" />
          </div>
          <div className="space-y-1.5">
            <Label>Role</Label>
            <Select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="developer">developer</option>
              <option value="viewer">viewer</option>
              <option value="admin">admin</option>
            </Select>
          </div>
          <Button className="mt-auto gap-2" onClick={submit} disabled={!email || invite.isPending}>
            <UserPlus className="h-4 w-4" /> Add
          </Button>
        </CardContent>
      </Card>
      <div className="space-y-2">
        {members.data?.map((member) => (
          <Card key={member.user_id} glass>
            <CardContent className="flex items-center justify-between gap-3 p-4">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold">{member.email}</div>
                <div className="truncate text-xs text-muted-foreground">{member.display_name}</div>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant="outline">{member.role}</Badge>
                <Button size="icon" variant="ghost" onClick={() => remove.mutate(member.user_id)}>
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

