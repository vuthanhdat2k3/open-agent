"use client";

import * as React from "react";
import { toast } from "sonner";
import { Upload, Trash2, FileText, Loader2 } from "lucide-react";
import {
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
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
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
  ingesting: "warning",
  ingested: "success",
  error: "destructive",
};

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function FilesPage() {
  const { data, isLoading } = useFiles();
  const upload = useUploadFile();
  const del = useDeleteFile();
  const ingest = useIngestFile();
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [collection, setCollection] = React.useState("default");

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await upload.mutateAsync(file);
      toast.success(`Uploaded ${file.name}`);
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
        title="Files"
        description="Upload documents and ingest them into the RAG service"
        actions={
          <>
            <Input
              value={collection}
              onChange={(e) => setCollection(e.target.value)}
              className="h-9 w-36"
              placeholder="collection"
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
              <Upload className="h-4 w-4" /> Upload
            </Button>
          </>
        }
      />

      <Card glass className="card-lift">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-2 p-6">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : data && data.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Collection</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((f: UploadedFile) => (
                  <TableRow key={f.id}>
                    <TableCell className="max-w-[240px] truncate font-medium">
                      {f.original_name}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {f.content_type || "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatSize(f.size)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusVariant[f.status] || "secondary"}>
                        {f.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {f.collection || "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="gap-1.5 active-tactile transition-transform"
                          loading={ingest.isPending}
                          disabled={f.status === "ingesting"}
                          onClick={async () => {
                            try {
                              const r = await ingest.mutateAsync({
                                id: f.id,
                                body: { collection },
                              });
                              toast.success(
                                r.document_id
                                  ? `Ingested → ${r.document_id}`
                                  : "Ingested",
                              );
                            } catch (err: any) {
                              toast.error(err.message);
                            }
                          }}
                        >
                          {f.status === "ingesting" ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : null}
                          Ingest
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8 text-muted-foreground hover:text-destructive"
                          onClick={() => del.mutate(f.id)}
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
              icon={FileText}
              title="No files yet"
              description="Upload a document to ingest it into RAG."
              action={
                <Button
                  className="gap-2 active-tactile transition-transform"
                  onClick={() => fileRef.current?.click()}
                >
                  <Upload className="h-4 w-4" /> Upload
                </Button>
              }
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
