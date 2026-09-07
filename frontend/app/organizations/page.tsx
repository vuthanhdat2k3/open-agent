"use client";

import * as React from "react";
import { Building2, Plus, Users, UserPlus, Trash2, Lock, Pencil } from "lucide-react";
import { toast } from "sonner";
import { useCreateOrganization, useOrganizations, useCurrentRole, useMembers, useInviteMember, useRemoveMember, useRenameOrganization, useDeleteOrganization } from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { useTranslation, roleLabel } from "@/lib/i18n";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog, ErrorState, LoadingSkeleton, DataPagination, PasswordComplexityIndicator } from "@/components/shared";
import { validateZitadelPassword } from "@/lib/password";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import type { Organization } from "@/types";
import { isOrgAdmin } from "@/lib/roles";

interface OrgMembersDialogProps {
  organization: Organization;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function OrgMembersDialog({ organization, open, onOpenChange }: OrgMembersDialogProps) {
  const { locale, tx, t } = useTranslation();
  const members = useMembers(organization.id);
  const invite = useInviteMember(organization.id);
  const remove = useRemoveMember(organization.id);
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");

  async function handleAddMember(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    const trimmedPass = password.trim();
    if (trimmedPass && !validateZitadelPassword(trimmedPass).isValid) {
      toast.error(
        tx(
          "Mật khẩu cần tối thiểu 8 ký tự, bao gồm chữ hoa, chữ thường, số và ký tự đặc biệt.",
          "Password requires min 8 chars with uppercase, lowercase, number, and symbol."
        )
      );
      return;
    }
    try {
      await invite.mutateAsync({
        email: email.trim(),
        role: "org_admin",
        initial_password: trimmedPass ? trimmedPass : undefined,
      });
      setEmail("");
      setPassword("");
      toast.success(tx(`Đã bổ nhiệm Quản trị viên cho ${organization.name}`, `Org Admin appointed for ${organization.name}`));
    } catch (err: any) {
      toast.error(err.message || tx("Không thể bổ nhiệm Quản trị viên", "Failed to appoint Org Admin"));
    }
  }

  const adminCount = members.data?.filter((m) => isOrgAdmin(m.role)).length ?? 0;

  function canRemoveMember(member: { role: string; user_id: string }): boolean {
    if (member.role === "platform_admin") return false;
    if (isOrgAdmin(member.role) && adminCount <= 1) return false;
    return true;
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            {tx("Quản trị viên của", "Org Admins of")}{organization.name}
          </DialogTitle>
          <DialogDescription>{tx("Bổ nhiệm hoặc quản lý Org Admins cho tenant này. Org Admins sẽ tự quản lý operator và người dùng của họ.", "Appoint or manage Org Admins for this tenant. Org Admins will manage their own operators and users.")}</DialogDescription>
        </DialogHeader>

        {/* Add Member Form - Fixed to org_admin */}
        <form onSubmit={handleAddMember} className="space-y-3 pt-2">
          <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <div className="space-y-1.5">
              <Label htmlFor="new-member-email" className="text-xs">{tx("Email Quản trị", "Admin Email")}</Label>
              <Input
                id="new-member-email"
                type="email"
                placeholder={tx("admin@example.com", "admin@example.com")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="new-member-password" className="text-xs">{tx("Mật khẩu ban đầu (tùy chọn)", "Initial Password (optional)")}</Label>
              <Input
                id="new-member-password"
                type="text"
                placeholder={tx("Mặc định: OpenAgent@2026", "Default: OpenAgent@2026")}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <Button type="submit" size="sm" className="gap-1.5" loading={invite.isPending}>
              <UserPlus className="h-4 w-4" />{tx("Thêm Quản trị viên", "Add Admin")}</Button>
          </div>
          <PasswordComplexityIndicator password={password} />
        </form>

        {/* Members List */}
        <div className="space-y-2 pt-3 border-t border-border">
          <Label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            {tx("Quản trị hiện tại (", "Current Admins (")}{members.data?.length ?? 0})
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
                        {roleLabel(m.role, t)}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {tx("Đã tham gia", "Joined")}{new Date(m.created_at).toLocaleDateString()}
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
                        title={tx("Xóa Quản trị viên", "Remove Admin")}
                        description={tx(`Xóa ${m.email} khỏi ${organization.name}?`, `Remove ${m.email} from ${organization.name}?`)}
                        confirmLabel={tx("Xóa", "Remove")}
                        destructive
                        onConfirm={async () => {
                          try {
                            await remove.mutateAsync(m.user_id);
                            toast.success(tx(`Đã xóa ${m.email}`, `Removed ${m.email}`));
                          } catch (err: any) {
                            toast.error(err.message || tx("Không thể xóa thành viên", "Failed to remove member"));
                          }
                        }}
                      />
                    ) : (
                      <span className="text-xs text-muted-foreground italic flex items-center gap-1">
                        <Lock className="h-3 w-3" />{tx("Được bảo vệ", "Protected")}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">{tx("Không tìm thấy thành viên.", "No members found.")}</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function OrganizationsPage() {
  const { t, dict, locale, tx } = useTranslation();
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
    return <ErrorState title={tx("Truy cập bị từ chối", "Access denied")} description={tx("Chỉ có quản trị viên nền tảng mới có thể quản lý các tổ chức.", "Only platform administrators can manage organizations.")} />;
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    const trimmedPass = password.trim();
    if (trimmedPass && !validateZitadelPassword(trimmedPass).isValid) {
      toast.error(
        tx(
          "Mật khẩu cần tối thiểu 8 ký tự, bao gồm chữ hoa, chữ thường, số và ký tự đặc biệt.",
          "Password requires min 8 chars with uppercase, lowercase, number, and symbol."
        )
      );
      return;
    }
    try {
      await create.mutateAsync({
        name: name.trim(),
        admin_email: adminEmail.trim() ? adminEmail.trim() : undefined,
        initial_password: trimmedPass ? trimmedPass : undefined,
      });
      setName("");
      setAdminEmail("");
      setPassword("");
      toast.success(tx("Đã tạo tổ chức", "Organization created"));
    } catch (error: any) {
      toast.error(error.message || tx("Không thể tạo tổ chức", "Unable to create organization"));
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
      toast.error(error.message || tx("Không thể đổi tên tổ chức", "Unable to rename organization"));
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Building2}
        title={dict.pages.organizations.title}
        description={tx("Tạo, cấp phép và giám sát các tổ chức tenant và quản trị viên ban đầu.", "Create, provision, and oversee tenant organizations and initial administrators.")}
      />
      <Card glass>
        <CardContent className="p-5">
          <form onSubmit={submit} className="space-y-4">
            <div className="grid gap-4 md:grid-cols-[1fr_1fr_1fr_auto] md:items-end">
              <div className="space-y-2">
                <Label htmlFor="organization-name">{tx("Tên tổ chức", "Organization name")}</Label>
                <Input id="organization-name" value={name} onChange={(event) => setName(event.target.value)} placeholder={tx("Acme Corporation", "Acme Corporation")} required />
              </div>
              <div className="space-y-2">
                <Label htmlFor="admin-email">{tx("Email Org Admin ban đầu (tùy chọn)", "Initial Org Admin Email (optional)")}</Label>
                <Input id="admin-email" type="email" value={adminEmail} onChange={(event) => setAdminEmail(event.target.value)} placeholder={tx("admin@acme.com", "admin@acme.com")} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="admin-password">{tx("Mật khẩu ban đầu (tùy chọn)", "Initial Password (optional)")}</Label>
                <Input id="admin-password" type="text" value={password} onChange={(event) => setPassword(event.target.value)} placeholder={tx("Mặc định: OpenAgent@2026", "Default: OpenAgent@2026")} />
              </div>
              <Button type="submit" className="gap-2" loading={create.isPending} disabled={!name.trim()}><Plus className="h-4 w-4" />{tx("Tạo tổ chức", "Create organization")}</Button>
            </div>
            <PasswordComplexityIndicator password={password} />
          </form>
        </CardContent>
      </Card>
      {organizations.isLoading ? <LoadingSkeleton variant="table" /> : organizations.isError ? <ErrorState title={tx("Không thể tải tổ chức", "Unable to load organizations")} description={tx("Dữ liệu tổ chức không thể được tải.", "Organization data could not be loaded.")} onRetry={() => void organizations.refetch()} /> : (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            {paginatedOrgs.map((organization) => (
              <Card key={organization.id} glass>
                <CardContent className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
                  <div className="min-w-0">
                    <div className="truncate font-semibold">{organization.name}</div>
                    <div className="truncate font-mono text-xs text-muted-foreground">{organization.slug}</div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1.5 text-xs"
                      onClick={() => setSelectedOrg(organization)}
                    >
                      <Users className="h-3.5 w-3.5" />{tx("Thành viên", "Members")}</Button>
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
                        onConfirm={async () => { try { await remove.mutateAsync(organization.id); toast.success(dict.pages.organizations.deleted); } catch (error: any) { toast.error(error.message || tx("Không thể xóa tổ chức", "Unable to delete organization")); } }}
                      />
                    </>}
                    <Badge variant="outline">{tx("hoạt động", "active")}</Badge>
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
