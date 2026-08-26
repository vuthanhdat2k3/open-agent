"use client";

import * as React from "react";
import Link from "next/link";
import { Check, ChevronLeft, ChevronRight, Edit3, ShieldAlert, Sparkles, X, ArrowRight } from "lucide-react";
import type { ApprovalRequest } from "@/types";
import { approvalTitle, expiry } from "@/components/layout/approval-bell";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

import { useTranslation } from "@/lib/i18n";

interface ApprovalCarouselProps {
  approvals: ApprovalRequest[];
  onDecide: (id: string, decision: "approved" | "rejected") => Promise<void>;
  onBatchDecideAll: () => Promise<void>;
  onOpenDetail?: (approval: ApprovalRequest) => void;
}

export function ApprovalCarousel({
  approvals,
  onDecide,
  onBatchDecideAll,
  onOpenDetail,
}: ApprovalCarouselProps) {
  const { t, locale } = useTranslation();
  const [currentIndex, setCurrentIndex] = React.useState(0);
  const [isDeciding, setIsDeciding] = React.useState(false);
  const [isBatchDeciding, setIsBatchDeciding] = React.useState(false);

  React.useEffect(() => {
    if (currentIndex >= approvals.length && approvals.length > 0) {
      setCurrentIndex(approvals.length - 1);
    }
  }, [approvals.length, currentIndex]);

  if (approvals.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card/60 p-8 text-center">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-500">
          <Check className="h-5 w-5" />
        </div>
        <p className="mt-3 text-sm font-semibold text-foreground">{t("pages.approvals.allCleared", "All approvals cleared")}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {t("pages.approvals.noPendingActions", "No pending actions require your review. All background routines are active and safe.")}
        </p>
      </div>
    );
  }

  const current = approvals[currentIndex];
  const title = approvalTitle(current, locale);
  const isHighRisk = current.risk_level === "HIGH" || current.risk_level === "high" || current.tool_name?.includes("send") || current.tool_name?.includes("delete");

  const handleNext = () => {
    setCurrentIndex((prev) => (prev + 1) % approvals.length);
  };

  const handlePrev = () => {
    setCurrentIndex((prev) => (prev - 1 + approvals.length) % approvals.length);
  };

  const handleApprove = async () => {
    if (!current) return;
    setIsDeciding(true);
    try {
      await onDecide(current.id, "approved");
    } finally {
      setIsDeciding(false);
    }
  };

  const handleReject = async () => {
    if (!current) return;
    setIsDeciding(true);
    try {
      await onDecide(current.id, "rejected");
    } finally {
      setIsDeciding(false);
    }
  };

  const handleBatchApprove = async () => {
    setIsBatchDeciding(true);
    try {
      await onBatchDecideAll();
    } finally {
      setIsBatchDeciding(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Carousel Navigation Header */}
      <div className="flex items-center justify-between font-mono text-[10.5px] text-muted-foreground">
        <span>
          {t("pages.approvals.requestsLabel", "APPROVAL REQUESTS (")}{currentIndex + 1} / {approvals.length})
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="h-6 w-6 rounded border-border bg-card text-muted-foreground hover:text-foreground"
            onClick={handlePrev}
            title={t("pages.approvals.prevCard", "Previous card")}
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-6 w-6 rounded border-border bg-card text-muted-foreground hover:text-foreground"
            onClick={handleNext}
            title={t("pages.approvals.nextCard", "Next card")}
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Main Card (Styled with Web App Card Pattern) */}
      <div className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 shadow-card transition-all">
        <div className="flex items-center justify-between gap-2">
          <Badge variant={isHighRisk ? "destructive" : "outline"} className="text-[10px] uppercase font-mono">
            {isHighRisk ? "⚡ HIGH RISK" : "STANDARD ACTION"}
          </Badge>
          <span className="font-mono text-[10.5px] text-muted-foreground">
            98% {t("pages.approvals.confidence", "Confidence")} · {expiry(current.expires_at, locale)}
          </span>
        </div>

        <h4 className="text-sm font-semibold leading-snug tracking-tight text-foreground">
          {title}
        </h4>

        {/* Reasoning Steps (3-Step Micro Steps) */}
        <div className="flex flex-col gap-2 rounded-lg border border-border/70 bg-muted/40 p-3 text-xs leading-relaxed">
          <div className="flex items-start gap-2">
            <span className="font-mono text-[10px] font-semibold text-muted-foreground">{t("pages.approvals.toolLabel", "01 / TOOL:")}</span>
            <span className="font-mono text-[11px] font-medium text-foreground">
              {current.tool_name || "gmail.send_message"}
            </span>
          </div>
          <div className="flex items-start gap-2">
            <span className="font-mono text-[10px] font-semibold text-muted-foreground">{t("pages.approvals.argsLabel", "02 / ARGS:")}</span>
            <div className="line-clamp-2 text-muted-foreground font-mono text-[11px]">
              {current.args_snapshot && typeof current.args_snapshot === "object"
                ? JSON.stringify(current.args_snapshot)
                : t("pages.approvals.automatedArgs", "Automated action synthesized from background routine.")}
            </div>
          </div>
          <div className="flex items-start gap-2">
            <span className="font-mono text-[10px] font-semibold text-muted-foreground">{t("pages.approvals.policyLabel", "03 / POLICY:")}</span>
            <span className="text-muted-foreground text-[11px]">
              {t("pages.approvals.verifiedBoundary", "Verified against safety boundary. Requires 1 explicit human confirmation before execution.")}
            </span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-between gap-2 pt-1">
          <div className="flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              className="h-8 border-border text-xs text-muted-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/40"
              onClick={handleReject}
              disabled={isDeciding}
            >
              <X className="mr-1 h-3.5 w-3.5" /> {t("pages.approvals.btnReject", "Reject")}
            </Button>
            {onOpenDetail && (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 text-xs text-muted-foreground hover:text-foreground"
                onClick={() => onOpenDetail(current)}
              >
                <Edit3 className="mr-1 h-3.5 w-3.5" /> {t("pages.approvals.details", "Details")}
              </Button>
            )}
          </div>

          <Button
            size="sm"
            className="h-8 px-4 text-xs font-semibold gap-1.5 shadow-sm"
            onClick={handleApprove}
            disabled={isDeciding}
          >
            <Check className="h-3.5 w-3.5" />
            {isDeciding ? t("pages.approvals.approving", "Approving...") : t("pages.approvals.oneClickApprove", "1-Click Approve")}
          </Button>
        </div>
      </div>

      {/* 1-Click Fast Batch Approve Bar (If > 1 item) */}
      {approvals.length > 1 && (
        <div className="flex items-center justify-between rounded-xl border border-primary/20 bg-primary/[0.04] p-3 text-xs">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary shrink-0" />
            <span className="font-medium text-foreground">
              {t("pages.approvals.fastApproveAll", "Fast Approve All {n} Safe Actions").replace("{n}", String(approvals.length))}
            </span>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="h-7 border-primary/30 bg-primary/10 text-xs font-semibold text-primary hover:bg-primary hover:text-primary-foreground"
            onClick={handleBatchApprove}
            disabled={isBatchDeciding}
          >
            {isBatchDeciding ? t("common.processing", "Processing...") : `Saves ~${approvals.length * 15}m →`}
          </Button>
        </div>
      )}

      {/* Queue Deep Link */}
      <div className="flex justify-center pt-1">
        <Link
          href="/approvals"
          className="flex items-center gap-1 font-mono text-[11px] text-muted-foreground hover:text-primary hover:underline transition-colors"
        >
          {t("pages.approvals.viewAllQueue", "View All in Approvals Queue (/approvals)")} <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
    </div>
  );
}
