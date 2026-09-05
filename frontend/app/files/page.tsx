"use client";

import * as React from "react";
import { toast } from "sonner";
import { Upload, Trash2, FileText, Loader2 } from "lucide-react";
import {
  useCan,
  useFiles,
  useUploadFile,
  useDeleteFile,
  useIngestFile,
} from "@/hooks";
import type { UploadedFile } from "@/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { useTranslation, statusLabel } from "@/lib/i18n";
import { ConfirmDialog, ErrorState, LoadingSkeleton, DataPagination } from "@/components/shared";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const statusVariant: Record<
  string,
  "secondary" | "warning" | "success" | "destructive"
> = {
  uploaded: "secondary",
  queued: "warning",
  processing: "warning",
  retrying: "warning",
  ingested: "success",
  error: "destructive",
  dead_letter: "destructive",
};

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function FilesPage() {
  const { t, dict, locale, tx } = useTranslation();
  const { data, isLoading, isError, refetch } = useFiles();
  const upload = useUploadFile();
  const del = useDeleteFile();
  const ingest = useIngestFile();
  const canIngest = useCan("files:manage");
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [collection, setCollection] = React.useState("default");
  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(10);

  const paginatedFiles = React.useMemo(() => {
    const start = (page - 1) * pageSize;
    return (data || []).slice(start, start + pageSize);
  }, [data, page, pageSize]);

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await upload.mutateAsync(file);
      toast.success(tx(`Đã tải lên ${file.name}`, `Uploaded ${file.name}`));
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        icon={FileText}
        title={dict.pages.files.title}
        description={tx("Tải lên và quản lý tài liệu, PDF, và tệp để tìm kiếm và truy xuất ngữ nghĩa.", "Upload and manage documents, PDFs, and files for semantic search and retrieval.")}
        actions={
          <>
            <Input
              value={collection}
              onChange={(e) => setCollection(e.target.value)}
              className="h-9 w-36 text-xs font-mono"
              placeholder={tx("bộ sưu tập", "collection")}
            />
            <input
              ref={fileRef}
              type="file"
              className="hidden"
              onChange={onPick}
            />
            <Button
              className="gap-2 active-tactile transition-transform"
              loading={upload.isPending}
              onClick={() => fileRef.current?.click()}
            >
              <Upload className="h-4 w-4" /> {tx("Tải lên", "Upload")}
            </Button>
          </>
        }
      />

      <Card glass className="shadow-3d-card overflow-hidden">
        <CardContent className="p-0">
          {isLoading ? <div className="p-6"><LoadingSkeleton variant="table" /></div> : isError ? <div className="p-6"><ErrorState title={tx("Không thể tải tệp", "Unable to load files")} description={tx("Không thể tải dữ liệu tệp.", "File data could not be loaded.")} onRetry={() => void refetch()} /></div> : data && data.length > 0 ? (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{tx("Tên", "Name")}</TableHead>
                    <TableHead>{tx("Loại", "Type")}</TableHead>
                    <TableHead>{tx("Kích thước", "Size")}</TableHead>
                    <TableHead>{tx("Trạng thái", "Status")}</TableHead>
                    <TableHead>{tx("Bộ sưu tập", "Collection")}</TableHead>
                    <TableHead className="text-right">{tx("Hành động", "Actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginatedFiles.map((f: UploadedFile) => (
                    <TableRow key={f.id}>
                      <TableCell className="max-w-[240px] truncate font-medium text-foreground">
                        {f.original_name}
                      </TableCell>
                      <TableCell className="text-muted-foreground font-mono text-xs">
                        {f.content_type || "—"}
                      </TableCell>
                      <TableCell className="text-muted-foreground font-mono text-xs">
                        {formatSize(f.size)}
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusVariant[f.status] || "secondary"} className="uppercase tracking-wider text-[10px]">
                          {statusLabel(f.status, t)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground font-mono text-xs">
                        {f.collection || "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          {canIngest && (
                            <Button
                              size="sm"
                              variant="outline"
                              className="gap-1.5 active-tactile transition-transform"
                              loading={ingest.isPending}
                              disabled={f.status === "queued" || f.status === "processing" || f.status === "retrying"}
                              onClick={async () => {
                                try {
                                  const r = await ingest.mutateAsync({
                                    id: f.id,
                                    body: { collection },
                                  });
                                  toast.success(
                                    r.rag_document_id
                                      ? (tx(`Nạp được chấp nhận ${r.rag_document_id}`, `Ingestion accepted ${r.rag_document_id}`))
                                      : (tx("Nạp đã được gửi", "Ingestion submitted")),
                                  );
                                } catch (err: any) {
                                  toast.error(err.message);
                                }
                              }}
                            >
                              <Loader2 className="h-3.5 w-3.5" /> {tx("Nạp", "Ingest")}
                            </Button>
                          )}
                          <ConfirmDialog
                            trigger={
                              <Button
                                size="sm"
                                variant="ghost"
                                className="text-destructive hover:bg-destructive/10 active-tactile transition-transform"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            }
                            title={tx("Xóa tệp", "Delete File")}
                            description={tx(`Bạn có chắc chắn muốn xóa ${f.original_name}? Hành động này không thể hoàn tác.`, `Are you sure you want to delete ${f.original_name}? This action cannot be undone.`)}
                            confirmLabel={tx("Xóa", "Delete")}
                            destructive
                            onConfirm={async () => {
                              try {
                                await del.mutateAsync(f.id);
                                toast.success(tx(`Đã xóa ${f.original_name}`, `Deleted ${f.original_name}`));
                              } catch (err: any) {
                                toast.error(err.message);
                              }
                            }}
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <DataPagination
                page={page}
                pageSize={pageSize}
                totalItems={data.length}
                onPageChange={setPage}
                onPageSizeChange={setPageSize}
                pageSizeOptions={[5, 10, 20, 50]}
              />
            </>
          ) : (
            <EmptyState
              icon={FileText}
              title={tx("Chưa có tệp nào", "No files yet")}
              description={tx("Tải lên tài liệu để nạp vào RAG.", "Upload a document to ingest it into RAG.")}
              action={
                <Button
                  className="gap-2 active-tactile transition-transform"
                  onClick={() => fileRef.current?.click()}
                >
                  <Upload className="h-4 w-4" /> {tx("Tải lên", "Upload")}
                </Button>
              }
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
