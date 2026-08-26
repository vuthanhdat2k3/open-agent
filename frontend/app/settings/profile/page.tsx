"use client";

import * as React from "react";
import { toast } from "sonner";
import { User, Shield, Building2, KeyRound } from "lucide-react";
import { useProfile, useUpdateProfile } from "@/hooks";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/page-header";
import { useTranslation } from "@/lib/i18n";
import { ErrorState } from "@/components/shared";

export default function ProfilePage() {
  const { t, dict, locale } = useTranslation();
  const profile = useProfile();
  const updateProfile = useUpdateProfile();

  const [displayName, setDisplayName] = React.useState("");
  const [oldPassword, setOldPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");

  React.useEffect(() => {
    if (profile.data?.display_name) {
      setDisplayName(profile.data.display_name);
    }
  }, [profile.data]);

  async function handleUpdateProfile(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateProfile.mutateAsync({ display_name: displayName });
      toast.success(locale === "vi" ? "Cập nhật hồ sơ thành công" : "Profile updated successfully");
    } catch (err: any) {
      toast.error(err.message || (locale === "vi" ? "Cập nhật hồ sơ thất bại" : "Failed to update profile"));
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      toast.error(locale === "vi" ? "Mật khẩu mới không khớp" : "New passwords do not match");
      return;
    }
    if (newPassword.length < 6) {
      toast.error(locale === "vi" ? "Mật khẩu mới phải có ít nhất 6 ký tự" : "New password must be at least 6 characters");
      return;
    }
    try {
      await updateProfile.mutateAsync({
        old_password: oldPassword,
        new_password: newPassword,
      });
      toast.success(locale === "vi" ? "Đổi mật khẩu thành công" : "Password changed successfully");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      toast.error(err.message || (locale === "vi" ? "Đổi mật khẩu thất bại" : "Failed to change password"));
    }
  }

  if (profile.isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader icon={User} title={dict.pages.profile.title} description={locale === "vi" ? "Quản lý hồ sơ tài khoản và bảo mật của bạn" : "Manage your account profile and security"} />
        <Skeleton className="h-48 w-full rounded-xl" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    );
  }

  const user = profile.data;

  return (
    <div className="space-y-6">
      <PageHeader icon={User} title={locale === "vi" ? "Hồ sơ" : "Profile"} description={locale === "vi" ? "Quản lý hồ sơ tài khoản và bảo mật của bạn" : "Manage your account profile and security"} />

      <div className="grid gap-6 md:grid-cols-2">
        {/* Profile Info Card */}
        <Card glass>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary">
                <User className="h-5 w-5" />
              </div>
              <div>
                <CardTitle>{locale === "vi" ? "Thông tin cá nhân" : "Personal Info"}</CardTitle>
                <CardDescription>{locale === "vi" ? "Cập nhật tên hiển thị và xem chi tiết tài khoản" : "Update your display name and view account details"}</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleUpdateProfile} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="profile-email">{locale === "vi" ? "Email" : "Email"}</Label>
                <Input id="profile-email" value={user?.email || ""} disabled className="bg-muted/50" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="profile-display-name">{locale === "vi" ? "Tên hiển thị" : "Display Name"}</Label>
                <Input
                  id="profile-display-name"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder={locale === "vi" ? "Tên hiển thị của bạn" : "Your display name"}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="profile-created">{locale === "vi" ? "Tài khoản được tạo" : "Account Created"}</Label>
                <Input
                  id="profile-created"
                  value={user?.created_at ? new Date(user.created_at).toLocaleDateString() : ""}
                  disabled
                  className="bg-muted/50"
                />
              </div>
              <Button type="submit" disabled={updateProfile.isPending}>
                {updateProfile.isPending ? (locale === "vi" ? "Đang lưu..." : "Saving...") : (locale === "vi" ? "Lưu thay đổi" : "Save Changes")}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Security / Password Card */}
        <Card glass>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary">
                <KeyRound className="h-5 w-5" />
              </div>
              <div>
                <CardTitle>{locale === "vi" ? "Đổi mật khẩu" : "Change Password"}</CardTitle>
                <CardDescription>{locale === "vi" ? "Đảm bảo tài khoản của bạn đang sử dụng mật khẩu dài, ngẫu nhiên" : "Ensure your account is using a long, random password"}</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleChangePassword} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="profile-current-password">{locale === "vi" ? "Mật khẩu hiện tại" : "Current Password"}</Label>
                <Input
                  id="profile-current-password"
                  type="password"
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="profile-new-password">{locale === "vi" ? "Mật khẩu mới" : "New Password"}</Label>
                <Input
                  id="profile-new-password"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="profile-confirm-password">{locale === "vi" ? "Xác nhận mật khẩu mới" : "Confirm New Password"}</Label>
                <Input
                  id="profile-confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                />
              </div>
              <Button type="submit" variant="secondary" disabled={updateProfile.isPending}>
                {updateProfile.isPending ? (locale === "vi" ? "Đang cập nhật..." : "Updating...") : (locale === "vi" ? "Cập nhật mật khẩu" : "Update Password")}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>

      {/* Organizations Card */}
      <Card glass>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary">
              <Building2 className="h-5 w-5" />
            </div>
            <div>
              <CardTitle>{locale === "vi" ? "Tổ chức & Vai trò" : "Organizations & Roles"}</CardTitle>
              <CardDescription>{locale === "vi" ? "Các tổ chức bạn hiện đang là thành viên" : "Organizations you are currently a member of"}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="divide-y divide-border rounded-lg border border-border">
            {user?.memberships.map((mem) => (
              <div key={mem.org_id} className="flex items-center justify-between p-4">
                <div className="space-y-1">
                  <div className="font-semibold">{mem.org_name}</div>
                  <div className="text-xs text-muted-foreground">{locale === "vi" ? "ID:" : "ID:"}{mem.org_id}</div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="capitalize">
                    <Shield className="mr-1 h-3 w-3" />
                    {mem.role}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
