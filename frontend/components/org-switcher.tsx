"use client";

import * as React from "react";
import { Building2, Check, ChevronDown } from "lucide-react";
import { useMe } from "@/hooks";
import { setAccessToken } from "@/lib/auth";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function OrgSwitcher({ collapsed }: { collapsed?: boolean }) {
  const me = useMe();
  const memberships = me.data?.memberships ?? [];
  const [selectedOrgId, setSelectedOrgId] = React.useState<string | null>(null);
  const [open, setOpen] = React.useState(false);

  const activeOrgId = selectedOrgId || memberships[0]?.org_id;
  const currentMembership = memberships.find((m) => m.org_id === activeOrgId) || memberships[0];

  async function switchOrg(orgId: string) {
    setSelectedOrgId(orgId);
    setOpen(false);
    try {
      const res = await api.post<{ access_token: string }>(`/api/auth/switch-org`, { org_id: orgId });
      if (res.access_token) {
        setAccessToken(res.access_token);
        window.location.reload();
      }
    } catch {
      localStorage.setItem("active_org_id", orgId);
      window.location.reload();
    }
  }

  if (!currentMembership) return null;

  return (
    <div className="relative">
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen((o) => !o)}
        className={collapsed ? "h-9 w-9 p-0 justify-center" : "w-full justify-between gap-2 px-3"}
      >
        <div className="flex items-center gap-2 truncate">
          <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
          {!collapsed && (
            <span className="truncate text-xs font-semibold">
              {currentMembership.org_name || currentMembership.org_id.slice(0, 8)}
            </span>
          )}
        </div>
        {!collapsed && <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-50" />}
      </Button>

      {open && (
        <div className="absolute left-0 top-full z-50 mt-1 w-56 rounded-md border border-border bg-popover p-1 shadow-md animate-fade-in">
          {memberships.map((m) => (
            <button
              key={m.org_id}
              onClick={() => switchOrg(m.org_id)}
              className="flex w-full items-center justify-between rounded px-2 py-1.5 text-xs text-popover-foreground hover:bg-accent hover:text-accent-foreground"
            >
              <span className="truncate font-medium">{m.org_name || m.org_id}</span>
              <span className="text-[10px] text-muted-foreground uppercase">{m.role}</span>
              {m.org_id === activeOrgId && <Check className="ml-2 h-3.5 w-3.5" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
