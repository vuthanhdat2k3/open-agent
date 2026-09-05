import type { SlashCommand, SlashCommandContext, SlashCommandOption } from "./types";
import type { Model, ExecutionPolicy } from "@/types";

/** Built-in slash commands registry */
export const SLASH_COMMANDS: SlashCommand[] = [
  {
    name: "model",
    description: "Đổi mô hình AI",
    usage: "/model <tên-mô-hình>",
    requiresArgs: true,
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
      const model = ctx.models.find(
        (m) => m.active && (m.id === args || m.name.toLowerCase().includes(args.toLowerCase()) || m.display_name?.toLowerCase().includes(args.toLowerCase()))
      );
      if (model) {
        ctx.onModelChange(model.id);
        return true;
      }
      return false;
    },
  },
  {
    name: "policy",
    description: "Đổi quyền thực thi",
    usage: "/policy <read-only|manual|full-access>",
    requiresArgs: true,
    getOptions: (ctx: SlashCommandContext): SlashCommandOption[] => {
      const policies: { value: ExecutionPolicy; label: string; detail: string }[] = [
        { value: "read-only", label: "Chỉ đọc", detail: "Chỉ truy vấn an toàn" },
        { value: "manual", label: "Cần phê duyệt", detail: "Duyệt trước khi thực thi" },
        { value: "full-access", label: "Toàn quyền", detail: "Tự động thực thi" },
      ];
      return policies.map((p) => ({
        id: p.value,
        label: p.label,
        detail: p.detail,
      }));
    },
    execute: (args: string, ctx: SlashCommandContext): boolean => {
      const validPolicies: ExecutionPolicy[] = ["read-only", "manual", "full-access"];
      const policy = validPolicies.find((p) => p.startsWith(args.toLowerCase()));
      if (policy) {
        ctx.onExecutionPolicyChange(policy);
        return true;
      }
      return false;
    },
  },
  {
    name: "clear",
    description: "Xóa lịch sử hội thoại",
    execute: (_args: string, ctx: SlashCommandContext): boolean => {
      ctx.onClear();
      return true;
    },
  },
  {
    name: "reset",
    description: "Tạo phiên hội thoại mới",
    execute: (_args: string, ctx: SlashCommandContext): boolean => {
      ctx.onReset();
      return true;
    },
  },
  {
    name: "help",
    description: "Hiển thị danh sách lệnh",
    execute: (_args: string, ctx: SlashCommandContext): boolean => {
      ctx.onDraftChange("/help");
      return true;
    },
  },
];

/** Parse slash command from input text at cursor position */
export function parseSlashCommand(text: string, cursorPos: number): { name: string; args: string } | null {
  // Find the start of the current word
  let start = cursorPos;
  while (start > 0 && text[start - 1] !== " " && text[start - 1] !== "\n") {
    start--;
  }

  // Check if current word starts with /
  if (text[start] !== "/") return null;

  // Get the command text up to cursor
  const cmdText = text.slice(start, cursorPos);
  const parts = cmdText.split(/\s+/);
  const name = parts[0].slice(1); // Remove leading /
  const args = parts.slice(1).join(" ");

  return { name, args };
}

/** Get command by name */
export function getCommand(name: string): SlashCommand | undefined {
  return SLASH_COMMANDS.find((cmd) => cmd.name === name);
}

/** Filter commands by partial name */
export function filterCommands(query: string): SlashCommand[] {
  if (!query) return SLASH_COMMANDS;
  const lower = query.toLowerCase();
  return SLASH_COMMANDS.filter(
    (cmd) => cmd.name.toLowerCase().includes(lower) || cmd.description.toLowerCase().includes(lower)
  );
}
