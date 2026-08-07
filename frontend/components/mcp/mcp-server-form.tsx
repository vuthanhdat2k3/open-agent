"use client";

import * as React from "react";
import type { McpServerCreate } from "@/lib/schemas";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";

export function McpServerForm({ initial, onSubmit }: { initial?: any; onSubmit: (values: McpServerCreate) => void }) {
  const [form, setForm] = React.useState({ name: initial?.name ?? "", transport: initial?.transport ?? "stdio", command: initial?.command ?? "", url: initial?.url ?? "", args: (initial?.args ?? []).join(" ") });

  return (
    <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); onSubmit({ name: form.name, transport: form.transport, command: form.command, url: form.url, args: form.args.split(" ").filter(Boolean), env: initial?.env ?? {}, headers: initial?.headers ?? {} }); }}>
      <div className="space-y-2"><Label htmlFor="mcp-name">Name</Label><Input id="mcp-name" name="name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required /></div>
      <div className="space-y-2"><Label htmlFor="mcp-transport">Transport</Label><Select id="mcp-transport" value={form.transport} onChange={(event) => setForm({ ...form, transport: event.target.value })}><option value="stdio">stdio</option><option value="sse">sse</option><option value="http">http</option></Select></div>
      {form.transport === "stdio" ? <><div className="space-y-2"><Label htmlFor="mcp-command">Command</Label><Input id="mcp-command" name="command" value={form.command} onChange={(event) => setForm({ ...form, command: event.target.value })} placeholder="npx" /></div><div className="space-y-2"><Label htmlFor="mcp-args">Args (space separated)</Label><Input id="mcp-args" name="args" value={form.args} onChange={(event) => setForm({ ...form, args: event.target.value })} placeholder="-y some-package" /></div></> : <div className="space-y-2"><Label htmlFor="mcp-url">URL</Label><Input id="mcp-url" name="url" value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} placeholder="http://localhost:3001/sse" /></div>}
      <Button type="submit" className="w-full">Save</Button>
    </form>
  );
}
