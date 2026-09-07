"use client";

import * as React from "react";
import { Eye, EyeOff, RotateCcw, Save, ShieldAlert, SlidersHorizontal } from "lucide-react";
import { toast } from "sonner";
import { useCan, usePlatformConfig, useResetPlatformConfig, useSetPlatformConfig } from "@/hooks";
import { PageHeader } from "@/components/page-header";
import { useTranslation } from "@/lib/i18n";
import { ErrorState, LoadingSkeleton } from "@/components/shared";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { PlatformConfigEntry } from "@/types";

export default function PlatformConfigPage() {
  const { t, tx } = useTranslation();
  const canAccess = useCan("platform:config:read");
  if (!canAccess) {
    return (
      <ErrorState
        title={t("forceChange.noAccess", "No access")}
        description={tx(
          "Chỉ platform admin mới có thể xem trang này.",
          "Only platform administrators can view this page."
        )}
      />
    );
  }
  return <PlatformConfigContent />;
}

function PlatformConfigContent() {
  const { tx } = useTranslation();
  const canManage = useCan("platform:config:manage");
  const query = usePlatformConfig();
  const setConfig = useSetPlatformConfig();
  const resetConfig = useResetPlatformConfig();

  if (query.isLoading) return <LoadingSkeleton />;
  if (query.isError || !query.data) {
    return (
      <ErrorState
        title={tx("Không thể tải cấu hình nền tảng", "Unable to load platform config")}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const groups = new Map<string, PlatformConfigEntry[]>();
  for (const entry of query.data) {
    if (!groups.has(entry.group)) groups.set(entry.group, []);
    groups.get(entry.group)!.push(entry);
  }

  const save = async (key: string, value: unknown) => {
    try {
      await setConfig.mutateAsync({ key, value });
      toast.success(tx("Đã lưu", "Saved"));
    } catch (error: any) {
      toast.error(error.message || tx("Không thể lưu cấu hình", "Failed to save config"));
    }
  };

  const reset = async (key: string) => {
    try {
      await resetConfig.mutateAsync(key);
      toast.success(tx("Đã khôi phục mặc định", "Reset to default"));
    } catch (error: any) {
      toast.error(error.message || tx("Không thể khôi phục", "Failed to reset"));
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        icon={SlidersHorizontal}
        title={tx("Cấu hình nền tảng", "Platform Config")}
        description={tx(
          "Chỉnh sửa các biến cấu hình an toàn (API key tích hợp, quan sát, sandbox, ...) áp dụng cho toàn bộ nền tảng, không cần khởi động lại.",
          "Edit safe, instance-wide config values (integration API keys, observability, sandbox, ...) without a restart."
        )}
      />

      {!canManage && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-600">
          <ShieldAlert className="h-4 w-4 shrink-0" />
          {tx("Bạn chỉ có quyền xem, không thể chỉnh sửa các giá trị này.", "You have read-only access; you cannot edit these values.")}
        </div>
      )}

      {Array.from(groups.entries()).map(([group, entries]) => (
        <Card key={group} className="shadow-card border-border/80">
          <CardHeader>
            <CardTitle className="text-base">{group}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-6 md:grid-cols-2">
            {entries.map((entry) => (
              <ConfigField
                key={entry.key}
                entry={entry}
                readOnly={!canManage}
                saving={setConfig.isPending}
                onSave={(value) => save(entry.key, value)}
                onReset={() => reset(entry.key)}
              />
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function ConfigField({
  entry,
  readOnly,
  saving,
  onSave,
  onReset,
}: {
  entry: PlatformConfigEntry;
  readOnly: boolean;
  saving: boolean;
  onSave: (value: unknown) => void;
  onReset: () => void;
}) {
  const { tx } = useTranslation();
  const [draft, setDraft] = React.useState<string>(
    entry.type === "secret" ? "" : String(entry.value ?? "")
  );
  const [revealSecret, setRevealSecret] = React.useState(false);
  const [editingSecret, setEditingSecret] = React.useState(false);
  const dirty =
    entry.type === "secret"
      ? editingSecret && draft !== ""
      : draft !== String(entry.value ?? "");

  const commit = () => {
    if (entry.type === "boolean") {
      onSave(draft === "true");
    } else {
      onSave(draft);
    }
    if (entry.type === "secret") setEditingSecret(false);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {entry.label}
        </Label>
        {entry.is_overridden && (
          <Badge variant="outline" className="text-[10px] font-mono">
            {tx("Đã tuỳ chỉnh", "Overridden")}
          </Badge>
        )}
      </div>

      {entry.type === "secret" ? (
        editingSecret ? (
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Input
                type={revealSecret ? "text" : "password"}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={tx("Nhập giá trị mới", "Enter new value")}
                disabled={readOnly}
                className="pr-9 text-xs font-mono"
              />
              <button
                type="button"
                onClick={() => setRevealSecret((v) => !v)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                tabIndex={-1}
              >
                {revealSecret ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              </button>
            </div>
            <Button size="sm" variant="ghost" onClick={() => setEditingSecret(false)}>
              {tx("Huỷ", "Cancel")}
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="flex h-10 flex-1 items-center rounded-lg border border-border bg-muted/30 px-3.5 text-xs font-mono text-muted-foreground">
              {entry.is_set ? entry.masked_value : tx("Chưa thiết lập", "Not set")}
            </span>
            {!readOnly && (
              <Button size="sm" variant="outline" onClick={() => setEditingSecret(true)}>
                {tx("Đổi", "Change")}
              </Button>
            )}
            {!readOnly && entry.is_overridden && (
              <Button size="sm" variant="ghost" onClick={onReset} title={tx("Khôi phục mặc định", "Reset to default")}>
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        )
      ) : entry.type === "boolean" ? (
        <Select
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={readOnly}
          className="text-xs font-mono"
        >
          <option value="true">{tx("Bật", "Enabled")}</option>
          <option value="false">{tx("Tắt", "Disabled")}</option>
        </Select>
      ) : entry.type === "options" && entry.options ? (
        <Select
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={readOnly}
          className="text-xs font-mono"
        >
          {entry.options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </Select>
      ) : (
        <Input
          type={entry.type === "number" ? "number" : "text"}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          disabled={readOnly}
          className="text-xs font-mono"
        />
      )}

      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] text-muted-foreground">{entry.description}</p>
        {!readOnly && dirty && (
          <Button size="sm" className="h-7 shrink-0 gap-1 px-2 text-[11px]" onClick={commit} loading={saving}>
            <Save className="h-3 w-3" /> {tx("Lưu", "Save")}
          </Button>
        )}
        {!readOnly && !dirty && entry.is_overridden && entry.type !== "secret" && (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 shrink-0 gap-1 px-2 text-[11px] text-muted-foreground"
            onClick={onReset}
          >
            <RotateCcw className="h-3 w-3" /> {tx("Mặc định", "Reset")}
          </Button>
        )}
      </div>
    </div>
  );
}
