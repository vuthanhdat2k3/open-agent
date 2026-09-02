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
  Square,
  Globe,
} from "lucide-react";
import {
  useWorkspaceArtifacts,
  useSandboxExecutions,
  useRunWorkspaceArtifact,
  useDeleteWorkspaceArtifact,
  useDeleteSandboxExecution,
  useUrlSearchParam,
  useCurrentRole,
  useMe,
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
import { EmptyState, ErrorState, LoadingSkeleton, DataPagination, ConfirmDialog, WebArtifactPreviewDialog } from "@/components/shared";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { streamSSEGet, api } from "@/lib/api";
import { useTranslation } from "@/lib/i18n";
import { isAdminRole, isOperatorOrAdmin } from "@/lib/roles";
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

const runStatusVariant: Record<string, "default" | "secondary" | "destructive" | "warning" | "success"> = {
  running: "warning",
  succeeded: "success",
  failed: "destructive",
  stopped: "secondary",
};

export default function WorkspacePage() {
  const { t, dict, locale, tx } = useTranslation();
  const [tabParam, setTabParam] = useUrlSearchParam("tab");
  const activeTab = (tabParam as "artifacts" | "executions") || "artifacts";
  const [previewParam, setPreviewParam] = useUrlSearchParam("preview");
  const [executionParam, setExecutionParam] = useUrlSearchParam("execution");

  const artifacts = useWorkspaceArtifacts();
  const executions = useSandboxExecutions();
  const runArtifact = useRunWorkspaceArtifact();
  const deleteArtifact = useDeleteWorkspaceArtifact();
  const deleteExecution = useDeleteSandboxExecution();
  const role = useCurrentRole();
  const me = useMe();
  const currentUserId = me.data?.id;
  const isAdmin = isAdminRole(role);
  const isOperator = isOperatorOrAdmin(role);

  const [selectedUserFilter, setSelectedUserFilter] = React.useState<string>("all");

  const [previewArtifact, setPreviewArtifact] = React.useState<WorkspaceArtifact | null>(null);
  const [previewContent, setPreviewContent] = React.useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [previewTab, setPreviewTab] = React.useState<"preview" | "code">("preview");

  const [viewExecution, setViewExecution] = React.useState<SandboxExecution | null>(null);

  const [runPanel, setRunPanel] = React.useState<{
    executionId: string;
    filename: string;
    status: "running" | "succeeded" | "failed" | "stopped";
    lines: string[];
    exitCode: number | null;
  } | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const terminalEndRef = React.useRef<HTMLDivElement>(null);
  const [isStopping, setIsStopping] = React.useState(false);

  const runPanelLines = runPanel?.lines;
  React.useEffect(() => {
    if (runPanelLines) {
      terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [runPanelLines]);

  const lastClosedParamRef = React.useRef<string | null>(null);
  const lastClosedExecutionRef = React.useRef<string | null>(null);

  // Restore preview from URL search param
  React.useEffect(() => {
    if (previewParam && previewParam !== lastClosedParamRef.current && artifacts.data && !previewArtifact) {
      const art = artifacts.data.find(
        (a) => a.id === previewParam || a.path === previewParam || a.path.endsWith(previewParam)
      );
      if (art) {
        void openArtifact(art);
      }
    }
    if (!previewParam) {
      lastClosedParamRef.current = null;
    }
  }, [previewParam, artifacts.data, previewArtifact]);

  // Restore execution details from URL search param
  React.useEffect(() => {
    if (executionParam && executionParam !== lastClosedExecutionRef.current && executions.data && !viewExecution) {
      const exec = executions.data.find((e) => e.id === executionParam);
      if (exec) {
        setViewExecution(exec);
      }
    }
    if (!executionParam) {
      lastClosedExecutionRef.current = null;
    }
  }, [executionParam, executions.data, viewExecution]);

  React.useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
    };
  }, []);

  const startStream = React.useCallback((executionId: string) => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    streamSSEGet(
      `/api/workspace/executions/${executionId}/stream`,
      (ev) => {
        if (ev.event === "stdout") {
          const line = typeof ev.data?.line === "string" ? ev.data.line : "";
          if (line) {
            setRunPanel((prev) => {
              if (!prev || prev.executionId !== executionId) return prev;
              return {
                ...prev,
                lines: [...prev.lines, line],
              };
            });
          }
        } else if (ev.event === "exit") {
          const code = typeof ev.data?.code === "number" ? ev.data.code : 0;
          setRunPanel((prev) => {
            if (!prev || prev.executionId !== executionId) return prev;
            return {
              ...prev,
              status: code === 0 ? "succeeded" : "failed",
              exitCode: code,
            };
          });
          void executions.refetch();
        } else if (ev.event === "stopped") {
          setRunPanel((prev) => {
            if (!prev || prev.executionId !== executionId) return prev;
            return {
              ...prev,
              status: "stopped",
            };
          });
          void executions.refetch();
        } else if (ev.event === "timed_out") {
          setRunPanel((prev) => {
            if (!prev || prev.executionId !== executionId) return prev;
            return {
              ...prev,
              status: "failed",
            };
          });
          void executions.refetch();
        } else if (ev.event === "error") {
          const msg = (ev.data?.message as string) || (typeof ev.data === "string" ? ev.data : "Error");
          setRunPanel((prev) => {
            if (!prev || prev.executionId !== executionId) return prev;
            return {
              ...prev,
              status: "failed",
              lines: [...prev.lines, `[ERROR] ${msg}`],
            };
          });
          void executions.refetch();
        }
      },
      controller.signal,
    ).catch((err) => {
      if (controller.signal.aborted) return;
      console.error("Workspace stream SSE error:", err);
    });
  }, [executions]);

  async function handleStopExecution() {
    if (!runPanel || runPanel.status !== "running" || isStopping) return;
    setIsStopping(true);
    try {
      await api.post(`/api/workspace/executions/${runPanel.executionId}/stop`);
      toast.success(tx("Đã gửi yêu cầu dừng", "Stop request sent"));
    } catch (err: any) {
      toast.error(err.message || tx("Không thể dừng thực thi", "Failed to stop execution"));
    } finally {
      setIsStopping(false);
    }
  }

  // Extract unique creators for filter dropdown
  const uniqueCreators = React.useMemo(() => {
    const map = new Map<string, { id: string; label: string }>();
    (artifacts.data ?? []).forEach((a) => {
      if (a.created_by_user_id) {
        map.set(a.created_by_user_id, {
          id: a.created_by_user_id,
          label: a.creator_email || a.creator_name || a.created_by_user_id.slice(0, 8),
        });
      }
    });
    (executions.data ?? []).forEach((e) => {
      if (e.created_by_user_id) {
        map.set(e.created_by_user_id, {
          id: e.created_by_user_id,
          label: e.creator_email || e.creator_name || e.created_by_user_id.slice(0, 8),
        });
      }
    });
    return Array.from(map.values());
  }, [artifacts.data, executions.data]);

  // Filtered lists
  const filteredArtifacts = React.useMemo(() => {
    if (selectedUserFilter === "all") return artifacts.data ?? [];
    return (artifacts.data ?? []).filter((a) => a.created_by_user_id === selectedUserFilter);
  }, [artifacts.data, selectedUserFilter]);

  const filteredExecutions = React.useMemo(() => {
    if (selectedUserFilter === "all") return executions.data ?? [];
    return (executions.data ?? []).filter((e) => e.created_by_user_id === selectedUserFilter);
  }, [executions.data, selectedUserFilter]);

  // Pagination states
  const [artifactPage, setArtifactPage] = React.useState(1);
  const [artifactPageSize, setArtifactPageSize] = React.useState(10);
  const paginatedArtifacts = React.useMemo(() => {
    const start = (artifactPage - 1) * artifactPageSize;
    return filteredArtifacts.slice(start, start + artifactPageSize);
  }, [filteredArtifacts, artifactPage, artifactPageSize]);

  const [executionPage, setExecutionPage] = React.useState(1);
  const [executionPageSize, setExecutionPageSize] = React.useState(10);
  const paginatedExecutions = React.useMemo(() => {
    const start = (executionPage - 1) * executionPageSize;
    return filteredExecutions.slice(start, start + executionPageSize);
  }, [filteredExecutions, executionPage, executionPageSize]);

  function isWebArtifact(path: string): boolean {
    const lower = path.toLowerCase();
    return lower.endsWith(".html") || lower.endsWith(".htm") || lower.endsWith(".svg");
  }

  async function openArtifact(artifact: WorkspaceArtifact, initialTab: "preview" | "code" = "preview") {
    setPreviewArtifact(artifact);
    setPreviewTab(isWebArtifact(artifact.path) ? initialTab : "code");
    setPreviewLoading(true);
    setPreviewParam(artifact.path);
    try {
      const res = await fetch(`/api/workspace/artifacts/${artifact.id}/content`);
      if (!res.ok) throw new Error(tx("Không thể tải nội dung tệp tin.", "Failed to load content"));
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
    if (!res.ok) throw new Error(tx("Tải xuống thất bại", "Download failed"));
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
    setExecutionParam(execution.id);
  }

  function isRunnableArtifact(path: string): boolean {
    const lower = path.toLowerCase();
    return (
      lower.endsWith(".py") ||
      lower.endsWith(".sh") ||
      lower.endsWith(".js") ||
      lower.endsWith(".mjs") ||
      lower.endsWith(".cjs")
    );
  }

  async function runWorkspaceArtifact(artifact: WorkspaceArtifact) {
    try {
      const filename = artifact.path.split("/").pop() || artifact.path;
      const res = await runArtifact.mutateAsync(artifact.id);
      setRunPanel({
        executionId: res.execution_id,
        filename,
        status: "running",
        lines: [],
        exitCode: null,
      });
      startStream(res.execution_id);
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

      {/* Segmented Navigation Tabs & Operator User Filter */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-border/70 pb-2">
        <div className="flex gap-2">
          <Button
            type="button"
            variant={activeTab === "artifacts" ? "secondary" : "ghost"}
            onClick={() => setTabParam("artifacts")}
            className="gap-2 font-medium"
          >
            <FileCode2 className="h-4 w-4 text-primary" />
            {dict.pages.workspace.artifactsCard} ({filteredArtifacts.length})
          </Button>

          <Button
            type="button"
            variant={activeTab === "executions" ? "secondary" : "ghost"}
            onClick={() => setTabParam("executions")}
            className="gap-2 font-medium"
          >
            <TerminalSquare className="h-4 w-4 text-primary" />
            {dict.pages.workspace.executionsCard} ({filteredExecutions.length})
          </Button>
        </div>

        {isOperator && uniqueCreators.length > 0 && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-muted-foreground font-medium">{dict.pages.workspace.tableCreator}:</span>
            <select
              value={selectedUserFilter}
              onChange={(e) => {
                setSelectedUserFilter(e.target.value);
                setArtifactPage(1);
                setExecutionPage(1);
              }}
              className="rounded-md border border-input bg-background/80 px-2.5 py-1 text-xs text-foreground shadow-sm focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="all">{dict.pages.workspace.filterAllUsers}</option>
              {uniqueCreators.map((creator) => (
                <option key={creator.id} value={creator.id}>
                  {creator.label}
                </option>
              ))}
            </select>
          </div>
        )}
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
                      <TableHead className="text-xs font-semibold">{dict.pages.workspace.tablePath}</TableHead>
                      <TableHead className="text-xs font-semibold">{dict.pages.workspace.tableSize}</TableHead>
                      <TableHead className="text-xs font-semibold">{tx("Trạng thái", "Status")}</TableHead>
                      {isOperator && (
                        <TableHead className="text-xs font-semibold">{dict.pages.workspace.tableCreator}</TableHead>
                      )}
                      <TableHead className="text-xs font-semibold">{tx("Cập nhật", "Updated")}</TableHead>
                      <TableHead className="text-right text-xs font-semibold">{tx("Thao tác", "Actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {paginatedArtifacts.map((artifact) => (
                      <TableRow key={artifact.id} className="hover:bg-muted/20 transition-colors">
                        <TableCell className="max-w-[300px] truncate font-medium text-foreground text-xs">
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
                        {isOperator && (
                          <TableCell className="text-xs text-muted-foreground max-w-[160px] truncate">
                            <span className="font-mono text-[11px] bg-muted/50 px-1.5 py-0.5 rounded border border-border/50">
                              {artifact.creator_email || artifact.creator_name || artifact.created_by_user_id?.slice(0, 8) || "—"}
                            </span>
                          </TableCell>
                        )}
                        <TableCell className="text-muted-foreground font-mono text-xs">
                          {new Date(artifact.updated_at).toLocaleString(tx("vi-VN", "en-US"))}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1.5">
                            {isWebArtifact(artifact.path) && (
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-8 w-8 text-primary hover:text-primary hover:bg-primary/10"
                                disabled={!artifact.exists}
                                aria-label={tx(`Chạy trực tiếp ${artifact.path}`, `Live preview ${artifact.path}`)}
                                title={tx(`Chạy trực tiếp ${artifact.path}`, `Live preview ${artifact.path}`)}
                                onClick={() => openArtifact(artifact, "preview")}
                              >
                                <Globe className="h-3.5 w-3.5" />
                              </Button>
                            )}
                            {isRunnableArtifact(artifact.path) && (
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-8 w-8"
                                disabled={!artifact.exists || runArtifact.isPending}
                                aria-label={tx(`Chạy ${artifact.path}`, `Run ${artifact.path}`)}
                                title={tx(`Chạy ${artifact.path}`, `Run ${artifact.path}`)}
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
                                  aria-label={tx(`Xem trước ${artifact.path}`, `Preview ${artifact.path}`)}
                                  title={tx(`Xem trước ${artifact.path}`, `Preview ${artifact.path}`)}
                                  onClick={() => openArtifact(artifact, isWebArtifact(artifact.path) ? "preview" : "code")}
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
                              aria-label={tx(`Tải xuống ${artifact.path}`, `Download ${artifact.path}`)}
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
                            {(isOperator || !artifact.created_by_user_id || artifact.created_by_user_id === currentUserId) && (
                              <ConfirmDialog
                                trigger={<Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-destructive" aria-label={tx(`Xóa ${artifact.path}`, `Delete ${artifact.path}`)}><Trash2 className="h-3.5 w-3.5" /></Button>}
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
                      <TableHead className="text-xs font-semibold">{dict.pages.workspace.executionsCard}</TableHead>
                      <TableHead className="text-xs font-semibold">{tx("Trạng thái", "Status")}</TableHead>
                      {isOperator && (
                        <TableHead className="text-xs font-semibold">{dict.pages.workspace.tableCreator}</TableHead>
                      )}
                      <TableHead className="text-right text-xs font-semibold">{dict.pages.workspace.tableTime}</TableHead>
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
                        {isOperator && (
                          <TableCell className="text-xs text-muted-foreground max-w-[160px] truncate">
                            <span className="font-mono text-[11px] bg-muted/50 px-1.5 py-0.5 rounded border border-border/50">
                              {execution.creator_email || execution.creator_name || execution.created_by_user_id?.slice(0, 8) || "—"}
                            </span>
                          </TableCell>
                        )}
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
                              aria-label={tx(`Xem thực thi ${execution.id}`, `View execution ${execution.id}`)}
                            >
                              <Eye className="h-3.5 w-3.5" />
                            </Button>
                            {(isOperator || !execution.created_by_user_id || execution.created_by_user_id === currentUserId) && (
                              <ConfirmDialog
                                trigger={<Button size="icon" variant="ghost" className="h-8 w-8 text-muted-foreground hover:text-destructive" aria-label={tx(`Xóa thực thi ${execution.id}`, `Delete execution ${execution.id}`)}><Trash2 className="h-3.5 w-3.5" /></Button>}
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

      {/* Interactive Web & Artifact Preview Dialog */}
      <WebArtifactPreviewDialog
        open={Boolean(previewArtifact)}
        onOpenChange={(open) => {
          if (!open) {
            lastClosedParamRef.current = previewParam;
            setPreviewArtifact(null);
            setPreviewContent(null);
            setPreviewParam(null);
          }
        }}
        title={previewArtifact?.path || "artifact"}
        content={previewContent || ""}
        initialTab={previewTab}
        onDownload={previewArtifact ? () => downloadArtifact(previewArtifact) : undefined}
      />

      {/* Execution Output Modal */}
      <Dialog
        open={Boolean(viewExecution)}
        onOpenChange={(open) => {
          if (!open) {
            lastClosedExecutionRef.current = executionParam;
            setViewExecution(null);
            setExecutionParam(null);
          }
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

      {/* Run Output Panel Sheet */}
      <Sheet
        open={Boolean(runPanel)}
        onOpenChange={(open) => {
          if (!open) {
            if (abortRef.current) {
              abortRef.current.abort();
              abortRef.current = null;
            }
            setRunPanel(null);
          }
        }}
      >
        <SheetContent
          side="right"
          className="w-full sm:max-w-[600px] flex flex-col h-full bg-card border-l border-border/80 p-0 shadow-3d-floating"
        >
          <SheetHeader className="p-4 border-b border-border/70 flex flex-row items-center justify-between space-y-0">
            <div className="flex items-center gap-2 min-w-0 pr-6">
              <TerminalSquare className="h-4 w-4 text-primary shrink-0" />
              <SheetTitle className="font-mono text-sm font-semibold truncate">
                {runPanel?.filename}
              </SheetTitle>
              {runPanel && (
                <Badge
                  variant={runStatusVariant[runPanel.status] || "secondary"}
                  className="text-[10px] uppercase tracking-wider shrink-0"
                >
                  {runPanel.status === "running"
                    ? tx("Đang chạy", "Running")
                    : runPanel.status === "succeeded"
                    ? tx("Thành công", "Succeeded")
                    : runPanel.status === "failed"
                    ? tx("Thất bại", "Failed")
                    : tx("Đã dừng", "Stopped")}
                </Badge>
              )}
            </div>
          </SheetHeader>

          <div className="flex-1 min-h-0 p-4 flex flex-col">
            <div className="flex-1 bg-black text-green-400 font-mono text-xs p-4 rounded-lg overflow-y-auto border border-zinc-800 shadow-inner space-y-1">
              {runPanel?.lines.length === 0 ? (
                <div className="text-zinc-500 italic">
                  {runPanel.status === "running"
                    ? dict.pages.workspace.runPanelConnecting
                    : dict.pages.workspace.runPanelNoOutput}
                </div>
              ) : (
                runPanel?.lines.map((line, idx) => (
                  <div
                    key={idx}
                    className={cn(
                      "whitespace-pre-wrap leading-relaxed break-all",
                      line.startsWith("[ERROR]") ? "text-red-400" : "text-green-400"
                    )}
                  >
                    {line}
                  </div>
                ))
              )}
              <div ref={terminalEndRef} />
            </div>
          </div>

          <div className="p-4 border-t border-border/70 bg-muted/20 flex items-center justify-between gap-3">
            <div>
              {runPanel?.exitCode !== null && runPanel?.exitCode !== undefined && (
                <div className="text-xs font-mono text-muted-foreground">
                  <span className="font-semibold">{dict.pages.workspace.runPanelExitCode}</span>{" "}
                  <span
                    className={cn(
                      "font-bold",
                      runPanel.exitCode === 0 ? "text-emerald-500" : "text-rose-500"
                    )}
                  >
                    {runPanel.exitCode}
                  </span>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              {runPanel?.status === "running" && (
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={isStopping}
                  onClick={handleStopExecution}
                  className="gap-1.5 text-xs font-medium"
                >
                  <Square className="h-3.5 w-3.5 fill-current" />
                  {dict.pages.workspace.runPanelStop}
                </Button>
              )}
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  if (abortRef.current) {
                    abortRef.current.abort();
                    abortRef.current = null;
                  }
                  setRunPanel(null);
                }}
                className="text-xs"
              >
                {tx("Đóng", "Close")}
              </Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
