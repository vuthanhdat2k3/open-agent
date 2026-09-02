"use client";

import * as React from "react";
import {
  ShieldAlert,
  ShieldCheck,
  ShieldX,
  FileCode,
  Terminal,
  RefreshCw,
  ChevronDown,
  Globe,
  Sparkles,
  Info,
} from "lucide-react";
import type { ChatMessage, ApprovalMessage } from "@/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useTranslation } from "@/lib/i18n";

interface ApprovalDockProps {
  pendingApprovals: ApprovalMessage[];
  onApprovalDecision?: (messageOrApprovalId: string, decision: "approved" | "rejected") => Promise<void>;
}

export function ApprovalDock({ pendingApprovals, onApprovalDecision }: ApprovalDockProps) {
  const { tx } = useTranslation();
  const [isDeciding, setIsDeciding] = React.useState<string | null>(null);
  const [showDetails, setShowDetails] = React.useState(false);

  if (pendingApprovals.length === 0) return null;

  const currentApproval = pendingApprovals[0];
  const toolName = currentApproval.toolName || "tool";
  const isCode = toolName === "run_code";
  const isWrite = toolName === "write_file";

  let filePath = "";
  let fileContent = "";
  const rawSnapshot = currentApproval.argsSnapshot;
  if (rawSnapshot && typeof rawSnapshot === "object") {
    filePath = (rawSnapshot as any).path || (rawSnapshot as any).filename || "";
    fileContent = (rawSnapshot as any).content || (rawSnapshot as any).code || "";
  } else if (typeof rawSnapshot === "string") {
    try {
      const parsed = JSON.parse(rawSnapshot);
      filePath = parsed.path || parsed.filename || "";
      fileContent = parsed.content || parsed.code || "";
    } catch {
      fileContent = rawSnapshot;
    }
  }

  const handleDecision = async (decision: "approved" | "rejected") => {
    if (!onApprovalDecision) return;
    const targetId = currentApproval.approvalId || currentApproval.id;
    setIsDeciding(decision);
    try {
      await onApprovalDecision(targetId, decision);
    } finally {
      setIsDeciding(null);
    }
  };

  return (
    <div className="w-full animate-slide-up rounded-2xl border-2 border-warning/60 bg-gradient-to-b from-card via-card/95 to-background p-4 shadow-xl backdrop-blur-xl transition-all">
      {/* Header Banner */}
      <div className="flex items-center justify-between gap-3 border-b border-border/60 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-warning/20 text-warning shadow-inner">
            <ShieldAlert className="h-4.5 w-4.5 animate-bounce" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-foreground">
                {tx("Yêu cầu phê duyệt hành động", "Action Approval Required")}
              </span>
              <Badge variant="outline" className="border-warning/50 bg-warning/15 font-mono text-[10px] text-warning">
                {toolName}
              </Badge>
            </div>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              {tx(
                "Agent cần sự cho phép của bạn trước khi thực hiện hành động này trong hệ thống.",
                "The agent requires your explicit permission before executing this action in your workspace."
              )}
            </p>
          </div>
        </div>

        {pendingApprovals.length > 1 && (
          <Badge variant="secondary" className="font-mono text-[10px]">
            +{pendingApprovals.length - 1} {tx("chờ duyệt", "more pending")}
          </Badge>
        )}
      </div>

      {/* Action Content Preview */}
      <div className="my-3 space-y-2.5">
        <div className="flex items-center gap-2 text-xs font-medium text-foreground">
          {isWrite ? (
            <FileCode className="h-4 w-4 text-primary" />
          ) : isCode ? (
            <Terminal className="h-4 w-4 text-primary" />
          ) : (
            <Sparkles className="h-4 w-4 text-warning" />
          )}
          <span>
            {isWrite
              ? tx("Tạo / Ghi tệp tin:", "Create / Write File:")
              : isCode
              ? tx("Thực thi mã trong Sandbox:", "Execute Script in Sandbox:")
              : tx("Thao tác công cụ:", "Tool Invocation:")}
          </span>
          {filePath && (
            <code className="rounded bg-muted px-2 py-0.5 font-mono text-[11px] font-semibold text-primary">
              {filePath}
            </code>
          )}
        </div>

        {/* Collapsible Details / Diff View */}
        <Collapsible open={showDetails} onOpenChange={setShowDetails} className="w-full">
          <div className="flex items-center justify-between rounded-lg bg-muted/40 px-3 py-1.5 border border-border/40 text-[11px]">
            <span className="font-medium text-muted-foreground flex items-center gap-1.5">
              <Info className="h-3 w-3" />
              {tx("Chi tiết nội dung / Tham số payload", "Payload Details & Code Arguments")}
            </span>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="sm" className="h-6 px-2 text-[10px] gap-1 text-primary hover:text-primary">
                <span>{showDetails ? tx("Ẩn chi tiết", "Hide details") : tx("Xem chi tiết", "View details")}</span>
                <ChevronDown className={`h-3 w-3 transition-transform duration-200 ${showDetails ? "rotate-180" : ""}`} />
              </Button>
            </CollapsibleTrigger>
          </div>
          <CollapsibleContent className="mt-2">
            <pre className="max-h-60 overflow-auto rounded-xl border border-border/60 bg-muted/30 p-3 font-mono text-[11px] leading-relaxed text-foreground scrollbar-thin whitespace-pre-wrap break-all">
              {fileContent || (typeof rawSnapshot === "string" ? rawSnapshot : JSON.stringify(rawSnapshot, null, 2))}
            </pre>
          </CollapsibleContent>
        </Collapsible>
      </div>

      {/* Decision Action Buttons */}
      <div className="flex items-center justify-end gap-2.5 pt-1">
        <Button
          size="sm"
          variant="outline"
          className="h-8 gap-1.5 px-3.5 text-xs text-muted-foreground hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors"
          disabled={isDeciding !== null}
          onClick={() => handleDecision("rejected")}
        >
          {isDeciding === "rejected" ? (
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ShieldX className="h-3.5 w-3.5" />
          )}
          <span>{tx("Từ chối (Reject)", "Reject")}</span>
        </Button>

        <Button
          size="sm"
          variant="default"
          className="h-8 gap-1.5 px-4 text-xs font-semibold shadow-md transition-all bg-primary hover:bg-primary/90"
          disabled={isDeciding !== null}
          onClick={() => handleDecision("approved")}
        >
          {isDeciding === "approved" ? (
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ShieldCheck className="h-3.5 w-3.5" />
          )}
          <span>{tx("Phê duyệt & Tiếp tục (Approve)", "Approve & Run")}</span>
        </Button>
      </div>
    </div>
  );
}
