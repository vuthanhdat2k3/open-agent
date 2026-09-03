"use client";

import * as React from "react";
import { toast } from "sonner";
import { MessageSquare, Plus, Pencil, Trash2, Plug, TestTube, Eye } from "lucide-react";
import Link from "next/link";
import {
  useChannelConnections,
  useCreateChannelConnection,
  useDeleteChannelConnection,
  useUpdateChannelConnection,
  useTestChannelConnection,
} from "@/hooks";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { useTranslation } from "@/lib/i18n";
import { ChannelForm } from "@/components/channels/channel-form";
import { ConfirmDialog, ErrorState, LoadingSkeleton } from "@/components/shared";
import type { ChannelConnection } from "@/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export default function ChannelsPage() {
  const { tx } = useTranslation();
  const { data, isLoading, isError, refetch } = useChannelConnections();
  const create = useCreateChannelConnection();
  const del = useDeleteChannelConnection();
  const update = useUpdateChannelConnection();
  const test = useTestChannelConnection();
  const [open, setOpen] = React.useState(false);
  const [editOpen, setEditOpen] = React.useState(false);
  const [editTarget, setEditTarget] = React.useState<ChannelConnection | null>(null);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={MessageSquare}
        title={tx("Kênh tin nhắn", "Messaging Channels")}
        description={tx(
          "Kết nối bot Telegram và Discord để nhận và phản hồi tin nhắn qua agent.",
          "Connect Telegram and Discord bots to receive and respond to messages via agent."
        )}
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="gap-2 active-tactile transition-transform">
                <Plus className="h-4 w-4" /> {tx("Kênh mới", "New Channel")}
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>{tx("Thêm kênh tin nhắn", "Add Messaging Channel")}</DialogTitle>
              </DialogHeader>
              <ChannelForm
                onSubmit={async (values) => {
                  try {
                    await create.mutateAsync({
                      provider: values.provider,
                      bot_token: values.bot_token,
                      bot_username: values.bot_username || undefined,
                      config: {
                        ...(values.default_agent_id ? { default_agent_id: values.default_agent_id } : {}),
                        ...(values.guild_id ? { guild_id: values.guild_id } : {}),
                        ...(values.public_key ? { public_key: values.public_key } : {}),
                      },
                    });
                    toast.success(tx("Đã thêm kênh", "Channel added"));
                    setOpen(false);
                  } catch (e: any) {
                    toast.error(e.message);
                  }
                }}
              />
            </DialogContent>
          </Dialog>
        }
      />

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{tx("Chỉnh sửa kênh", "Edit Channel")}</DialogTitle>
          </DialogHeader>
          {editTarget && (
            <ChannelForm
              initial={{
                provider: editTarget.provider,
                bot_username: editTarget.bot_username,
                default_agent_id: editTarget.config?.default_agent_id ?? "",
                guild_id: editTarget.config?.guild_id ?? "",
                public_key: editTarget.config?.public_key ?? "",
              }}
              onSubmit={async (values) => {
                try {
                  await update.mutateAsync({
                    id: editTarget.id,
                    bot_token: values.bot_token || undefined,
                    bot_username: values.bot_username || undefined,
                    config: {
                      ...(values.default_agent_id ? { default_agent_id: values.default_agent_id } : {}),
                      ...(values.guild_id ? { guild_id: values.guild_id } : {}),
                      ...(values.public_key ? { public_key: values.public_key } : {}),
                    },
                  });
                  toast.success(tx("Đã cập nhật kênh", "Channel updated"));
                  setEditOpen(false);
                  setEditTarget(null);
                } catch (e: any) {
                  toast.error(e.message);
                }
              }}
            />
          )}
        </DialogContent>
      </Dialog>

      {isLoading ? (
        <LoadingSkeleton variant="grid" />
      ) : isError ? (
        <ErrorState
          title={tx("Không thể tải kênh", "Unable to load channels")}
          description={tx("Không thể tải dữ liệu kênh tin nhắn.", "Channel data could not be loaded.")}
          onRetry={() => void refetch()}
        />
      ) : data && data.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 stagger">
          {data.map((c) => {
            const active = c.status === "active";
            const errored = c.status === "error";
            return (
              <Card key={c.id} glass className="card-lift flex flex-col p-5">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary shadow-inner-edge border border-primary/25">
                      <MessageSquare className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-sm tracking-tight text-foreground">
                        {c.provider === "telegram" ? "Telegram" : "Discord"}
                        {c.bot_username && <span className="text-muted-foreground font-normal"> @{c.bot_username}</span>}
                      </p>
                      <Badge
                        variant={active ? "success" : errored ? "destructive" : "secondary"}
                        className="mt-1 gap-1 text-[10px] py-0 px-1.5 uppercase font-semibold tracking-wider"
                      >
                        {active && <Plug className="h-3 w-3" />}
                        {c.status}
                      </Badge>
                    </div>
                  </div>
                </div>

                <div className="mt-4 flex-1 space-y-1">
                  <div className="font-semibold text-[10px] uppercase tracking-wider text-muted-foreground/80">
                    {tx("ID Kênh", "Channel ID")}
                  </div>
                  <div className="truncate rounded-lg border border-border/40 bg-muted/30 px-2.5 py-1.5 font-mono text-xs text-muted-foreground select-all shadow-inner-edge">
                    {c.id}
                  </div>
                </div>

                <div className="mt-5 flex gap-2 border-t border-border/60 pt-4">
                  <Link href={`/channels/${c.id}`}>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 text-muted-foreground hover:text-foreground active-tactile transition-transform"
                      aria-label={tx(`Xem tin nhắn ${c.provider}`, `View ${c.provider} messages`)}
                    >
                      <Eye className="h-4 w-4" />
                    </Button>
                  </Link>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8 text-muted-foreground hover:text-foreground active-tactile transition-transform"
                    aria-label={tx(`Chỉnh sửa ${c.provider}`, `Edit ${c.provider}`)}
                    onClick={() => {
                      setEditTarget(c);
                      setEditOpen(true);
                    }}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1.5 active-tactile transition-transform"
                    loading={test.isPending}
                    onClick={async () => {
                      const r = await test.mutateAsync(c.id);
                      toast[r.ok ? "success" : "error"](r.message);
                    }}
                  >
                    <TestTube className="h-3.5 w-3.5" /> {tx("Kiểm tra", "Test")}
                  </Button>
                  <ConfirmDialog
                    trigger={
                      <Button size="sm" variant="destructive" className="gap-1.5">
                        <Trash2 className="h-3.5 w-3.5" /> {tx("Xóa", "Delete")}
                      </Button>
                    }
                    title={tx(`Xóa kênh ${c.provider}?`, `Delete ${c.provider} channel?`)}
                    description={tx(
                      "Kết nối kênh này sẽ bị xóa vĩnh viễn.",
                      "This channel connection will be permanently removed."
                    )}
                    confirmLabel={tx("Xóa kênh", "Delete channel")}
                    destructive
                    onConfirm={() => del.mutateAsync(c.id).then(() => undefined)}
                  />
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        <EmptyState
          icon={MessageSquare}
          title={tx("Chưa có kênh tin nhắn nào", "No messaging channels yet")}
          description={tx(
            "Thêm bot Telegram hoặc Discord để bắt đầu nhận tin nhắn.",
            "Add a Telegram or Discord bot to start receiving messages."
          )}
          action={
            <Button className="gap-2 active-tactile transition-transform" onClick={() => setOpen(true)}>
              <Plus className="h-4 w-4" /> {tx("Kênh mới", "New Channel")}
            </Button>
          }
        />
      )}
    </div>
  );
}
