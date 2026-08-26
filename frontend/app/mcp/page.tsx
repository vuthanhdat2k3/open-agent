"use client";

import * as React from "react";
import { toast } from "sonner";
import { Network, Plus, Pencil, Plug, Unplug, Wrench, Trash2 } from "lucide-react";
import {
  useMcpServers,
  useCreateMcp,
  useDeleteMcp,
  useConnectMcp,
  useDisconnectMcp,
  useUpdateMcp,
} from "@/hooks";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { McpServerForm } from "@/components/mcp/mcp-server-form";
import { ConfirmDialog, ErrorState, LoadingSkeleton } from "@/components/shared";
import type { McpServer } from "@/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export default function McpPage() {
  const { data, isLoading, isError, refetch } = useMcpServers();
  const create = useCreateMcp();
  const del = useDeleteMcp();
  const connect = useConnectMcp();
  const disconnect = useDisconnectMcp();
  const update = useUpdateMcp();
  const [open, setOpen] = React.useState(false);
  const [editOpen, setEditOpen] = React.useState(false);
  const [editTarget, setEditTarget] = React.useState<McpServer | null>(null);

  return (
    <div className="space-y-6">
      <PageHeader
        icon={Network}
        title="Tool Registry & MCP Integrations"
        description="Register Model Context Protocol (MCP) servers, inspect capabilities, and grant external tools to AI agents."
        actions={
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="gap-2 active-tactile transition-transform">
                <Plus className="h-4 w-4" /> New Server
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>New MCP Server</DialogTitle>
              </DialogHeader>
              <McpServerForm
                onSubmit={async (values) => {
                  try {
                    await create.mutateAsync(values);
                    toast.success("Server created");
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
            <DialogTitle>Edit MCP Server</DialogTitle>
          </DialogHeader>
          {editTarget && (
            <McpServerForm
              initial={editTarget}
              onSubmit={async (values) => {
                try {
                  await update.mutateAsync({ id: editTarget.id, ...values });
                  toast.success("Server updated");
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

      {isLoading ? <LoadingSkeleton variant="grid" /> : isError ? <ErrorState title="Unable to load MCP servers" description="MCP server data could not be loaded." onRetry={() => void refetch()} /> : data && data.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 stagger">
          {data.map((s) => {
            const connected = s.connection_status === "connected";
            const errored = s.connection_status === "error";
            return (
              <Card key={s.id} glass className="card-lift flex flex-col p-5">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary shadow-inner-edge border border-primary/25">
                      <Network className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-sm tracking-tight text-foreground">{s.name}</p>
                      <Badge
                        variant={connected ? "success" : errored ? "destructive" : "secondary"}
                        className="mt-1 gap-1 text-[10px] py-0 px-1.5 uppercase font-semibold tracking-wider"
                      >
                        {connected && <Plug className="h-3 w-3" />}
                        {s.connection_status}
                      </Badge>
                    </div>
                  </div>
                </div>
                
                <div className="mt-4 flex-1 space-y-1">
                  <div className="font-semibold text-[10px] uppercase tracking-wider text-muted-foreground/80">Command / transport</div>
                  <div className="truncate rounded-lg border border-border/40 bg-muted/30 px-2.5 py-1.5 font-mono text-xs text-muted-foreground select-all shadow-inner-edge">
                    <span className="text-foreground font-semibold">{s.transport}</span>{" "}
                    {s.command} {s.args.join(" ")} {s.url}
                  </div>
                </div>

                {s.tools.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-border/40 space-y-1.5">
                    <div className="text-[10px] uppercase tracking-wider font-semibold text-muted-foreground/80">Tools exposed</div>
                    <div className="flex flex-wrap gap-1.5">
                      {s.tools.map((t) => (
                        <Badge key={t.id} variant="outline" className="gap-1 font-mono text-[10px] bg-muted/30 border-border/60">
                          <Wrench className="h-2.5 w-2.5" /> {t.name}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mt-5 flex gap-2 border-t border-border/60 pt-4">
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8 text-muted-foreground hover:text-foreground active-tactile transition-transform"
                    aria-label={`Edit ${s.name}`}
                    onClick={() => {
                      setEditTarget(s);
                      setEditOpen(true);
                    }}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  {connected ? (
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1.5 active-tactile transition-transform ml-auto"
                      onClick={() => disconnect.mutate(s.id)}
                    >
                      <Unplug className="h-3.5 w-3.5" /> Disconnect
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      className="gap-1.5 active-tactile transition-transform ml-auto"
                      loading={connect.isPending}
                      onClick={async () => {
                        const r = await connect.mutateAsync(s.id);
                        toast[r.ok ? "success" : "error"](r.message);
                      }}
                    >
                      <Plug className="h-3.5 w-3.5" /> Connect
                    </Button>
                  )}
                  <ConfirmDialog
                    trigger={<Button size="sm" variant="destructive" className="gap-1.5"><Trash2 className="h-3.5 w-3.5" /> Delete</Button>}
                    title={`Delete ${s.name}?`}
                    description="This MCP server configuration will be permanently removed."
                    confirmLabel="Delete server"
                    destructive
                    onConfirm={() => del.mutateAsync(s.id).then(() => undefined)}
                  />
                </div>
              </Card>
            );
          })}
        </div>
      ) : (
        <EmptyState
          icon={Network}
          title="No MCP servers yet"
          description="Add one to expose external tools."
          action={
            <Button className="gap-2 active-tactile transition-transform" onClick={() => setOpen(true)}>
              <Plus className="h-4 w-4" /> New Server
            </Button>
          }
        />
      )}
    </div>
  );
}
