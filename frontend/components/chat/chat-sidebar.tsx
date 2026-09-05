"use client";

import * as React from "react";
import { MessageSquare, Plus, Trash2, PanelLeftClose, PanelLeft, History } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { useCurrentRoles, useMe } from "@/hooks";
import { useIsMobile } from "@/components/hooks/use-mobile";
import type { Session } from "@/types";

interface ChatSidebarProps {
  sessions: Session[];
  activeSessionId: string | null;
  onSessionChange: (sessionId: string) => void;
  onNewSession: () => void;
  onDeleteSession: (sessionId: string) => Promise<void>;
}

export function ChatSidebar({
  sessions,
  activeSessionId,
  onSessionChange,
  onNewSession,
  onDeleteSession,
}: ChatSidebarProps) {
  const { t, locale, tx } = useTranslation();
  const roles = useCurrentRoles();
  const me = useMe();
  const isMobile = useIsMobile();
  const currentUserId = me.data?.id;
  const isOperator = roles.includes("operator");
  
  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileSheetOpen, setMobileSheetOpen] = React.useState(false);
  const [selectedUserFilter, setSelectedUserFilter] = React.useState<string>("all");

  // Auto-collapse sidebar on mobile screen
  React.useEffect(() => {
    if (isMobile) {
      setCollapsed(true);
    }
  }, [isMobile]);

  // Extract unique creators for filter dropdown
  const uniqueCreators = React.useMemo(() => {
    const map = new Map<string, { id: string; label: string }>();
    sessions.forEach((s) => {
      if (s.created_by_user_id) {
        map.set(s.created_by_user_id, {
          id: s.created_by_user_id,
          label: s.creator_email || s.creator_name || s.created_by_user_id.slice(0, 8),
        });
      }
    });
    return Array.from(map.values());
  }, [sessions]);

  // Filter sessions by selected creator
  const filteredSessions = React.useMemo(() => {
    if (selectedUserFilter === "all") return sessions;
    return sessions.filter((s) => s.created_by_user_id === selectedUserFilter);
  }, [sessions, selectedUserFilter]);

  const renderSessionList = (onSelectCallback?: () => void) => (
    <div className="flex h-full flex-col">
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-border/60 px-3">
        <Button
          variant="ghost"
          className="flex-1 justify-start gap-2 h-9 px-2 font-medium"
          onClick={() => {
            onNewSession();
            onSelectCallback?.();
          }}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {tx("Tạo phiên mới", "New chat")}
        </Button>
        {!isMobile && (
          <Button
            variant="ghost"
            size="icon"
            className="ml-2 h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
            onClick={() => setCollapsed(true)}
            aria-label={tx("Thu gọn Sidebar", "Collapse Sidebar")}
            title={tx("Thu gọn Sidebar", "Collapse Sidebar")}
          >
            <PanelLeftClose className="h-4 w-4" aria-hidden="true" />
          </Button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        <div className="flex items-center justify-between px-2 py-1.5">
          <span className="text-xs font-medium text-muted-foreground">
            {tx("Lịch sử phiên", "Sessions")} ({filteredSessions.length})
          </span>
          {isOperator && uniqueCreators.length > 0 && (
            <select
              value={selectedUserFilter}
              onChange={(e) => setSelectedUserFilter(e.target.value)}
              className="rounded border border-input bg-background/80 px-1.5 py-0.5 text-[10px] text-foreground shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="all">{tx("Tất cả", "All")}</option>
              {uniqueCreators.map((creator) => (
                <option key={creator.id} value={creator.id}>
                  {creator.label}
                </option>
              ))}
            </select>
          )}
        </div>
        {filteredSessions.length === 0 ? (
          <div className="px-2 py-6 text-center text-xs text-muted-foreground/60">
            {tx("Chưa có phiên hội thoại nào.", "No sessions yet.")}
          </div>
        ) : (
          <div className="space-y-0.5">
            {filteredSessions.map((s) => {
              const isActive = s.id === activeSessionId;
              const canDelete = isOperator || !s.created_by_user_id || s.created_by_user_id === currentUserId;
              return (
                <div
                  key={s.id}
                  className={cn(
                    "group relative flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm transition-colors hover:bg-accent hover:text-accent-foreground",
                    isActive ? "bg-accent text-accent-foreground font-medium" : "text-muted-foreground"
                  )}
                  onClick={() => {
                    onSessionChange(s.id);
                    onSelectCallback?.();
                  }}
                >
                  <MessageSquare className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <div className="flex-1 min-w-0">
                    <span className="block truncate leading-tight">{s.title}</span>
                    {isOperator && s.created_by_user_id && s.created_by_user_id !== currentUserId && (
                      <span className="block truncate text-[10px] text-muted-foreground/60">
                        {s.creator_email || s.creator_name || s.created_by_user_id.slice(0, 8)}
                      </span>
                    )}
                  </div>

                  {canDelete && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        void onDeleteSession(s.id);
                      }}
                      className={cn(
                        "absolute right-1 flex h-6 w-6 items-center justify-center rounded-sm bg-background/50 text-muted-foreground/60 opacity-0 transition-opacity hover:bg-destructive hover:text-destructive-foreground focus:opacity-100 focus:outline-none group-hover:opacity-100",
                        isActive && "opacity-100"
                      )}
                      aria-label={tx("Xóa phiên", "Delete session")}
                      title={tx("Xóa phiên", "Delete session")}
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );

  // Mobile rendering: compact icon bar that triggers a full slide-over Sheet
  if (isMobile) {
    return (
      <>
        <div className="flex h-full w-10 shrink-0 flex-col items-center border-r border-border/60 bg-muted/10 py-2.5 gap-2">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMobileSheetOpen(true)}
            className="h-7 w-7 text-muted-foreground hover:text-foreground"
            aria-label={tx("Lịch sử phiên trò chuyện", "Chat sessions history")}
            title={tx("Lịch sử phiên trò chuyện", "Chat sessions history")}
          >
            <History className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onNewSession}
            className="h-7 w-7 text-muted-foreground hover:text-foreground"
            aria-label={tx("Tạo phiên mới", "New session")}
            title={tx("Tạo phiên mới", "New session")}
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>

        <Sheet open={mobileSheetOpen} onOpenChange={setMobileSheetOpen}>
          <SheetContent side="left" className="w-[85vw] max-w-[320px] p-0 bg-background">
            <SheetHeader className="sr-only">
              <SheetTitle>{tx("Lịch sử phiên", "Sessions History")}</SheetTitle>
              <SheetDescription>{tx("Danh sách các phiên trò chuyện đã lưu", "List of saved chat sessions")}</SheetDescription>
            </SheetHeader>
            {renderSessionList(() => setMobileSheetOpen(false))}
          </SheetContent>
        </Sheet>
      </>
    );
  }

  // Desktop / Tablet Collapsed state
  if (collapsed) {
    return (
      <div className="flex h-full w-12 shrink-0 flex-col items-center border-r border-border/60 bg-muted/10 py-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setCollapsed(false)}
          className="h-8 w-8 text-muted-foreground hover:text-foreground"
          aria-label={tx("Mở rộng Sidebar", "Expand Sidebar")}
          title={tx("Mở rộng Sidebar", "Expand Sidebar")}
        >
          <PanelLeft className="h-4 w-4" aria-hidden="true" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onNewSession}
          className="mt-4 h-8 w-8 text-muted-foreground hover:text-foreground"
          aria-label={tx("Tạo phiên mới", "New session")}
          title={tx("Tạo phiên mới", "New session")}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    );
  }

  // Desktop Expanded state
  return (
    <div className="flex h-full w-64 shrink-0 flex-col border-r border-border/60 bg-muted/10">
      {renderSessionList()}
    </div>
  );
}
