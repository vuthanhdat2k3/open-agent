"use client";

import * as React from "react";
import { toast } from "sonner";
import {
  FolderKanban,
  FileCode2,
  TerminalSquare,
  Play,
  Download,
  Trash2,
  Eye,
  RefreshCw,
  Code2,
  Layers,
} from "lucide-react";
import {
  useWorkspaceArtifacts,
  useSandboxExecutions,
  useRunWorkspaceArtifact,
  useDeleteWorkspaceArtifact,
  useDeleteSandboxExecution,
  useUrlSearchParam,
  useCurrentRole,
} from "@/hooks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageHeader } from "@/components/page-header";
import { EmptyState, ErrorState, LoadingSkeleton, DataPagination, ConfirmDialog } from "@/components/shared";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useTranslation } from "@/lib/i18n";
import type { WorkspaceArtifact, SandboxExecution } from "@/types";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatMs(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

const executionVariant: Record<string, "default" | "secondary" | "destructive" | "outline" | "success" | "warning"> = {
  succeeded: "success",
  failed: "destructive",
  running: "warning",
  queued: "secondary",
};

export default function WorkspacePage() {
  const { t, dict, locale, tx } = useTranslation();
  const [tabParam, setTabParam] = useUrlSearchParam("tab");
  const activeTab = (tabParam as "artifacts" | "executions") || "artifacts";

  const artifacts = useWorkspaceArtifacts();
  const executions = useSandboxExecutions();
  const runArtifact = useRunWorkspaceArtifact();
  const deleteArtifact = useDeleteWorkspaceArtifact();
  const deleteExecution = useDeleteSandboxExecution();
  const role = useCurrentRole();
  const isAdmin = role === "admin" || role === "platform_admin";

  const [previewArtifact, setPreviewArtifact] = React.useState<WorkspaceArtifact | null>(null);
  const [previewContent, setPreviewContent] = React.useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = React.useState(false);

  const [viewExecution, setViewExecution] = React.useState<SandboxExecution | null>(null);

  // Pagination states
  const [artifactPage, setArtifactPage] = React.useState(1);
  const [artifactPageSize, setArtifactPageSize] = React.useState(10);
  const paginatedArtifacts = React.useMemo(() => {
    const start = (artifactPage - 1) * artifactPageSize;
    return (artifacts.data ?? []).slice(start, start + artifactPageSize);
  }, [artifacts.data, artifactPage, artifactPageSize]);

  const [executionPage, setExecutionPage] = React.useState(1);
  const [executionPageSize, setExecutionPageSize] = React.useState(10);
  const paginatedExecutions = React.useMemo(() => {
    const start = (executionPage - 1) * executionPageSize;
    return (executions.data ?? []).slice(start, start + executionPageSize);
  }, [executions.data, executionPage, executionPageSize]);

  async function openArtifact(artifact: WorkspaceArtifact) {
    setPreviewArtifact(artifact);
    setPreviewLoading(true);
    try {
      const res = await fetch(`/api/workspace/artifacts/${artifact.id}/content`);
      if (!res.ok) throw new Error("Failed to load content");
      const text = await res.text();
      setPreviewContent(text);
    } catch {
      setPreviewContent(tx("Không thể tải nội dung tệp tin.", "Unable to load artifact content."));
    } finally {
      setPreviewLoading(false);
    }
  }

  async function downloadArtifact(artifact: WorkspaceArtifact) {
    const res = await fetch(`/api/workspace/artifacts/${artifact.id}/content`);
    if (!res.ok) throw new Error("Download failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = artifact.path.split("/").pop() || "artifact";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function openExecution(execution: SandboxExecution) {
    setViewExecution(execution);
  }

  function isRunnableArtifact(path: string): boolean {
    const lower = path.toLowerCase();
    return (
      lower.endsWith(".py") ||
      lower.endsWith(".sh") ||
      lower.endsWith(".js") ||
      lower.endsWith(".ts")
    );
  }

  async function runWorkspaceArtifact(artifact: WorkspaceArtifact) {
    try {
      await runArtifact.mutateAsync(artifact.id);
      toast.success(tx(`Đã khởi chạy ${artifact.path}`, `Started ${artifact.path}`));
    } catch (err: any) {
      toast.error(err.message);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={FolderKanban}
        title={dict.pages.workspace.title}
        description={dict.pages.workspace.description}
        actions={
          <Button
            variant="outline"
            className="gap-2"
            onClick={() => {
              void artifacts.refetch();
              void executions.refetch();
            }}
          >
            <RefreshCw className="h-4 w-4" />
            {tx("Làm mới", "Refresh")}
          </Button>
        }
      />

      {/* Segmented Navigation Tabs */}
      <div className="flex gap-2 border-b border-border/70 pb-2">
        <Button
          type="button"
          variant={activeTab === "artifacts" ? "secondary" : "ghost"}
          onClick={() => setTabParam("artifacts")}
          className="gap-2 font-medium"
        >
          <FileCode2 className="h-4 w-4 text-primary" />
          {tx("Tệp Artifacts", "Artifacts")} ({artifacts.data?.length ?? 0})
        </Button>

        <Button
          type="button"
          variant={activeTab === "executions" ? "secondary" : "ghost"}
          onClick={() => setTabParam("executions")}
          className="gap-2 font-medium"
        >
          <TerminalSquare className="h-4 w-4 text-primary" />
          {tx("Lịch sử Thực thi Sandbox", "Sandbox Executions")} ({executions.data?.length ?? 0})
        </Button>
      </div>

      {/* Tab 1: Artifacts Table */}
      {activeTab === "artifacts" && (
        <Card glass className="overflow-hidden shadow-card border-border/80">
          <CardContent className="p-0">
            {artifacts.isLoading ? (
              <div className="p-6"><LoadingSkeleton variant="table" /></div>
            ) : artifacts.isError ? (
              <div className="p-6">
                <ErrorState
                  title={tx("Không thể tải artifacts", "Unable to load artifacts")}
                  description={tx("Dữ liệu artifacts không khả dụng.", "Workspace artifacts could not be loaded.")}
                  onRetry={() => void artifacts.refetch()}
                />
              </div>
            ) : artifacts.data?.length ? (
              <div>
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40">
                      <TableHead className="text-xs font-semibold">{tx("Đường dẫn tệp", "Path")}</TableHead>
                      <TableHead className="text-xs font-semibold">{tx("Kích thước", "Size")}</TableHead>
                      <TableHead className="text-xs font-semibold">{tx("Trạng thái", "Status")}</TableHead>
                      <TableHead className="text-xs font-semibold">{tx("Cập nhật", "Updated")}</TableHead>
                      <TableHead className="text-right text-xs font-semibold">{tx("Thao tác", "Actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedArtifacts.map((artifact) => (
                      <TableRow key={artifact.id} className="hover:bg-muted/20 transition-colors">
                        <TableCell className="max-w-[320px] truncate font-medium text-foreground text-xs">
                          <div className="flex items-center gap-2">
                            <Code2 className="h-4 w-4 text-muted-foreground shrink-0" />
                            <span className="truncate">{artifact.path}</span>
                          </div>
                        </TableCell>
                        <TableCell className="text-muted-foreground font-mono text-xs">
                          {formatBytes(artifact.size)}
                        </TableCell>
                        <TableCell>
                          <Badge variant={artifact.exists ? "default" : "secondary"} className="text-[10px]">
                            {artifact.exists ? (tx("Đã lưu", "stored")) : (tx("Thất lạc", "missing"))}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-muted-foreground font-mono text-xs">
                          {new Date(artifact.updated_at).toLocaleString(tx("vi-VN", "en-US"))}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1.5">
                            {isRunnableArtifact(artifact.path) && (
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-8 w-8"
                                disabled={!artifact.exists || runArtifact.isPending}
                                aria-label={`Run ${artifact.path}`}
                                onClick={() => runWorkspaceArtifact(artifact)}
                              >
                                <Play className="h-3.5 w-3.5" />
                              </Button>
                            )}
                            {(() => {
                              const ext = artifact.path.split(".").pop()?.toLowerCase();
                              const canPreview = ext && ["txt", "md", "json", "py", "js", "ts", "tsx", "jsx", "html", "svg", "css", "yaml", "yml", "sh", "sql", "env"].includes(ext);
                              return (
                                <Button
                                  size="icon"
                                  variant="ghost"
                                  className="h-8 w-8"
                                  disabled={!artifact.exists || !canPreview}
                                  aria-label={`Preview ${artifact.path}`}
                                  onClick={() => openArtifact(artifact)}
                                >
                                  <Eye className="h-3.5 w-3.5" />
                                </Button>
                              );
                            })()}
                            <Button
                              size="icon"
                              variant="ghost"
                              className="h-8 w-8"
                              disabled={!artifact.exists}
                              aria-label={`Download ${artifact.path}`}
                              onClick={async () => {
                                try {
                                  await downloadArtifact(artifact);
                                } catch (err: any) {
                                  toast.error(err.message);
                                }
                              }}
                            >
                              <Download className="h-3.5 w-3.5" />
                            </Button>
                            {isAdmin && (
                              <ConfirmDialog
                                trigger={<Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-destructive" aria-label={`Delete ${artifact.path}`}><Trash2 className="h-3.5 w-3.5" /></Button>}
                                title={tx(`Xóa ${artifact.path}?`, `Delete ${artifact.path}?`)}
                                description={tx("Tệp workspace này sẽ bị xóa vĩnh viễn khỏi sandbox.", "This workspace artifact will be permanently removed.")}
                                confirmLabel={tx("Xóa tệp", "Delete artifact")}
                                destructive
                                onConfirm={() => deleteArtifact.mutateAsync(artifact.id).then(() => undefined)}
                              />
                            )}
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
                    pageSizeOptions={[5, 10, 25, 50]}
                  />
                </div>
              </div>
            ) : (
              <EmptyState
                icon={FileCode2}
                title={tx("Chưa có artifact nào", "No artifacts yet")}
                description={tx("Yêu cầu Agent viết tệp hoặc chạy tác vụ để sinh artifacts.", "Ask an agent to write a file with write_file.")}
              />
            )}
          </CardContent>
        </Card>
      )}

      {/* Tab 2: Executions Table */}
      {activeTab === "executions" && (
        <Card glass className="overflow-hidden shadow-card border-border/80">
          <CardContent className="p-0">
            {executions.isLoading ? (
              <div className="p-6"><LoadingSkeleton variant="table" /></div>
            ) : executions.isError ? (
              <div className="p-6">
                <ErrorState
                  title={tx("Không thể tải lịch sử thực thi", "Unable to load executions")}
                  description={tx("Lịch sử sandbox không khả dụng.", "Sandbox execution history could not be loaded.")}
                  onRetry={() => void executions.refetch()}
                />
              </div>
            ) : executions.data?.length ? (
              <div>
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40">
                      <TableHead className="text-xs font-semibold">{tx("Tác vụ / Lệnh", "Run")}</TableHead>
                      <TableHead className="text-xs font-semibold">{tx("Trạng thái", "Status")}</TableHead>
                      <TableHead className="text-right text-xs font-semibold">{tx("Thời gian", "Time")}</TableHead>
                      <TableHead className="text-right text-xs font-semibold">{tx("Thao tác", "Actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedExecutions.map((execution) => (
                      <TableRow key={execution.id} className="hover:bg-muted/20 transition-colors">
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
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1.5">
                            <Button
                              size="icon"
                              variant="ghost"
                              className="h-8 w-8"
                              onClick={() => openExecution(execution)}
                              aria-label={`View execution ${execution.id}`}
                            >
                              <Eye className="h-3.5 w-3.5" />
                            </Button>
                            {isAdmin && (
                              <ConfirmDialog
                                trigger={<Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-destructive" aria-label={`Delete execution ${execution.id}`}><Trash2 className="h-3.5 w-3.5" /></Button>}
                                title={tx("Xóa bản ghi thực thi này?", "Delete this execution?")}
                                description={tx("Bản ghi thực thi và kết quả output sẽ bị xóa vĩnh viễn.", "The execution record and its output preview will be removed.")}
                                confirmLabel={tx("Xóa bản ghi", "Delete execution")}
                                destructive
                                onConfirm={() => deleteExecution.mutateAsync(execution.id).then(() => undefined)}
                              />
                            )}
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
                    pageSizeOptions={[5, 10, 25, 50]}
                  />
                </div>
              </div>
            ) : (
              <EmptyState
                icon={TerminalSquare}
                title={tx("Chưa có lần thực thi nào", "No executions yet")}
                description={tx("Các lệnh code chạy trong sandbox container sẽ xuất hiện tại đây.", "Code runs executed in isolated containers will be listed here.")}
              />
            )}
          </CardContent>
        </Card>
      )}

      {/* Artifact Preview Modal */}
      <Dialog
        open={Boolean(previewArtifact)}
        onOpenChange={(open) => {
          if (!open) {
            setPreviewArtifact(null);
            setPreviewContent(null);
          }
        }}
      >
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 font-mono text-sm">
              <FileCode2 className="h-4 w-4 text-primary" />
              {previewArtifact?.path}
            </DialogTitle>
          </DialogHeader>
          <div className="max-h-[60vh] overflow-auto rounded-lg border border-border/80 bg-muted/30 p-4 font-mono text-xs">
            {previewLoading ? (
              <p className="text-muted-foreground">{tx("Đang tải nội dung tệp...", "Loading content...")}</p>
            ) : (
              <pre className="whitespace-pre-wrap">{previewContent}</pre>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Execution Output Modal */}
      <Dialog
        open={Boolean(viewExecution)}
        onOpenChange={(open) => {
          if (!open) setViewExecution(null);
        }}
      >
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-sm font-semibold">
              <TerminalSquare className="h-4 w-4 text-primary" />
              {tx("Chi tiết thực thi", "Execution Details")}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="font-semibold text-muted-foreground">{tx("Nguồn:", "Source:")}</span>{" "}
                <span className="font-mono">{viewExecution?.source}</span>
              </div>
              <div>
                <span className="font-semibold text-muted-foreground">{tx("Trạng thái:", "Status:")}</span>{" "}
                <Badge variant={executionVariant[viewExecution?.status || ""] || "secondary"} className="text-[10px]">
                  {viewExecution?.status}
                </Badge>
              </div>
              <div>
                <span className="font-semibold text-muted-foreground">{tx("Mã thoát:", "Exit code:")}</span>{" "}
                <span className="font-mono">{viewExecution?.exit_code ?? "—"}</span>
              </div>
              <div>
                <span className="font-semibold text-muted-foreground">{tx("Thời lượng:", "Duration:")}</span>{" "}
                <span className="font-mono">{formatMs(viewExecution?.duration_ms ?? null)}</span>
              </div>
            </div>
            {viewExecution?.command && (
              <div>
                <p className="mb-1 font-semibold text-muted-foreground">{tx("Lệnh thực thi:", "Command:")}</p>
                <pre className="rounded bg-muted/40 p-2 font-mono">{viewExecution.command}</pre>
              </div>
            )}
            <div>
              <p className="mb-1 font-semibold text-muted-foreground">{tx("Kết quả Output / Logs:", "Output preview:")}</p>
              <pre className="max-h-60 overflow-auto rounded bg-muted/40 p-2 font-mono whitespace-pre-wrap">
                {viewExecution?.stdout_preview || (tx("(không có output)", "(no output)"))}
              </pre>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
