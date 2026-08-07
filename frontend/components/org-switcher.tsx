"use client";

import * as React from "react";
import { Building2, Check, ChevronDown } from "lucide-react";
import { useMe } from "@/hooks";
import { setAccessToken } from "@/lib/auth";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

export function OrgSwitcher({ collapsed }: { collapsed?: boolean }) {
  const me = useMe();
  const memberships = me.data?.memberships ?? [];
  const [selectedOrgId, setSelectedOrgId] = React.useState<string | null>(null);
  const activeOrgId = selectedOrgId || memberships[0]?.org_id;
  const currentMembership = memberships.find((membership) => membership.org_id === activeOrgId) || memberships[0];
  if (!currentMembership) return null;

  async function switchOrg(orgId: string) {
    setSelectedOrgId(orgId);
    try {
      const res = await api.post<{ access_token: string }>("/api/auth/switch-org", { org_id: orgId });
      if (res.access_token) setAccessToken(res.access_token);
      window.location.reload();
    } catch {
      localStorage.setItem("active_org_id", orgId);
      window.location.reload();
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className={collapsed ? "h-10 w-10 justify-center p-0" : "w-full justify-between gap-2 px-3"} aria-label={`Active organization: ${currentMembership.org_name || currentMembership.org_id}`}>
          <span className="flex min-w-0 items-center gap-2"><Building2 className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />{!collapsed && <span className="truncate text-xs font-semibold">{currentMembership.org_name || currentMembership.org_id.slice(0, 8)}</span>}</span>
          {!collapsed && <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" aria-hidden="true" />}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60">
        <DropdownMenuLabel>Switch organization</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {memberships.map((membership) => <DropdownMenuItem key={membership.org_id} onSelect={() => void switchOrg(membership.org_id)} className="gap-3"><span className="min-w-0 flex-1 truncate">{membership.org_name || membership.org_id}</span><span className="text-[10px] uppercase text-muted-foreground">{membership.role}</span>{membership.org_id === activeOrgId && <Check className="h-4 w-4 shrink-0 text-primary" aria-label="Active organization" />}</DropdownMenuItem>)}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
