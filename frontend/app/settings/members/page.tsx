"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Copy,
  KeyRound,
  Lock,
  Plus,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserPlus,
  Users,
} from "lucide-react";
import {
  useCan,
  useInviteMember,
  useMe,
  useMembers,
  useRemoveMember,
  useApiKeys,
  useCreateApiKey,
  useRevokeApiKey,
  useUrlSearchParam,
} from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { useTranslation, roleLabel } from "@/lib/i18n";
import { ConfirmDialog, EmptyState, ErrorState, LoadingSkeleton, DataPagination } from "@/components/shared";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { getActiveOrgId } from "@/lib/auth";

export default function MembersAndAccessPage() {
  const { t, dict, locale, tx } = useTranslation();
  const [tabParam, setTabParam] = useUrlSearchParam("tab");
  const activeTab = (tabParam as "members" | "keys") || "members";

  const me = useMe();
  const orgId = me.data?.active_org_id || getActiveOrgId() || me.data?.memberships?.[0]?.org_id;
  const members = useMembers(orgId);
  const invite = useInviteMember(orgId);
  const remove = useRemoveMember(orgId);
  const canManage = useCan("orgs:manage");

  // API Keys state
  const keys = useApiKeys(orgId);
  const createKey = useCreateApiKey(orgId);
  const revokeKey = useRevokeApiKey(orgId);
  const [keyName, setKeyName] = React.useState("");
  const [secret, setSecret] = React.useState<string | null>(null);

  // Invite member state
  const [email, setEmail] = React.useState("");
  const [role, setRole] = React.useState("user");
  const [password, setPassword] = React.useState("");

  // Pagination states
  const [memberPage, setMemberPage] = React.useState(1);
  const [memberPageSize, setMemberPageSize] = React.useState(10);
  const paginatedMembers = React.useMemo(() => {
    const start = (memberPage - 1) * memberPageSize;
    return (members.data || []).slice(start, start + memberPageSize);
  }, [members.data, memberPage, memberPageSize]);

  const [keyPage, setKeyPage] = React.useState(1);
  const [keyPageSize, setKeyPageSize] = React.useState(10);
  const paginatedKeys = React.useMemo(() => {
    const start = (keyPage - 1) * keyPageSize;
    return (keys.data || []).slice(start, start + keyPageSize);
  }, [keys.data, keyPage, keyPageSize]);

  async function submitMember(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      await invite.mutateAsync({
        email,
        role,
        initial_password: password.trim() ? password.trim() : undefined,
      });
      toast.success("Member added & provisioned successfully");
      setEmail("");
      setPassword("");
    } catch (error: any) {
      toast.error(error.message || "Unable to add member");
    }
  }

  async function submitKey(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!keyName.trim()) return;
    try {
      const created = await createKey.mutateAsync({ name: keyName.trim() });
      setSecret(created.secret_key);
      setKeyName("");
      toast.success("API key created successfully");
    } catch (error: any) {
      toast.error(error.message || "Failed to create API key");
    }
  }

  const adminCount = members.data?.filter((m) => m.role === "org_admin" || m.role === "admin").length ?? 0;
  const operatorCount = members.data?.filter((m) => m.role === "operator").length ?? 0;
  const userCount = members.data?.filter((m) => m.role === "user").length ?? 0;
  const totalMembers = members.data?.length ?? 0;
  const totalKeys = keys.data?.length ?? 0;

  function canRemoveMember(member: { role: string; user_id: string }): boolean {
    if (member.role === "platform_admin") return false;
    if (me.data?.id === member.user_id) return false;
    const isAdminRole = member.role === "org_admin" || member.role === "admin";
    if (isAdminRole && adminCount <= 1) return false;
    return true;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Users}
        title={dict.pages.members.title}
        description={tx("Manage organization team members, role-based access, and API integration keys.", "Manage organization team members, role-based access, and API integration keys.")}
      />

      {/* 1. Metrics Ribbon */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary">
            <Users className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{totalMembers}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Total Team Members", "Total Team Members")}</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-500/10 text-emerald-500">
            <UserCheck className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{adminCount}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Org Administrators", "Org Administrators")}</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-sky-500/10 text-sky-500">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{operatorCount}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("AI Operators & Builders", "AI Operators & Builders")}</p>
          </div>
        </Card>

        <Card className="flex items-center gap-3.5 p-4 shadow-card">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-500/10 text-amber-500">
            <KeyRound className="h-5 w-5" />
          </div>
          <div>
            <p className="text-2xl font-bold leading-none tabular-nums text-foreground">{totalKeys}</p>
            <p className="mt-1 text-xs text-muted-foreground font-medium">{tx("Active API Keys", "Active API Keys")}</p>
          </div>
        </Card>
      </div>

      {/* 2. Navigation Segmented Tabs */}
      <div className="flex gap-2 border-b border-border/70 pb-2">
        <Button
          type="button"
          variant={activeTab === "members" ? "secondary" : "ghost"}
          onClick={() => setTabParam("members")}
          className="gap-2 font-medium"
        >
          <Users className="h-4 w-4" />
          {tx("Members", "Members")}<Badge variant="outline" className="ml-1 text-[10px] font-mono">
            {totalMembers}
          </Badge>
        </Button>

        <Button
          type="button"
          variant={activeTab === "keys" ? "secondary" : "ghost"}
          onClick={() => setTabParam("keys")}
          className="gap-2 font-medium"
        >
          <KeyRound className="h-4 w-4" />
          {tx("API Keys", "API Keys")}<Badge variant="outline" className="ml-1 text-[10px] font-mono">
            {totalKeys}
          </Badge>
        </Button>
      </div>

      {/* 3. Tab Content */}
      {!canManage ? (
        <ErrorState
          title={tx("Read-only access", "Read-only access")}
          description={tx("Only organization administrators can manage members and access tokens.", "Only organization administrators can manage members and access tokens.")}
        />
      ) : activeTab === "members" ? (
        <div className="space-y-4">
          <Card className="shadow-card border-border/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-foreground">{tx("Add Organization Member", "Add Organization Member")}</CardTitle>
              <CardDescription className="text-xs">
                {tx("Adding a member automatically provisions their account on ZITADEL with the initial password so they can log in immediately.", "Adding a member automatically provisions their account on ZITADEL with the initial password so they can log in immediately.")}</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={submitMember} className="grid gap-4 md:grid-cols-[minmax(0,1.2fr)_160px_160px_auto] md:items-end">
                <div className="space-y-2">
                  <Label htmlFor="member-email" className="text-xs font-medium">{tx("Email Address", "Email Address")}</Label>
                  <Input
                    id="member-email"
                    name="email"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder={tx("teammate@example.com", "teammate@example.com")}
                    required
                    className="text-xs"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="member-role" className="text-xs font-medium">{tx("Role Assignment", "Role Assignment")}</Label>
                  <Select id="member-role" value={role} onChange={(event) => setRole(event.target.value)} className="text-xs">
                    <option value="user">{tx("User (Consumer)", "User (Consumer)")}</option>
                    <option value="operator">{tx("Operator (Builder)", "Operator (Builder)")}</option>
                    <option value="org_admin">{tx("Org Admin", "Org Admin")}</option>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="member-password" className="text-xs font-medium">{tx("Initial Password", "Initial Password")}</Label>
                  <Input
                    id="member-password"
                    name="password"
                    type="text"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder={tx("Default: OpenAgent@2026", "Default: OpenAgent@2026")}
                    className="text-xs font-mono"
                  />
                </div>
                <Button type="submit" className="gap-1.5 font-semibold text-xs h-9" loading={invite.isPending} disabled={!email}>
                  <UserPlus className="h-4 w-4" /> {tx("Add Member", "Add Member")}</Button>
              </form>
            </CardContent>
          </Card>

          {members.isLoading ? (
            <LoadingSkeleton variant="table" />
          ) : members.isError ? (
            <ErrorState
              title={tx("Unable to load members", "Unable to load members")}
              description={tx("Organization member data could not be loaded.", "Organization member data could not be loaded.")}
              onRetry={() => void members.refetch()}
            />
          ) : members.data?.length ? (
            <div className="space-y-4">
              <div className="space-y-2.5">
                {paginatedMembers.map((member) => (
                  <Card key={member.user_id} className="shadow-card border-border/80 p-4 transition-colors hover:border-primary/40">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-primary/20 bg-primary/10 font-semibold text-primary text-xs">
                          {member.email.charAt(0).toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold text-foreground">{member.email}</div>
                          <div className="truncate text-xs text-muted-foreground">{member.display_name || "Active Teammate"}</div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2.5">
                        <Badge variant={member.role === "org_admin" || member.role === "admin" ? "default" : "outline"} className="font-mono text-[10px] uppercase">
                          {roleLabel(member.role, t)}
                        </Badge>
                        {canRemoveMember(member) ? (
                          <ConfirmDialog
                            trigger={
                              <Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-destructive">
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            }
                            title={`Remove ${member.email}?`}
                            description={tx("This member will lose access to the organization immediately.", "This member will lose access to the organization immediately.")}
                            confirmLabel="Remove member"
                            destructive
                            onConfirm={() => remove.mutateAsync(member.user_id).then(() => undefined)}
                          />
                        ) : (
                          <Lock className="h-4 w-4 text-muted-foreground/40" aria-label="Protected member" />
                        )}
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
              <DataPagination
                page={memberPage}
                pageSize={memberPageSize}
                totalItems={members.data.length}
                onPageChange={setMemberPage}
                onPageSizeChange={setMemberPageSize}
                pageSizeOptions={[5, 10, 20, 50]}
              />
            </div>
          ) : (
            <EmptyState
              icon={Users}
              title={tx("No members yet", "No members yet")}
              description={tx("Add a provisioned teammate to collaborate in this organization.", "Add a provisioned teammate to collaborate in this organization.")}
            />
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <Card className="shadow-card border-border/80">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold text-foreground">{tx("Create API Key", "Create API Key")}</CardTitle>
              <CardDescription className="text-xs">
                {tx("API keys allow backend services and external integrations to authenticate on behalf of your organization.", "API keys allow backend services and external integrations to authenticate on behalf of your organization.")}</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={submitKey} className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
                <div className="space-y-2">
                  <Label htmlFor="api-key-name" className="text-xs font-medium">{tx("Integration Name / Key Description", "Integration Name / Key Description")}</Label>
                  <Input
                    id="api-key-name"
                    name="name"
                    value={keyName}
                    onChange={(event) => setKeyName(event.target.value)}
                    placeholder={tx("e.g. n8n-automation-pipeline, zapier-sync, backend-service", "e.g. n8n-automation-pipeline, zapier-sync, backend-service")}
                    required
                    className="text-xs font-mono"
                  />
                </div>
                <Button type="submit" loading={createKey.isPending} disabled={!keyName.trim()} className="gap-1.5 font-semibold text-xs h-9">
                  <Plus className="h-4 w-4" /> {tx("Create API Key", "Create API Key")}</Button>
              </form>
            </CardContent>
          </Card>

          {secret && (
            <Card className="border-amber-500/40 bg-amber-500/10 shadow-card">
              <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-amber-500">{tx("Copy this secret key now", "Copy this secret key now")}</p>
                  <p className="text-xs text-muted-foreground">{tx("For security reasons, this token will never be displayed again.", "For security reasons, this token will never be displayed again.")}</p>
                  <code className="mt-2 block break-all rounded-lg border border-amber-500/30 bg-background/80 p-2 font-mono text-xs font-semibold text-foreground">
                    {secret}
                  </code>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  className="gap-2 shrink-0 border-amber-500/40 bg-amber-500/20 text-xs font-semibold hover:bg-amber-500 hover:text-white"
                  onClick={() => {
                    void navigator.clipboard.writeText(secret);
                    toast.success("API key copied to clipboard");
                  }}
                >
                  <Copy className="h-4 w-4" /> {tx("Copy Secret", "Copy Secret")}</Button>
              </CardContent>
            </Card>
          )}

          {keys.isLoading ? (
            <LoadingSkeleton variant="table" />
          ) : keys.isError ? (
            <ErrorState
              title={tx("Unable to load API keys", "Unable to load API keys")}
              description={tx("Organization API keys could not be loaded.", "Organization API keys could not be loaded.")}
              onRetry={() => void keys.refetch()}
            />
          ) : keys.data?.length ? (
            <div className="space-y-4">
              <div className="space-y-2.5">
                {paginatedKeys.map((key) => (
                  <Card key={key.id} className="shadow-card border-border/80 p-4 transition-colors hover:border-primary/40">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-amber-500/25 bg-amber-500/10 text-amber-500">
                          <KeyRound className="h-4 w-4" />
                        </div>
                        <div className="min-w-0">
                          <div className="truncate text-sm font-semibold text-foreground">{key.name}</div>
                          <div className="font-mono text-xs text-muted-foreground">{key.key_prefix}••••••••</div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2.5">
                        <Badge variant="outline" className="font-mono text-[10px]">
                          {key.expires_at ? "Has Expiry" : "No Expiry"}
                        </Badge>
                        <ConfirmDialog
                          trigger={
                            <Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-destructive">
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          }
                          title={`Revoke API Key ${key.name}?`}
                          description={tx("Any integration using this key will be revoked immediately.", "Any integration using this key will be revoked immediately.")}
                          confirmLabel="Revoke Key"
                          destructive
                          onConfirm={() => revokeKey.mutateAsync(key.id).then(() => undefined)}
                        />
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
              <DataPagination
                page={keyPage}
                pageSize={keyPageSize}
                totalItems={keys.data.length}
                onPageChange={setKeyPage}
                onPageSizeChange={setKeyPageSize}
                pageSizeOptions={[5, 10, 20, 50]}
              />
            </div>
          ) : (
            <EmptyState
              icon={KeyRound}
              title={tx("No API keys configured", "No API keys configured")}
              description={tx("Create an API key to enable external service integrations.", "Create an API key to enable external service integrations.")}
            />
          )}
        </div>
      )}
    </div>
  );
}
