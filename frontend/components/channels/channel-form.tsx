"use client";

import * as React from "react";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { useTranslation } from "@/lib/i18n";

interface ChannelFormState {
  provider: "telegram" | "discord";
  bot_token: string;
  bot_username: string;
  default_agent_id: string;
  guild_id: string;
  public_key: string;
}

export function ChannelForm({
  initial,
  onSubmit,
}: {
  initial?: Partial<ChannelFormState>;
  onSubmit: (values: ChannelFormState) => void;
}) {
  const { tx } = useTranslation();
  const [form, setForm] = React.useState<ChannelFormState>({
    provider: initial?.provider ?? "telegram",
    bot_token: initial?.bot_token ?? "",
    bot_username: initial?.bot_username ?? "",
    default_agent_id: initial?.default_agent_id ?? "",
    guild_id: initial?.guild_id ?? "",
    public_key: initial?.public_key ?? "",
  });

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(form);
      }}
    >
      <div className="space-y-2">
        <Label htmlFor="channel-provider">{tx("Nền tảng", "Platform")}</Label>
        <Select
          id="channel-provider"
          value={form.provider}
          onChange={(event) =>
            setForm({ ...form, provider: event.target.value as "telegram" | "discord" })
          }
        >
          <option value="telegram">Telegram</option>
          <option value="discord">Discord</option>
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="channel-token">
          {tx("Bot Token", "Bot Token")}
        </Label>
        <Input
          id="channel-token"
          name="bot_token"
          type="password"
          value={form.bot_token}
          onChange={(event) => setForm({ ...form, bot_token: event.target.value })}
          placeholder={tx("Nhập bot token từ BotFather / Developer Portal", "Enter bot token from BotFather / Developer Portal")}
          required
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="channel-username">
          {tx("Bot Username (tùy chọn)", "Bot Username (optional)")}
        </Label>
        <Input
          id="channel-username"
          name="bot_username"
          value={form.bot_username}
          onChange={(event) => setForm({ ...form, bot_username: event.target.value })}
          placeholder="@my_bot"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="channel-agent">
          {tx("Default Agent ID (tùy chọn)", "Default Agent ID (optional)")}
        </Label>
        <Input
          id="channel-agent"
          name="default_agent_id"
          value={form.default_agent_id}
          onChange={(event) => setForm({ ...form, default_agent_id: event.target.value })}
          placeholder={tx("ID agent mặc định để xử lý tin nhắn", "Default agent ID for processing messages")}
        />
      </div>

      {form.provider === "discord" && (
        <>
          <div className="space-y-2">
            <Label htmlFor="channel-guild">
              {tx("Guild ID (Discord)", "Guild ID (Discord)")}
            </Label>
            <Input
              id="channel-guild"
              name="guild_id"
              value={form.guild_id}
              onChange={(event) => setForm({ ...form, guild_id: event.target.value })}
              placeholder="123456789012345678"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="channel-pubkey">
              {tx("Public Key (Discord)", "Public Key (Discord)")}
            </Label>
            <Input
              id="channel-pubkey"
              name="public_key"
              value={form.public_key}
              onChange={(event) => setForm({ ...form, public_key: event.target.value })}
              placeholder={tx("Khóa công khai để xác minh chữ ký webhook", "Public key for webhook signature verification")}
            />
          </div>
        </>
      )}

      <Button type="submit" className="w-full">
        {tx("Lưu kết nối", "Save Connection")}
      </Button>
    </form>
  );
}
