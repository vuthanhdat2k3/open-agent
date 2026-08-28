"use client";

import * as React from "react";
import type { McpServerCreate } from "@/lib/schemas";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { useTranslation } from "@/lib/i18n";

export function McpServerForm({ initial, onSubmit }: { initial?: any; onSubmit: (values: McpServerCreate) => void }) {
    const { locale, tx } = useTranslation();
  const [form, setForm] = React.useState({ name: initial?.name ?? "", transport: initial?.transport ?? "stdio", command: initial?.command ?? "", url: initial?.url ?? "", args: (initial?.args ?? []).join(" ") });

  return (
    <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); onSubmit({ name: form.name, transport: form.transport, command: form.command, url: form.url, args: form.args.split(" ").filter(Boolean), env: initial?.env ?? {}, headers: initial?.headers ?? {} }); }}>
      <div className="space-y-2"><Label htmlFor="mcp-name">{tx("Tên", "Name")}</Label><Input id="mcp-name" name="name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required /></div>
      <div className="space-y-2"><Label htmlFor="mcp-transport">{tx("Giao thức vận chuyển", "Transport")}</Label><Select id="mcp-transport" value={form.transport} onChange={(event) => setForm({ ...form, transport: event.target.value })}><option value="stdio">{tx("stdio", "stdio")}</option><option value="sse">{tx("sse", "sse")}</option><option value="http">{tx("http", "http")}</option></Select></div>
      {form.transport === "stdio" ? <><div className="space-y-2"><Label htmlFor="mcp-command">{tx("Lệnh", "Command")}</Label><Input id="mcp-command" name="command" value={form.command} onChange={(event) => setForm({ ...form, command: event.target.value })} placeholder={tx("npx", "npx")} /></div><div className="space-y-2"><Label htmlFor="mcp-args">{tx("Tham số (cách nhau bởi dấu cách)", "Args (space separated)")}</Label><Input id="mcp-args" name="args" value={form.args} onChange={(event) => setForm({ ...form, args: event.target.value })} placeholder={tx("-y some-package", "-y some-package")} /></div></> : <div className="space-y-2"><Label htmlFor="mcp-url">{tx("URL", "URL")}</Label><Input id="mcp-url" name="url" value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} placeholder={tx("http://localhost:3001/sse", "http://localhost:3001/sse")} /></div>}
      <Button type="submit" className="w-full">{tx("Lưu", "Save")}</Button>
    </form>
  );
}
