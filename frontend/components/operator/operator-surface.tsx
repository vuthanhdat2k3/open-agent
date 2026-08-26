"use client";

import * as React from "react";
import Link from "next/link";
import { Bot, ChevronRight, Send, Sparkles, X } from "lucide-react";
import { ApprovalCarousel } from "./approval-carousel";
import { EmailTriageAccordion, BriefingsAccordion } from "./micro-accordion-list";
import type { ApprovalRequest, CustomerIntelligenceNotification, CustomerIntelligenceCase } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useTranslation } from "@/lib/i18n";

export type OperatorTab = "approvals" | "inbox" | "reports";

interface OperatorSurfaceProps {
  isOpen: boolean;
  onClose: () => void;
  anchorRect: DOMRect | null;
  companionName?: string;
  approvals: ApprovalRequest[];
  notifications: CustomerIntelligenceNotification[];
  cases: CustomerIntelligenceCase[];
  activeRoutinesCount?: number;
  onDecideApproval: (id: string, decision: "approved" | "rejected") => Promise<void>;
  onBatchDecideAllApprovals: () => Promise<void>;
  onOpenApprovalDetail?: (approval: ApprovalRequest) => void;
  onOpenEmailDetail?: (notification: CustomerIntelligenceNotification) => void;
  onSendDirection?: (prompt: string) => void;
}

