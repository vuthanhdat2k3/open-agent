import type { Model } from "@/types";
import type { SlashCommand, SlashCommandContext, SlashCommandOption } from "./types";

/** Compact prompt sent to the agent when the user runs /compact */
const COMPACT_PROMPT =
  "Hãy tóm tắt ngắn gọn toàn bộ hội thoại phía trên thành một bản ghi nhớ cô đọng (các yêu cầu chính, quyết định đã chốt, kết quả quan trọng). Sau đó trả lời duy nhất bằng bản tóm tắt đó.";

function formatCost(usd: number): string {
  if (usd >= 1) return `$${usd.toFixed(2)}`;
  return `$${usd.toFixed(4)}`;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/** Built-in slash commands registry */
export const SLASH_COMMANDS: SlashCommand[] = [
  {
    name: "model",
    description: "Đổi mô hình AI",
    usage: "/model <tên-mô-hình>",
    icon: "cpu",
    requiresArgs: true,
    getOptions: (ctx: SlashCommandContext): SlashCommandOption[] =>
      ctx.models
        .filter((m) => m.active)
        .map((m) => ({
          id: m.id,
          label: m.display_name || m.name,
          detail: [m.tier, m.supports_vision ? "Vision" : null].filter(Boolean).join(" · ") || undefined,
        })),
    execute: (args: string, ctx: SlashCommandContext): boolean => {
      const model = ctx.models.find(
        (m) =>
          m.active &&
          (m.id === args ||
            m.name.toLowerCase().includes(args.toLowerCase()) ||
            m.display_name?.toLowerCase().includes(args.toLowerCase())),
      );
      if (model) {
        ctx.onModelChange(model.id);
        ctx.notify(ctx.tx(`Đã chuyển sang ${model.display_name || model.name}`, `Switched to ${model.display_name || model.name}`), "success");
        return true;
      }
      ctx.notify(ctx.tx("Không tìm thấy mô hình", "Model not found"), "error");
      return false;
    },
  },
  {
    name: "select-model",
    description: "Chọn mô hình AI (hiển thị danh sách)",
    usage: "/select-model",
    icon: "sliders",
    getOptions: (ctx: SlashCommandContext): SlashCommandOption[] => {
      return ctx.models
        .filter((m: Model) => m.active)
        .map((m: Model) => ({
          id: m.id,
          label: m.display_name || m.name,
          detail: m.supports_vision ? "Vision" : undefined,
        }));
    },
    execute: (args: string, ctx: SlashCommandContext): boolean => {
      if (args) {
        ctx.onModelChange(args);
        const model = ctx.models.find((m) => m.id === args);
        if (model) {
          ctx.notify(ctx.tx(`Đã chuyển sang ${model.display_name || model.name}`, `Switched to ${model.display_name || model.name}`), "success");
        }
        return true;
      }
      return false;
    },
  },
  {
    name: "policy",
    description: "Đổi quyền thực thi hệ thống",
    usage: "/policy <read-only|manual|full-access>",
    icon: "shield",
    requiresArgs: true,
    getOptions: (_ctx: SlashCommandContext): SlashCommandOption[] => [
      { id: "read-only", label: "Chỉ đọc", detail: "Chỉ truy vấn an toàn, chặn thao tác ghi" },
      { id: "manual", label: "Cần phê duyệt", detail: "Yêu cầu duyệt trước khi ghi hoặc chạy mã" },
      { id: "full-access", label: "Toàn quyền", detail: "Tự động chạy mọi công cụ được phép" },
    ],
    execute: (args: string, ctx: SlashCommandContext): boolean => {
      const valid = ["read-only", "manual", "full-access"] as const;
      const policy = valid.find((p) => p.startsWith(args.toLowerCase()));
      if (policy) {
        ctx.onExecutionPolicyChange(policy);
        const labels: Record<string, string> = {
          "read-only": "Chỉ đọc",
          manual: "Cần phê duyệt",
          "full-access": "Toàn quyền tự động",
        };
        ctx.notify(ctx.tx(`Quyền thực thi: ${labels[policy]}`, `Execution policy: ${policy}`), "success");
        return true;
      }
      ctx.notify(ctx.tx("Quyền không hợp lệ (read-only | manual | full-access)", "Invalid policy (read-only | manual | full-access)"), "error");
      return false;
    },
  },
  {
    name: "agents",
    description: "Chuyển sang agent khác",
    usage: "/agents <tên-agent>",
    icon: "bot",
    getOptions: (ctx: SlashCommandContext): SlashCommandOption[] =>
      ctx.agents.map((a) => ({
        id: a.id,
        label: a.name,
        detail: a.kind === "orchestrator" ? "Orchestrator" : "Worker",
      })),
    execute: (args: string, ctx: SlashCommandContext): boolean => {
      const agent = ctx.agents.find(
        (a) => a.id === args || a.name.toLowerCase().includes(args.toLowerCase()),
      );
      if (agent) {
        ctx.onAgentChange(agent.id);
        ctx.notify(ctx.tx(`Đã chuyển sang agent "${agent.name}"`, `Switched to agent "${agent.name}"`), "success");
        return true;
      }
      ctx.notify(ctx.tx("Không tìm thấy agent", "Agent not found"), "error");
      return false;
    },
  },
  {
    name: "compact",
    description: "Tóm tắt hội thoại để tiết kiệm context",
    icon: "sparkles",
    execute: async (_args: string, ctx: SlashCommandContext): Promise<boolean> => {
      ctx.onDraftChange("");
      if (ctx.onCompactSession) {
        await ctx.onCompactSession();
        return true;
      }
      ctx.onSend(COMPACT_PROMPT);
      return true;
    },
  },
  {
    name: "context",
    description: "Xem chi tiết ngữ cảnh phiên hiện tại",
    icon: "info",
    execute: (_args: string, ctx: SlashCommandContext): boolean => {
      if (ctx.openDialog) {
        ctx.openDialog("context");
        return true;
      }
      const model = ctx.effectiveModel ? ctx.effectiveModel.display_name || ctx.effectiveModel.name : "—";
      const agent = ctx.agents.find((a) => a.id === ctx.currentAgentId);
      const policyLabels: Record<string, string> = {
        "read-only": "Chỉ đọc",
        manual: "Cần phê duyệt",
        "full-access": "Toàn quyền",
      };
      const lines = [
        `🧠 Agent: ${agent?.name ?? "—"}`,
        `⚙️ Mô hình: ${model}`,
        `🛡️ Quyền: ${ctx.executionPolicy ? policyLabels[ctx.executionPolicy] ?? ctx.executionPolicy : "—"}`,
      ];
      ctx.notify(lines.join("\n"), "info");
      return true;
    },
  },
  {
    name: "usage",
    description: "Xem chi phí và thống kê tokens",
    icon: "chart",
    execute: (_args: string, ctx: SlashCommandContext): boolean => {
      if (ctx.openDialog) {
        ctx.openDialog("usage");
        return true;
      }
      if (!ctx.usage.length) {
        ctx.notify(ctx.tx("Chưa có dữ liệu sử dụng.", "No usage data yet."), "info");
        return true;
      }
      const totalCost = ctx.usage.reduce((acc, u) => acc + u.cost_usd, 0);
      const totalCalls = ctx.usage.reduce((acc, u) => acc + u.calls, 0);
      const totalIn = ctx.usage.reduce((acc, u) => acc + u.input_tokens, 0);
      const totalOut = ctx.usage.reduce((acc, u) => acc + u.output_tokens, 0);
      const top = [...ctx.usage].sort((a, b) => b.cost_usd - a.cost_usd).slice(0, 3);
      const lines = [
        `💰 Tổng chi phí: ${formatCost(totalCost)} · ${totalCalls} calls`,
        `📥 Input: ${formatTokens(totalIn)} tokens · 📤 Output: ${formatTokens(totalOut)} tokens`,
        "",
        ...top.map(
          (u) =>
            `• ${u.agent_name} (${u.model_name}): ${formatCost(u.cost_usd)} · ${u.calls} calls · ${formatTokens(u.input_tokens + u.output_tokens)} tk`,
        ),
      ];
      ctx.notify(lines.join("\n"), "info");
      return true;
    },
  },
  {
    name: "clear",
    description: "Xóa lịch sử hội thoại hiện tại",
    icon: "trash",
    execute: async (_args: string, ctx: SlashCommandContext): Promise<boolean> => {
      ctx.onDraftChange("");
      if (ctx.onClearSession) {
        await ctx.onClearSession();
        return true;
      }
      ctx.onClear();
      ctx.notify(ctx.tx("Đã xóa hội thoại", "Conversation cleared"), "success");
      return true;
    },
  },
  {
    name: "reset",
    description: "Bắt đầu phiên làm việc mới",
    icon: "rotate",
    execute: (_args: string, ctx: SlashCommandContext): boolean => {
      ctx.onDraftChange("");
      ctx.onReset();
      return true;
    },
  },
  {
    name: "help",
    description: "Bảng trợ giúp và danh sách lệnh",
    icon: "help",
    execute: (_args: string, ctx: SlashCommandContext): boolean => {
      if (ctx.openDialog) {
        ctx.openDialog("help");
        return true;
      }
      const lines = SLASH_COMMANDS.map((c) => `/${c.name} — ${c.description}`);
      ctx.notify(lines.join("\n"), "info");
      return true;
    },
  },
];

/** Get command by name */
export function getCommand(name: string): SlashCommand | undefined {
  return SLASH_COMMANDS.find((cmd) => cmd.name === name);
}

/** Filter commands by partial name (prefix-first, then substring on name/description) */
export function filterCommands(query: string): SlashCommand[] {
  if (!query) return SLASH_COMMANDS;
  const lower = query.toLowerCase();
  const starts = SLASH_COMMANDS.filter((cmd) => cmd.name.toLowerCase().startsWith(lower));
  if (starts.length) return starts;
  return SLASH_COMMANDS.filter(
    (cmd) => cmd.name.toLowerCase().includes(lower) || cmd.description.toLowerCase().includes(lower),
  );
}
