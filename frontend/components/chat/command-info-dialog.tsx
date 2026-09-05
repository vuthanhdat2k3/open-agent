"use client";

import * as React from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";
import { toast } from "sonner";
import {
  Bot,
  Cpu,
  ShieldCheck,
  BarChart2,
  HelpCircle,
  Sparkles,
  Copy,
  Check,
  Terminal,
  Info,
  ArrowRight,
  Eye,
  Sliders,
  RotateCcw,
  Trash2,
  Search,
} from "lucide-react";
import type { Agent, ExecutionPolicy, Model, UsageSummary } from "@/types";
import type { SlashCommand, CommandDialogType } from "./commands/types";

interface CommandInfoDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialTab?: CommandDialogType;
  effectiveModel?: Model;
  currentAgent?: Agent;
  executionPolicy?: ExecutionPolicy;
  sessionId?: string;
  usage: UsageSummary[];
  commands: SlashCommand[];
  onSelectCommand?: (cmd: SlashCommand) => void;
}

function formatCost(usd: number): string {
  if (usd >= 1) return `$${usd.toFixed(2)}`;
  return `$${usd.toFixed(4)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export function CommandInfoDialog({
  open,
  onOpenChange,
  initialTab = "context",
  effectiveModel,
  currentAgent,
  executionPolicy,
  sessionId,
  usage,
  commands,
  onSelectCommand,
}: CommandInfoDialogProps) {
  const { tx } = useTranslation();
  const [activeTab, setActiveTab] = React.useState<CommandDialogType>(initialTab);
  const [copiedSession, setCopiedSession] = React.useState(false);
  const [searchQuery, setSearchQuery] = React.useState("");

  // Sync tab when initialTab prop updates on re-open
  React.useEffect(() => {
    if (open) {
      setActiveTab(initialTab);
      setSearchQuery("");
    }
  }, [open, initialTab]);

  const handleCopySession = () => {
    if (!sessionId) return;
    navigator.clipboard.writeText(sessionId);
    setCopiedSession(true);
    toast.success(tx("Đã sao chép ID phiên vào bộ nhớ tạm", "Session ID copied to clipboard"));
    setTimeout(() => setCopiedSession(false), 2000);
  };

  // Usage aggregate calculations
  const totalCost = React.useMemo(() => usage.reduce((acc, u) => acc + u.cost_usd, 0), [usage]);
  const totalCalls = React.useMemo(() => usage.reduce((acc, u) => acc + u.calls, 0), [usage]);
  const totalIn = React.useMemo(() => usage.reduce((acc, u) => acc + u.input_tokens, 0), [usage]);
  const totalOut = React.useMemo(() => usage.reduce((acc, u) => acc + u.output_tokens, 0), [usage]);

  const filteredCommands = React.useMemo(() => {
    if (!searchQuery.trim()) return commands;
    const q = searchQuery.toLowerCase().trim();
    return commands.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.description.toLowerCase().includes(q) ||
        (c.usage && c.usage.toLowerCase().includes(q))
    );
  }, [commands, searchQuery]);

  const policyLabels: Record<ExecutionPolicy, { label: string; desc: string; badge: "info" | "warning" | "success" }> = {
    "read-only": {
      label: tx("Chỉ đọc", "Read-only"),
      desc: tx("Chỉ truy vấn an toàn, chặn thao tác ghi và chạy mã", "Safe queries only, blocks mutating actions and execution"),
      badge: "info",
    },
    manual: {
      label: tx("Cần phê duyệt", "Manual approval"),
      desc: tx("Yêu cầu bạn xác nhận trước khi thực hiện tác vụ rủi ro", "Requires explicit approval for mutating commands"),
      badge: "warning",
    },
    "full-access": {
      label: tx("Toàn quyền tự động", "Full access"),
      desc: tx("Tự động thực thi mọi công cụ được phép không cần phê duyệt", "Autonomous execution for all permitted tools"),
      badge: "success",
    },
  };

  const getCommandIcon = (icon?: string) => {
    switch (icon) {
      case "cpu":
        return <Cpu className="h-4 w-4 text-blue-500" />;
      case "sliders":
        return <Sliders className="h-4 w-4 text-indigo-500" />;
      case "shield":
        return <ShieldCheck className="h-4 w-4 text-emerald-500" />;
      case "bot":
        return <Bot className="h-4 w-4 text-purple-500" />;
      case "sparkles":
        return <Sparkles className="h-4 w-4 text-amber-500" />;
      case "info":
        return <Info className="h-4 w-4 text-sky-500" />;
      case "chart":
        return <BarChart2 className="h-4 w-4 text-teal-500" />;
      case "trash":
        return <Trash2 className="h-4 w-4 text-rose-500" />;
      case "rotate":
        return <RotateCcw className="h-4 w-4 text-orange-500" />;
      case "help":
      default:
        return <HelpCircle className="h-4 w-4 text-violet-500" />;
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col p-0 overflow-hidden border border-border/80 bg-card/95 shadow-2xl backdrop-blur-xl">
        {/* Header */}
        <DialogHeader className="px-6 pt-6 pb-4 border-b border-border/60">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-primary/20 via-primary/10 to-transparent border border-primary/20 text-primary shadow-sm">
              <Terminal className="h-5 w-5" />
            </div>
            <div>
              <DialogTitle className="text-lg font-semibold tracking-tight">
                {tx("Trợ Lý Lệnh & Trạng Thái Phiên", "Command Assistant & Session Status")}
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                {tx(
                  "Xem ngữ cảnh môi trường đang chạy, hạn mức tài nguyên và các phím tắt lệnh.",
                  "Inspect the active runtime context, resource metrics, and available slash shortcuts."
                )}
              </DialogDescription>
            </div>
          </div>

          {/* Tab Navigation Pill */}
          <div className="flex items-center gap-1.5 mt-4 p-1 rounded-lg bg-muted/60 border border-border/40 text-xs font-medium">
            <button
              type="button"
              onClick={() => setActiveTab("context")}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 py-1.5 px-3 rounded-md transition-all text-xs",
                activeTab === "context"
                  ? "bg-card text-foreground shadow-sm font-semibold border border-border/50"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
              )}
            >
              <Info className="h-3.5 w-3.5" />
              <span>{tx("Ngữ cảnh phiên", "Context")}</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("usage")}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 py-1.5 px-3 rounded-md transition-all text-xs",
                activeTab === "usage"
                  ? "bg-card text-foreground shadow-sm font-semibold border border-border/50"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
              )}
            >
              <BarChart2 className="h-3.5 w-3.5" />
              <span>{tx("Sử dụng & Chi phí", "Usage & Cost")}</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("help")}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 py-1.5 px-3 rounded-md transition-all text-xs",
                activeTab === "help"
                  ? "bg-card text-foreground shadow-sm font-semibold border border-border/50"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
              )}
            >
              <HelpCircle className="h-3.5 w-3.5" />
              <span>{tx("Danh sách lệnh", "Commands")}</span>
            </button>
          </div>
        </DialogHeader>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          {/* TAB 1: CONTEXT */}
          {activeTab === "context" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
              {/* Active Agent Card */}
              <div className="rounded-xl border border-border/70 bg-card p-4 shadow-sm hover:border-border transition-colors">
                <div className="flex items-center justify-between pb-2 border-b border-border/40 mb-3">
                  <div className="flex items-center gap-2">
                    <Bot className="h-4 w-4 text-purple-500" />
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      {tx("Agent Đang Chạy", "Active Agent")}
                    </span>
                  </div>
                  {currentAgent?.kind && (
                    <Badge variant="outline" className="text-[10px] capitalize font-mono">
                      {currentAgent.kind}
                    </Badge>
                  )}
                </div>
                <div className="text-base font-semibold text-foreground">
                  {currentAgent?.name || tx("Mặc định / Không xác định", "Default / Unassigned")}
                </div>
                <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                  {currentAgent?.description ||
                    tx("Trợ lý trí tuệ nhân tạo tương tác trực tiếp qua hội thoại.", "Conversational intelligent assistant in this session.")}
                </p>
              </div>

              {/* Active Model Card */}
              <div className="rounded-xl border border-border/70 bg-card p-4 shadow-sm hover:border-border transition-colors">
                <div className="flex items-center justify-between pb-2 border-b border-border/40 mb-3">
                  <div className="flex items-center gap-2">
                    <Cpu className="h-4 w-4 text-blue-500" />
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      {tx("Mô Hình AI", "Active Model")}
                    </span>
                  </div>
                  {effectiveModel?.tier && (
                    <Badge variant="default" className="text-[10px] capitalize">
                      {effectiveModel.tier}
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-base font-semibold text-foreground">
                    {effectiveModel?.display_name || effectiveModel?.name || tx("Chưa chọn mô hình", "No model")}
                  </span>
                  {effectiveModel?.supports_vision && (
                    <span title={tx("Hỗ trợ đọc ảnh (Vision)", "Supports Vision")}>
                      <Eye className="h-3.5 w-3.5 text-sky-500" />
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {effectiveModel?.name ? `ID: ${effectiveModel.name}` : tx("Kế thừa từ cấu hình mặc định của hệ thống.", "Inherited from system default settings.")}
                </p>
              </div>

              {/* Execution Policy Card */}
              <div className="rounded-xl border border-border/70 bg-card p-4 shadow-sm hover:border-border transition-colors">
                <div className="flex items-center justify-between pb-2 border-b border-border/40 mb-3">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="h-4 w-4 text-emerald-500" />
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      {tx("Chính Sách Thực Thi", "Execution Policy")}
                    </span>
                  </div>
                  {executionPolicy && (
                    <Badge variant={policyLabels[executionPolicy]?.badge || "default"} className="text-[10px]">
                      {policyLabels[executionPolicy]?.label || executionPolicy}
                    </Badge>
                  )}
                </div>
                <div className="text-sm font-semibold text-foreground">
                  {executionPolicy ? policyLabels[executionPolicy]?.label : tx("Chưa thiết lập", "Not configured")}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {executionPolicy ? policyLabels[executionPolicy]?.desc : "—"}
                </p>
              </div>

              {/* Session ID Card */}
              <div className="rounded-xl border border-border/70 bg-card p-4 shadow-sm hover:border-border transition-colors">
                <div className="flex items-center justify-between pb-2 border-b border-border/40 mb-3">
                  <div className="flex items-center gap-2">
                    <Terminal className="h-4 w-4 text-amber-500" />
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      {tx("Mã Phiên Hội Thoại", "Session Identifier")}
                    </span>
                  </div>
                  {sessionId && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={handleCopySession}
                      className="h-6 px-2 text-[11px] gap-1 hover:bg-muted text-muted-foreground hover:text-foreground"
                    >
                      {copiedSession ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
                      <span>{copiedSession ? tx("Đã chép", "Copied") : tx("Sao chép", "Copy")}</span>
                    </Button>
                  )}
                </div>
                <div className="font-mono text-xs text-foreground select-all truncate bg-muted/40 p-2 rounded-lg border border-border/40">
                  {sessionId || tx("Phiên mới (chưa lưu)", "New conversation (unsaved)")}
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  {tx("Dùng mã này để tra cứu logs và truy vết trên Langfuse / Audit Trail.", "Use this key to trace conversation executions in observability logs.")}
                </p>
              </div>
            </div>
          )}

          {/* TAB 2: USAGE & COST */}
          {activeTab === "usage" && (
            <div className="space-y-4">
              {/* 4 Metrics Highlight Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="rounded-xl border border-border/70 bg-card p-3.5 shadow-sm">
                  <span className="text-[11px] font-medium text-muted-foreground block">
                    {tx("Tổng chi phí", "Total Cost")}
                  </span>
                  <div className="text-lg font-bold text-emerald-600 dark:text-emerald-400 mt-0.5">
                    {formatCost(totalCost)}
                  </div>
                </div>

                <div className="rounded-xl border border-border/70 bg-card p-3.5 shadow-sm">
                  <span className="text-[11px] font-medium text-muted-foreground block">
                    {tx("Số lượt gọi", "Total Calls")}
                  </span>
                  <div className="text-lg font-bold text-foreground mt-0.5">
                    {totalCalls}
                  </div>
                </div>

                <div className="rounded-xl border border-border/70 bg-card p-3.5 shadow-sm">
                  <span className="text-[11px] font-medium text-muted-foreground block">
                    {tx("Tokens nạp vào", "Input Tokens")}
                  </span>
                  <div className="text-lg font-bold text-foreground mt-0.5">
                    {formatTokens(totalIn)}
                  </div>
                </div>

                <div className="rounded-xl border border-border/70 bg-card p-3.5 shadow-sm">
                  <span className="text-[11px] font-medium text-muted-foreground block">
                    {tx("Tokens sinh ra", "Output Tokens")}
                  </span>
                  <div className="text-lg font-bold text-foreground mt-0.5">
                    {formatTokens(totalOut)}
                  </div>
                </div>
              </div>

              {/* Usage Breakdown */}
              <div className="rounded-xl border border-border/70 bg-card p-4 shadow-sm">
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3 flex items-center justify-between">
                  <span>{tx("Chi Tiết Theo Agent & Mô Hình", "Usage Breakdown by Agent & Model")}</span>
                  <span className="text-[10px] text-muted-foreground lowercase">
                    {usage.length} {tx("bản ghi", "records")}
                  </span>
                </div>

                {usage.length === 0 ? (
                  <div className="py-8 text-center">
                    <BarChart2 className="h-8 w-8 mx-auto text-muted-foreground/40 mb-2" />
                    <p className="text-xs text-muted-foreground">
                      {tx("Chưa có phát sinh lượt gọi AI nào trong phiên này.", "No AI model invocations recorded in this session yet.")}
                    </p>
                  </div>
                ) : (
                  <div className="divide-y divide-border/40">
                    {usage.map((item, idx) => {
                      const costRatio = totalCost > 0 ? (item.cost_usd / totalCost) * 100 : 0;
                      return (
                        <div key={`${item.agent_name}-${item.model_name}-${idx}`} className="py-2.5 first:pt-0 last:pb-0">
                          <div className="flex items-center justify-between text-xs mb-1">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className="font-semibold text-foreground truncate">{item.agent_name}</span>
                              <span className="text-muted-foreground/60">•</span>
                              <span className="text-muted-foreground font-mono text-[11px] truncate">{item.model_name}</span>
                            </div>
                            <div className="text-right shrink-0">
                              <span className="font-semibold text-foreground">{formatCost(item.cost_usd)}</span>
                              <span className="text-muted-foreground text-[10px] ml-1.5">({item.calls} calls)</span>
                            </div>
                          </div>
                          <div className="flex items-center justify-between text-[11px] text-muted-foreground mb-1.5">
                            <span>
                              {formatTokens(item.input_tokens)} in / {formatTokens(item.output_tokens)} out
                            </span>
                            <span>{costRatio.toFixed(1)}%</span>
                          </div>
                          <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                            <div
                              className="h-full bg-primary/70 rounded-full transition-all duration-300"
                              style={{ width: `${Math.max(costRatio, 2)}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 3: HELP & COMMANDS */}
          {activeTab === "help" && (
            <div className="space-y-3.5">
              {/* Search input */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <input
                  type="text"
                  placeholder={tx("Tìm kiếm lệnh...", "Search commands...")}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 text-xs rounded-lg border border-border bg-muted/40 placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>

              {/* Commands List */}
              <div className="divide-y divide-border/40 rounded-xl border border-border/70 bg-card overflow-hidden">
                {filteredCommands.length === 0 ? (
                  <div className="p-6 text-center text-xs text-muted-foreground">
                    {tx("Không tìm thấy lệnh phù hợp.", "No matching commands found.")}
                  </div>
                ) : (
                  filteredCommands.map((cmd) => (
                    <div
                      key={cmd.name}
                      className="p-3 flex items-center justify-between gap-3 hover:bg-muted/40 transition-colors group"
                    >
                      <div className="flex items-center gap-3 min-w-0 flex-1">
                        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted/70 border border-border/50">
                          {getCommandIcon(cmd.icon)}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-bold text-primary">/{cmd.name}</span>
                            {cmd.usage && (
                              <span className="font-mono text-[10px] text-muted-foreground/70 bg-muted/60 px-1.5 py-0.5 rounded border border-border/30 truncate">
                                {cmd.usage}
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{cmd.description}</p>
                        </div>
                      </div>

                      {onSelectCommand && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            onSelectCommand(cmd);
                            onOpenChange(false);
                          }}
                          className="h-7 text-xs gap-1 opacity-80 group-hover:opacity-100 hover:bg-primary/10 hover:text-primary shrink-0"
                        >
                          <span>{tx("Chạy", "Run")}</span>
                          <ArrowRight className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  ))
                )}
              </div>

              {/* Shortcuts Legend */}
              <div className="rounded-lg border border-border/50 bg-muted/30 p-2.5 text-[11px] text-muted-foreground flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-foreground">{tx("Phím tắt điều khiển:", "Quick keys:")}</span>
                <div className="flex flex-wrap items-center gap-3">
                  <span>
                    <kbd className="px-1.5 py-0.5 rounded bg-muted border border-border text-[10px] font-mono">↑ / ↓</kbd> {tx("di chuyển", "navigate")}
                  </span>
                  <span>
                    <kbd className="px-1.5 py-0.5 rounded bg-muted border border-border text-[10px] font-mono">↵ / Tab</kbd> {tx("chọn lệnh", "select")}
                  </span>
                  <span>
                    <kbd className="px-1.5 py-0.5 rounded bg-muted border border-border text-[10px] font-mono">Esc</kbd> {tx("đóng menu", "close")}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
