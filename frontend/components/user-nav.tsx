"use client";

import * as React from "react";
import Link from "next/link";
import { User, LogOut, Settings, ChevronUp } from "lucide-react";
import { useProfile } from "@/hooks";
import { setAccessToken } from "@/lib/auth";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export function UserNav({ collapsed }: { collapsed?: boolean }) {
  const profile = useProfile();
  const [open, setOpen] = React.useState(false);
  const dropdownRef = React.useRef<HTMLDivElement>(null);

  const user = profile.data;
  const displayName = user?.display_name || user?.email?.split("@")[0] || "User";
  const email = user?.email || "";
  const initial = displayName.charAt(0).toUpperCase();

  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function handleLogout() {
    try {
      await api.post("/api/auth/logout");
    } catch {
      // Ignore
    } finally {
      setAccessToken(null);
      window.location.href = "/login";
    }
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "group flex w-full items-center gap-3 rounded-xl p-2 text-left text-sm font-medium transition-all duration-200 ease-out-expo hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
          collapsed && "justify-center px-0",
          open && "bg-accent/80",
        )}
        title={collapsed ? displayName : undefined}
      >
        {/* Avatar */}
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-primary/80 to-primary text-primary-foreground font-bold text-sm shadow-sm ring-1 ring-white/10 group-hover:scale-105 transition-transform duration-200">
          {initial}
        </div>

        {!collapsed && (
          <>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold leading-tight text-foreground">
                {displayName}
              </div>
              <div className="truncate text-xs text-muted-foreground">{email}</div>
            </div>
            <ChevronUp className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200", open && "rotate-180")} />
          </>
        )}
      </button>

      {/* Popover Dropdown Menu */}
      {open && (
        <div
          className={cn(
            "absolute z-50 mb-2 w-56 rounded-xl border border-border/60 bg-popover/95 p-1.5 shadow-xl backdrop-blur-xl animate-fade-in",
            collapsed ? "bottom-0 left-full ml-2" : "bottom-full left-0 w-full",
          )}
        >
          <div className="px-2 py-1.5 border-b border-border/40 mb-1">
            <p className="text-xs font-semibold text-foreground truncate">{displayName}</p>
            <p className="text-[11px] text-muted-foreground truncate">{email}</p>
          </div>

          <Link
            href="/settings/profile"
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs font-medium text-foreground hover:bg-accent transition-colors"
          >
            <User className="h-4 w-4 text-muted-foreground" />
            Profile Settings
          </Link>

          <Link
            href="/settings/members"
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs font-medium text-foreground hover:bg-accent transition-colors"
          >
            <Settings className="h-4 w-4 text-muted-foreground" />
            Organization Settings
          </Link>

          <div className="my-1 border-t border-border/40" />

          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors"
          >
            <LogOut className="h-4 w-4" />
            Sign Out
          </button>
        </div>
      )}
    </div>
  );
}
