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
  useCurrentRole,
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
import { ConfirmDialog, ErrorState, LoadingSkeleton, DataPagination } from "@/components/shared";
import { PageHeader } from "@/components/page-header";
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
  success: "success",
  error: "destructive",
  timeout: "destructive",
};

function isRunnableArtifact(path: string) {
  return /\.(py|sh)$/i.test(path);
}

function isRenderableArtifact(path: string) {
  return /\.(html?|svg)$/i.test(path);
}

async function fetchText(url: string) {
  const token = getAccessToken();
  const res = await fetch(url, {
    credentials: "include",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
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
  const isAdmin = useCurrentRole() === "admin";
  const artifacts = useWorkspaceArtifacts();
  const executions = useSandboxExecutions();
  const deleteArtifact = useDeleteWorkspaceArtifact();
  const runArtifact = useRunWorkspaceArtifact();
  const deleteExecution = useDeleteSandboxExecution();
  const [previewTitle, setPreviewTitle] = React.useState("");
  const [previewPath, setPreviewPath] = React.useState("");
  const [previewContent, setPreviewContent] = React.useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = React.useState(false);

  const [artifactPage, setArtifactPage] = React.useState(1);
  const [artifactPageSize, setArtifactPageSize] = React.useState(10);
  const paginatedArtifacts = React.useMemo(() => {
    const start = (artifactPage - 1) * artifactPageSize;
    return (artifacts.data || []).slice(start, start + artifactPageSize);
  }, [artifacts.data, artifactPage, artifactPageSize]);

  const [executionPage, setExecutionPage] = React.useState(1);
  const [executionPageSize, setExecutionPageSize] = React.useState(10);
  const paginatedExecutions = React.useMemo(() => {
    const start = (executionPage - 1) * executionPageSize;
    return (executions.data || []).slice(start, start + executionPageSize);
  }, [executions.data, executionPage, executionPageSize]);

  async function openArtifact(artifact: WorkspaceArtifact) {
    try {
      setPreviewTitle(artifact.path);
      setPreviewPath(artifact.path);
      setPreviewContent(await fetchText(`/api/workspace/artifacts/${artifact.id}/content`));
      setPreviewOpen(true);
    } catch (err: any) {
      toast.error(err.message);
    }
  }

  function openExecution(execution: SandboxExecution) {
    setPreviewTitle(`${execution.source} ${execution.status}`);
    setPreviewPath("");
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
        title="Sandbox"
        description="Inspect agent artifacts, execution logs, and run isolated sandbox containers."
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
            {artifacts.isLoading ? <div className="p-6"><LoadingSkeleton variant="table" /></div> : artifacts.isError ? <div className="p-6"><ErrorState title="Unable to load artifacts" description="Workspace artifacts could not be loaded." onRetry={() => void artifacts.refetch()} /></div> : artifacts.data?.length ? (
              <div className="space-y-2">
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
                    {paginatedArtifacts.map((artifact) => (
                      <TableRow key={artifact.id}>
                        <TableCell className="max-w-[280px] truncate font-medium text-foreground">
                          <div className="flex items-center gap-2">
                            <Code2 className="h-4 w-4 text-muted-foreground" />
                            <span className="truncate">{artifact.path}</span>
                          </div>
                        </TableCell>
                        <TableCell className="text-muted-foreground font-mono text-xs">
                          {formatBytes(artifact.size)}
                        </TableCell>
                        <TableCell>
                          <Badge variant={artifact.exists ? "default" : "secondary"} className="text-[10px]">
                            {artifact.exists ? "stored" : "missing"}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-muted-foreground font-mono text-xs">
                          {new Date(artifact.updated_at).toLocaleString()}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1.5">
                            {isRunnableArtifact(artifact.path) && (
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-10 w-10"
                                disabled={!artifact.exists || runArtifact.isPending}
                                aria-label={`Run ${artifact.path}`}
                                onClick={() => runWorkspaceArtifact(artifact)}
                              >
                                <Play className="h-4 w-4" />
                              </Button>
                            )}
                            {(() => {
                              const ext = artifact.path.split(".").pop()?.toLowerCase();
                              const canPreview = ext && ["txt", "md", "json", "py", "js", "ts", "tsx", "jsx", "html", "svg", "css", "yaml", "yml", "sh", "sql", "env"].includes(ext);
                              return (
                                <Button
                                  size="icon"
                                  variant="ghost"
                                  className="h-10 w-10"
                                  disabled={!artifact.exists || !canPreview}
                                  aria-label={`Preview ${artifact.path}`}
                                  onClick={() => openArtifact(artifact)}
                                >
                                  <Eye className="h-4 w-4" />
                                </Button>
                              );
                            })()}
                            <Button size="icon" variant="ghost" className="h-10 w-10" disabled={!artifact.exists} aria-label={`Download ${artifact.path}`} onClick={async () => {
                                try {
                                  await downloadArtifact(artifact);
                                } catch (err: any) {
                                  toast.error(err.message);
                                }
                              }}
                            >
                              <Download className="h-4 w-4" />
                            </Button>
                            {isAdmin && <ConfirmDialog
                              trigger={<Button size="icon" variant="ghost" className="h-10 w-10 text-muted-foreground hover:text-destructive" aria-label={`Delete ${artifact.path}`}><Trash2 className="h-4 w-4" /></Button>}
                              title={`Delete ${artifact.path}?`}
                              description="This workspace artifact will be permanently removed."
                              confirmLabel="Delete artifact"
                              destructive
                              onConfirm={() => deleteArtifact.mutateAsync(artifact.id).then(() => undefined)}
                            />}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <div className="p-3 border-t border-border/60">
                  <DataPagination
                    page={artifactPage}
                    pageSize={artifactPageSize}
                    totalItems={artifacts.data.length}
                    onPageChange={setArtifactPage}
                    onPageSizeChange={setArtifactPageSize}
                    pageSizeOptions={[5, 10, 20]}
                  />
                </div>
              </div>
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
            {executions.isLoading ? <div className="p-6"><LoadingSkeleton variant="table" /></div> : executions.isError ? <div className="p-6"><ErrorState title="Unable to load executions" description="Sandbox execution history could not be loaded." onRetry={() => void executions.refetch()} /></div> : executions.data?.length ? (
              <div className="space-y-2">
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
                    {paginatedExecutions.map((execution) => (
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
                            <Button size="icon" variant="ghost" className="h-10 w-10" onClick={() => openExecution(execution)} aria-label={`View execution ${execution.id}`}>
                              <Eye className="h-4 w-4" />
                            </Button>
                            {isAdmin && <ConfirmDialog
                              trigger={<Button size="icon" variant="ghost" className="h-10 w-10 text-muted-foreground hover:text-destructive" aria-label={`Delete execution ${execution.id}`}><Trash2 className="h-4 w-4" /></Button>}
                              title="Delete this execution?"
                              description="The execution record and its output preview will be removed."
                              confirmLabel="Delete execution"
                              destructive
                              onConfirm={() => deleteExecution.mutateAsync(execution.id).then(() => undefined)}
                            />}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <div className="p-3 border-t border-border/60">
                  <DataPagination
                    page={executionPage}
                    pageSize={executionPageSize}
                    totalItems={executions.data.length}
                    onPageChange={setExecutionPage}
                    onPageSizeChange={setExecutionPageSize}
                    pageSizeOptions={[5, 10, 20]}
                  />
                </div>
              </div>
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
          {previewPath && isRenderableArtifact(previewPath) ? (
            <iframe
              title={`Preview ${previewPath}`}
              sandbox="allow-scripts"
              srcDoc={previewContent || ""}
              className="h-[65vh] w-full rounded-xl border border-border/70 bg-white"
            />
          ) : (
            <pre className="max-h-[65vh] overflow-auto rounded-xl border border-border/70 bg-background/80 p-4 text-xs leading-relaxed text-foreground">
              {previewContent}
            </pre>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