export function OperatorSurface({
  isOpen,
  onClose,
  anchorRect,
  companionName = "OpenAgent Operator",
  approvals,
  notifications,
  cases,
  activeRoutinesCount = 7,
  onDecideApproval,
  onBatchDecideAllApprovals,
  onOpenApprovalDetail,
  onOpenEmailDetail,
  onSendDirection,
}: OperatorSurfaceProps) {
    const { locale } = useTranslation();
  const [activeTab, setActiveTab] = React.useState<OperatorTab>("approvals");
  const [directionPrompt, setDirectionPrompt] = React.useState("");
  const surfaceRef = React.useRef<HTMLDivElement>(null);
  const [pos, setPos] = React.useState<{ top: number; left: number; width: number; isAbove: boolean; arrowX: number }>({
    top: 100,
    left: 100,
    width: 480,
    isAbove: false,
    arrowX: 240,
  });

  // Calculate clamped and auto-flipped coordinates
  React.useEffect(() => {
    if (!isOpen || !anchorRect) return;

    const surfaceWidth = Math.min(490, window.innerWidth - 32);
    const surfaceHeight = surfaceRef.current?.offsetHeight || 480;

    let left = anchorRect.left + anchorRect.width / 2 - surfaceWidth / 2;
    const clampedLeft = Math.max(16, Math.min(window.innerWidth - surfaceWidth - 16, left));
    const arrowX = Math.max(20, Math.min(surfaceWidth - 20, anchorRect.left + anchorRect.width / 2 - clampedLeft));

    let top = anchorRect.bottom + 14;
    let isAbove = false;
    if (top + surfaceHeight > window.innerHeight - 16) {
      top = anchorRect.top - surfaceHeight - 14;
      isAbove = true;
    }
    top = Math.max(16, Math.min(window.innerHeight - surfaceHeight - 16, top));

    setPos({
      top,
      left: clampedLeft,
      width: surfaceWidth,
      isAbove,
      arrowX,
    });
  }, [isOpen, anchorRect, activeTab]);

  // Click outside to close
  React.useEffect(() => {
    if (!isOpen) return;
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as HTMLElement;
      if (
        surfaceRef.current &&
        !surfaceRef.current.contains(target) &&
        !target.closest("#companion-trigger")
      ) {
        onClose();
      }
    }
    window.addEventListener("mousedown", handleClickOutside);
    return () => window.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen, onClose]);

  // Keyboard shortcut Esc
  React.useEffect(() => {
    if (!isOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const handleSubmitDirection = (e: React.FormEvent) => {
    e.preventDefault();
    if (!directionPrompt.trim()) return;
    if (onSendDirection) onSendDirection(directionPrompt.trim());
    setDirectionPrompt("");
  };

  if (!isOpen) return null;

  return (
    <div
      ref={surfaceRef}
      style={{
        position: "fixed",
        top: `${pos.top}px`,
        left: `${pos.left}px`,
        width: `${pos.width}px`,
        zIndex: 50,
      }}
      className="animate-in fade-in zoom-in-95 duration-200 flex max-h-[calc(100vh-32px)] flex-col overflow-y-auto rounded-2xl border border-border/90 bg-card/95 p-4 text-card-foreground shadow-3d-floating backdrop-blur-2xl"
    >
      {/* Pointer Arrow Synchronized with Card Border */}
      <div
        style={{
          left: `${pos.arrowX}px`,
          top: pos.isAbove ? "auto" : "-6px",
          bottom: pos.isAbove ? "-6px" : "auto",
        }}
        className={`pointer-events-none absolute h-3 w-3 -translate-x-1/2 rotate-45 bg-card ${
          pos.isAbove
            ? "border-b border-r border-border/90"
            : "border-l border-t border-border/90"
        }`}
      />

      {/* Header with Consistent Web App Theme */}
      <div className="flex flex-col gap-3 border-b border-border/70 pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="grid h-7 w-7 place-items-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
              <Bot className="h-4 w-4" aria-hidden="true" />
            </div>
            <div>
              <h3 className="text-sm font-semibold tracking-tight text-foreground">{companionName}</h3>
              <p className="text-[11px] text-muted-foreground">{locale === "vi" ? "Personal Executive Chief of Staff" : "Personal Executive Chief of Staff"}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 font-mono text-[10px] text-emerald-400">
              <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-emerald-400" />
              {activeRoutinesCount} {locale === "vi" ? "Routines Active" : "Routines Active"}</Badge>
            <div className="flex items-center gap-1">
              <kbd className="hidden sm:inline-block rounded border border-border/80 bg-muted/60 px-1.5 py-0.5 font-mono text-[9px] text-muted-foreground">
                {locale === "vi" ? "Esc" : "Esc"}</kbd>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
                onClick={onClose}
                aria-label="Close"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

        {/* Segmented Capsule Tabs (100% Theme Tokens) */}
        <div className="flex rounded-lg border border-border/70 bg-muted/50 p-1">
          <button
            type="button"
            onClick={() => setActiveTab("approvals")}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-all ${
              activeTab === "approvals"
                ? "bg-card font-semibold text-foreground shadow-sm border border-border/50"
                : "text-muted-foreground hover:bg-muted/80 hover:text-foreground"
            }`}
          >
            <span>{locale === "vi" ? "⚡ Approvals" : "⚡ Approvals"}</span>
            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[9.5px] font-semibold ${
                approvals.length > 0
                  ? "border border-amber-500/40 bg-amber-500/15 text-amber-400"
                  : "border border-border bg-muted text-muted-foreground"
              }`}
            >
              {approvals.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("inbox")}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-all ${
              activeTab === "inbox"
                ? "bg-card font-semibold text-foreground shadow-sm border border-border/50"
                : "text-muted-foreground hover:bg-muted/80 hover:text-foreground"
            }`}
          >
            <span>{locale === "vi" ? "✉ Email Triage" : "✉ Email Triage"}</span>
            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[9.5px] font-semibold ${
                notifications.length > 0
                  ? "border border-sky-500/40 bg-sky-500/15 text-sky-400"
                  : "border border-border bg-muted text-muted-foreground"
              }`}
            >
              {notifications.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("reports")}
            className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-all ${
              activeTab === "reports"
                ? "bg-card font-semibold text-foreground shadow-sm border border-border/50"
                : "text-muted-foreground hover:bg-muted/80 hover:text-foreground"
            }`}
          >
            <span>{locale === "vi" ? "📋 Briefings" : "📋 Briefings"}</span>
            <span className="rounded border border-emerald-500/40 bg-emerald-500/15 px-1.5 py-0.5 font-mono text-[9.5px] font-semibold text-emerald-400">
              {cases.length || 4}
            </span>
          </button>
        </div>
      </div>

      {/* Main Tab Content */}
      <div className="py-3">
        {activeTab === "approvals" && (
          <ApprovalCarousel
            approvals={approvals}
            onDecide={onDecideApproval}
            onBatchDecideAll={onBatchDecideAllApprovals}
            onOpenDetail={onOpenApprovalDetail}
          />
        )}
        {activeTab === "inbox" && (
          <EmailTriageAccordion
            notifications={notifications}
            onOpenEmail={onOpenEmailDetail}
          />
        )}
        {activeTab === "reports" && <BriefingsAccordion cases={cases} />}
      </div>

      {/* Direction Input (Synchronized with Website Theme) */}
      <form onSubmit={handleSubmitDirection} className="mt-1 flex flex-col gap-2.5 border-t border-border/70 pt-3">
        <div className="flex items-center gap-1.5 rounded-xl border border-input bg-muted/40 px-3 py-1.5 transition-all focus-within:border-primary focus-within:ring-1 focus-within:ring-primary/30">
          <Input
            value={directionPrompt}
            onChange={(e) => setDirectionPrompt(e.target.value)}
            placeholder={locale === "vi" ? "Direct operator: 'Approve all', 'Brief me on Acme', 'Prep tomorrow meeting'..." : "Direct operator: 'Approve all', 'Brief me on Acme', 'Prep tomorrow meeting'..."}
            className="h-8 border-0 bg-transparent px-0 text-xs text-foreground placeholder:text-muted-foreground focus-visible:ring-0"
          />
          <Button type="submit" size="sm" className="h-7 px-3 text-xs font-semibold gap-1.5">
            <Send className="h-3 w-3" />
            {locale === "vi" ? "Direct" : "Direct"}</Button>
        </div>

        {/* Quick Suggestion Chips */}
        <div className="flex flex-wrap items-center gap-1.5">
          {approvals.length > 0 && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onBatchDecideAllApprovals()}
              className="h-6 rounded-md border-amber-500/40 bg-amber-500/10 px-2 py-0 text-[11px] font-medium text-amber-400 hover:bg-amber-500/20"
            >
              <Sparkles className="mr-1 h-3 w-3 text-amber-400" /> {locale === "vi" ? "Approve All (" : "Approve All ("}{approvals.length})
            </Button>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setActiveTab("inbox")}
            className="h-6 rounded-md border-border/80 bg-secondary/60 px-2 py-0 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            {locale === "vi" ? "✉ View Emails" : "✉ View Emails"}</Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setActiveTab("reports")}
            className="h-6 rounded-md border-border/80 bg-secondary/60 px-2 py-0 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground"
          >
            {locale === "vi" ? "📋 View Briefings" : "📋 View Briefings"}</Button>
          <Link
            href="/chat"
            className="ml-auto flex items-center gap-0.5 text-[11px] font-semibold text-primary transition-colors hover:underline"
            onClick={onClose}
          >
            {locale === "vi" ? "Chat Workspace" : "Chat Workspace"}<ChevronRight className="h-3 w-3" />
          </Link>
        </div>
      </form>
    </div>
  );
}
