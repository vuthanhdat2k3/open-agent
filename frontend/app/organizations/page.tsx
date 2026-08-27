"use client";

import * as React from "react";
import { Building2, Plus, Users, UserPlus, Trash2, Lock, Pencil } from "lucide-react";
import { toast } from "sonner";
import { useCreateOrganization, useOrganizations, useCurrentRole, useMembers, useInviteMember, useRemoveMember, useRenameOrganization, useDeleteOrganization } from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { useTranslation } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog, ErrorState, LoadingSkeleton, DataPagination } from "@/components/shared";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import type { Organization } from "@/types";

interface OrgMembersDialogProps {
  organization: Organization;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function OrgMembersDialog({ organization, open, onOpenChange }: OrgMembersDialogProps) {
  const { locale } = useTranslation();
  const members = useMembers(organization.id);
  const invite = useInviteMember(organization.id);
  const remove = useRemoveMember(organization.id);
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");

  async function handleAddMember(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    try {
      await invite.mutateAsync({
        email: email.trim(),
        role: "org_admin",
        initial_password: password.trim() ? password.trim() : undefined,
      });
      setEmail("");
      setPassword("");
      toast.success(`Org Admin appointed for ${organization.name}`);
    } catch (err: any) {
      toast.error(err.message || "Failed to appoint Org Admin");
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
            {locale === "vi" ? "Org Admins of" : "Org Admins of"}{organization.name}
          </DialogTitle>
          <DialogDescription>{locale === "vi" ? "Bổ nhiệm hoặc quản lý Org Admins cho tenant này. Org Admins sẽ tự quản lý operator và người dùng của họ." : "Appoint or manage Org Admins for this tenant. Org Admins will manage their own operators and users."}</DialogDescription>
        </DialogHeader>

        {/* Add Member Form - Fixed to org_admin */}
        <form onSubmit={handleAddMember} className="grid gap-3 pt-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <div className="space-y-1.5">
            <Label htmlFor="new-member-email" className="text-xs">{locale === "vi" ? "Email Quản trị" : "Admin Email"}</Label>
            <Input
              id="new-member-email"
              type="email"
              placeholder={locale === "vi" ? "admin@example.com" : "admin@example.com"}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-member-password" className="text-xs">{locale === "vi" ? "Mật khẩu ban đầu (tùy chọn)" : "Initial Password (optional)"}</Label>
            <Input
              id="new-member-password"
              type="text"
              placeholder={locale === "vi" ? "Mặc định: OpenAgent@2026" : "Default: OpenAgent@2026"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <Button type="submit" size="sm" className="gap-1.5" loading={invite.isPending}>
            <UserPlus className="h-4 w-4" />{locale === "vi" ? "Thêm Quản trị viên" : "Add Admin"}</Button>
        </form>

        {/* Members List */}
        <div className="space-y-2 pt-3 border-t border-border">
          <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            {locale === "vi" ? "Current Admins (" : "Current Admins ("}{members.data?.length ?? 0})
          </Label>
          {members.isLoading ? (
            <LoadingSkeleton variant="table" />
          ) : members.data && members.data.length > 0 ? (
            <div className="divide-y divide-border rounded-md border border-border">
              {members.data.map((m: any) => (
                <div key={m.user_id} className="flex items-center justify-between p-3 text-sm">
                  <div className="min-w-0 space-y-0.5">
                    <p className="font-medium truncate">{m.email}</p>
                    <div className="flex items-center gap-2">
                      <Badge variant={m.role === "platform_admin" ? "default" : "outline"} className="text-xs">
                        {m.role}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {locale === "vi" ? "Joined" : "Joined"}{new Date(m.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {canRemoveMember(m) ? (
                      <ConfirmDialog
                        trigger={
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive hover:bg-destructive/10 hover:text-destructive h-8 w-8 p-0"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        }
                        title={locale === "vi" ? "Xóa Quản trị viên" : "Remove Admin"}
                        description={`Remove ${m.email} from ${organization.name}?`}
                        confirmLabel={locale === "vi" ? "Xóa" : "Remove"}
                        destructive
                        onConfirm={async () => {
                          try {
                            await remove.mutateAsync(m.user_id);
                            toast.success(`Removed ${m.email}`);
                          } catch (err: any) {
                            toast.error(err.message || "Failed to remove member");
                          }
                        }}
                      />
                    ) : (
                      <span className="text-xs text-muted-foreground italic flex items-center gap-1">
                        <Lock className="h-3 w-3" />{locale === "vi" ? "Được bảo vệ" : "Protected"}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">{locale === "vi" ? "Không tìm thấy thành viên." : "No members found."}</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function OrganizationsPage() {
  const { t, dict, locale } = useTranslation();
  const role = useCurrentRole();
  const organizations = useOrganizations(role === "platform_admin");
  const create = useCreateOrganization();
  const rename = useRenameOrganization();
  const remove = useDeleteOrganization();
  const [name, setName] = React.useState("");
  const [adminEmail, setAdminEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [selectedOrg, setSelectedOrg] = React.useState<Organization | null>(null);
  const [renameOrg, setRenameOrg] = React.useState<Organization | null>(null);
  const [renameValue, setRenameValue] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(10);

  const paginatedOrgs = React.useMemo(() => {
    const start = (page - 1) * pageSize;
    return (organizations.data || []).slice(start, start + pageSize);
  }, [organizations.data, page, pageSize]);

  if (role !== "platform_admin") {
    return <ErrorState title={locale === "vi" ? "Truy cập bị từ chối" : "Access denied"} description={locale === "vi" ? "Chỉ có quản trị viên nền tảng mới có thể quản lý các tổ chức." : "Only platform administrators can manage organizations."} />;
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      await create.mutateAsync({
        name: name.trim(),
        admin_email: adminEmail.trim() ? adminEmail.trim() : undefined,
        initial_password: password.trim() ? password.trim() : undefined,
      });
      setName("");
      setAdminEmail("");
      setPassword("");
      toast.success(locale === "vi" ? "Đã tạo tổ chức" : "Organization created");
    } catch (error: any) {
      toast.error(error.message || "Unable to create organization");
    }
  }

  async function submitRename(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!renameOrg || !renameValue.trim()) return;
    try {
      await rename.mutateAsync({ orgId: renameOrg.id, name: renameValue.trim() });
      setRenameOrg(null);
      toast.success(dict.pages.organizations.renamed);
    } catch (error: any) {
      toast.error(error.message || "Unable to rename organization");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Building2}
        title={dict.pages.organizations.title}
        description={locale === "vi" ? "Tạo, cấp phép và giám sát các tổ chức tenant và quản trị viên ban đầu." : "Create, provision, and oversee tenant organizations and initial administrators."}
      />
      <Card glass>
        <CardContent className="p-5">
          <form onSubmit={submit} className="grid gap-4 md:grid-cols-[1fr_1fr_1fr_auto] md:items-end">
            <div className="space-y-2">
              <Label htmlFor="organization-name">{locale === "vi" ? "Tên tổ chức" : "Organization name"}</Label>
              <Input id="organization-name" value={name} onChange={(event) => setName(event.target.value)} placeholder={locale === "vi" ? "Acme Corporation" : "Acme Corporation"} required />
            </div>
            <div className="space-y-2">
              <Label htmlFor="admin-email">{locale === "vi" ? "Email Org Admin ban đầu (tùy chọn)" : "Initial Org Admin Email (optional)"}</Label>
              <Input id="admin-email" type="email" value={adminEmail} onChange={(event) => setAdminEmail(event.target.value)} placeholder={locale === "vi" ? "admin@acme.com" : "admin@acme.com"} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="admin-password">{locale === "vi" ? "Mật khẩu ban đầu (tùy chọn)" : "Initial Password (optional)"}</Label>
              <Input id="admin-password" type="text" value={password} onChange={(event) => setPassword(event.target.value)} placeholder={locale === "vi" ? "Mặc định: OpenAgent@2026" : "Default: OpenAgent@2026"} />
            </div>
            <Button type="submit" className="gap-2" loading={create.isPending} disabled={!name.trim()}><Plus className="h-4 w-4" />{locale === "vi" ? "Tạo tổ chức" : "Create organization"}</Button>
          </form>
        </CardContent>
      </Card>
      {organizations.isLoading ? <LoadingSkeleton variant="table" /> : organizations.isError ? <ErrorState title={locale === "vi" ? "Không thể tải tổ chức" : "Unable to load organizations"} description={locale === "vi" ? "Dữ liệu tổ chức không thể được tải." : "Organization data could not be loaded."} onRetry={() => void organizations.refetch()} /> : (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            {paginatedOrgs.map((organization) => (
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
                      <Users className="h-3.5 w-3.5" />{locale === "vi" ? "Thành viên" : "Members"}</Button>
                    {organization.slug !== "platform" && <>
                      <Button size="sm" variant="ghost" className="h-8 w-8 p-0" aria-label={dict.pages.organizations.rename} onClick={() => { setRenameOrg(organization); setRenameValue(organization.name); }}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <ConfirmDialog
                        trigger={<Button size="sm" variant="ghost" className="h-8 w-8 p-0 text-destructive hover:bg-destructive/10 hover:text-destructive" aria-label={dict.pages.organizations.delete}><Trash2 className="h-3.5 w-3.5" /></Button>}
                        title={dict.pages.organizations.deleteTitle}
                        description={`${dict.pages.organizations.deleteDescription} (${organization.name})`}
                        confirmLabel={dict.pages.organizations.delete}
                        destructive
                        loading={remove.isPending}
                        onConfirm={async () => { try { await remove.mutateAsync(organization.id); toast.success(dict.pages.organizations.deleted); } catch (error: any) { toast.error(error.message || "Unable to delete organization"); } }}
                      />
                    </>}
                    <Badge variant="outline">{locale === "vi" ? "hoạt động" : "active"}</Badge>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          <DataPagination
            page={page}
            pageSize={pageSize}
            totalItems={organizations.data?.length ?? 0}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
            pageSizeOptions={[6, 10, 20, 50]}
          />
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
      <Dialog open={!!renameOrg} onOpenChange={(open) => { if (!open) setRenameOrg(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{dict.pages.organizations.renameTitle}</DialogTitle>
            <DialogDescription>{renameOrg?.name}</DialogDescription>
          </DialogHeader>
          <form onSubmit={submitRename} className="space-y-4">
            <div className="space-y-2"><Label htmlFor="rename-organization-name">{dict.pages.organizations.orgName}</Label><Input id="rename-organization-name" value={renameValue} onChange={(event) => setRenameValue(event.target.value)} maxLength={128} required /></div>
            <Button type="submit" className="w-full" loading={rename.isPending} disabled={!renameValue.trim()}>{dict.pages.organizations.rename}</Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
