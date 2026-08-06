"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  Code2,
  Download,
  Eye,
  FileCode2,
  FolderKanban,
  Play,
  RefreshCw,
  TerminalSquare,
  Trash2,
} from "lucide-react";
import {
  useDeleteSandboxExecution,
  useDeleteWorkspaceArtifact,
  useRunWorkspaceArtifact,
  useSandboxExecutions,
  useWorkspaceArtifacts,
} from "@/hooks";
import { getAccessToken } from "@/lib/auth";
import type { SandboxExecution, WorkspaceArtifact } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatMs(ms: number | null) {
  if (ms == null) return "running";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

const executionVariant: Record<string, "secondary" | "warning" | "success" | "destructive"> = {
  running: "warning",
  succeeded: "success",
  failed: "destructive",
  timed_out: "destructive",
};

function isRunnableArtifact(path: string) {
  return /\.(py|sh)$/i.test(path);
}

async function fetchText(path: string) {
  const token = getAccessToken();
  const res = await fetch(path, {
    credentials: "include",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new Error(`request failed: ${res.status}`);
  return res.text();
}

async function downloadArtifact(artifact: WorkspaceArtifact) {
  const token = getAccessToken();
  const res = await fetch(`/api/workspace/artifacts/${artifact.id}/download`, {
    credentials: "include",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new Error(`download failed: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = artifact.path.split("/").pop() || "artifact";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export default function WorkspacePage() {
  const artifacts = useWorkspaceArtifacts();
  const executions = useSandboxExecutions();
  const deleteArtifact = useDeleteWorkspaceArtifact();
  const runArtifact = useRunWorkspaceArtifact();
  const deleteExecution = useDeleteSandboxExecution();
  const [previewTitle, setPreviewTitle] = React.useState("");
  const [previewContent, setPreviewContent] = React.useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = React.useState(false);

  async function openArtifact(artifact: WorkspaceArtifact) {
    try {
      setPreviewTitle(artifact.path);
      setPreviewContent(await fetchText(`/api/workspace/artifacts/${artifact.id}/content`));
      setPreviewOpen(true);
    } catch (err: any) {
      toast.error(err.message);
    }
  }

  function openExecution(execution: SandboxExecution) {
    setPreviewTitle(`${execution.source} ${execution.status}`);
    setPreviewContent(execution.stdout_preview || execution.error || "(no output)");
    setPreviewOpen(true);
  }

  async function runWorkspaceArtifact(artifact: WorkspaceArtifact) {
    try {
      await runArtifact.mutateAsync(artifact.id);
      toast.success(`Started ${artifact.path}`);
    } catch (err: any) {
      toast.error(err.message);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={FolderKanban}
        title="Workspace"
        description="Manage agent-generated files and code execution history"
        actions={
          <Button
            variant="outline"
            className="gap-2"
            onClick={() => {
              artifacts.refetch();
              executions.refetch();
            }}
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        }
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(420px,0.8fr)]">
        <Card glass className="overflow-hidden shadow-3d-card">
          <CardHeader className="flex flex-row items-center gap-3 border-b border-border/60 bg-muted/20">
            <FileCode2 className="h-4 w-4 text-primary" />
            <CardTitle className="text-sm font-semibold">Artifacts</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {artifacts.isLoading ? (
              <div className="space-y-2 p-6">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-11 w-full" />
                ))}
              </div>
            ) : artifacts.data?.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Path</TableHead>
                    <TableHead>Size</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Updated</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {artifacts.data.map((artifact) => (
                    <TableRow key={artifact.id}>
                      <TableCell className="max-w-[320px] truncate font-mono text-xs text-foreground">
                        {artifact.path}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {formatBytes(artifact.size)}
                      </TableCell>
                      <TableCell>
                        <Badge variant={artifact.exists ? "success" : "destructive"} className="text-[10px] uppercase tracking-wider">
                          {artifact.exists ? "present" : "missing"}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-[11px] text-muted-foreground">
                        {new Date(artifact.updated_at).toLocaleString()}
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-1.5">
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8 text-primary"
                            disabled={!artifact.exists || !isRunnableArtifact(artifact.path) || runArtifact.isPending}
                            onClick={() => runWorkspaceArtifact(artifact)}
                            title={isRunnableArtifact(artifact.path) ? "Run file" : "Only .py and .sh files can run"}
                            aria-label={`Run ${artifact.path}`}
                          >
                            <Play className="h-4 w-4" />
                          </Button>
                          <Button size="icon" variant="ghost" className="h-8 w-8" disabled={!artifact.exists} onClick={() => openArtifact(artifact)}>
                            <Eye className="h-4 w-4" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8"
                            disabled={!artifact.exists}
                            onClick={async () => {
                              try {
                                await downloadArtifact(artifact);
                              } catch (err: any) {
                                toast.error(err.message);
                              }
                            }}
                          >
                            <Download className="h-4 w-4" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8 text-muted-foreground hover:text-destructive"
                            onClick={() => deleteArtifact.mutate(artifact.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <EmptyState
                icon={FileCode2}
                title="No artifacts yet"
                description="Ask an agent to write a file with write_file."
              />
            )}
          </CardContent>
        </Card>

        <Card glass className="overflow-hidden shadow-3d-card">
          <CardHeader className="flex flex-row items-center gap-3 border-b border-border/60 bg-muted/20">
            <TerminalSquare className="h-4 w-4 text-primary" />
            <CardTitle className="text-sm font-semibold">Executions</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {executions.isLoading ? (
              <div className="space-y-2 p-6">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-11 w-full" />
                ))}
              </div>
            ) : executions.data?.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Run</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Time</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {executions.data.map((execution) => (
                    <TableRow key={execution.id}>
                      <TableCell>
                        <div className="flex min-w-0 items-center gap-2">
                          <Code2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                          <div className="min-w-0">
                            <div className="truncate text-xs font-semibold text-foreground">
                              {execution.source}
                              {execution.language ? `/${execution.language}` : ""}
                            </div>
                            <div className="truncate font-mono text-[10px] text-muted-foreground">
                              {execution.command || "(no command)"}
                            </div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={executionVariant[execution.status] || "secondary"} className="text-[10px] uppercase tracking-wider">
                          {execution.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">
                        {formatMs(execution.duration_ms)}
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-1.5">
                          <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => openExecution(execution)}>
                            <Eye className="h-4 w-4" />
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8 text-muted-foreground hover:text-destructive"
                            onClick={() => deleteExecution.mutate(execution.id)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <EmptyState
                icon={TerminalSquare}
                title="No executions yet"
                description="run_code and sandbox API calls will appear here."
              />
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle className="font-mono text-sm">{previewTitle}</DialogTitle>
            <DialogDescription>Read-only preview</DialogDescription>
          </DialogHeader>
          <pre className="max-h-[65vh] overflow-auto rounded-xl border border-border/70 bg-background/80 p-4 text-xs leading-relaxed text-foreground">
            {previewContent}
          </pre>
        </DialogContent>
      </Dialog>
    </div>
  );
}
