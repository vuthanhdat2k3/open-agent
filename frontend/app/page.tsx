"use client";

import { useCurrentRole } from "@/hooks";
import { isOperator, isOrgAdmin, isPlatformAdmin } from "@/lib/roles";
import { PlatformAdminDashboard } from "@/components/dashboard/platform-admin-dashboard";
import { OrgAdminDashboard } from "@/components/dashboard/org-admin-dashboard";
import { OperatorDashboard } from "@/components/dashboard/operator-dashboard";
import { UserDashboard } from "@/components/dashboard/user-dashboard";

export default function Dashboard() {
  const role = useCurrentRole();

  if (isPlatformAdmin(role)) {
    return <PlatformAdminDashboard />;
  }

  if (isOrgAdmin(role)) {
    return <OrgAdminDashboard />;
  }

  if (isOperator(role)) {
    return <OperatorDashboard />;
  }

  return <UserDashboard />;
}
