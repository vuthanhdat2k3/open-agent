"use client";

import * as React from "react";
import type { McpServerCreate } from "@/lib/schemas";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";

export function McpServerForm({
  initial,
  onSubmit,
}: {
  initial?: any;
  onSubmit: (values: McpServerCreate) => void;
}) {
  const [form, setForm] = React.useState({
    name: initial?.name ?? "",
    transport: initial?.transport ?? "stdio",
    command: initial?.command ?? "",
    url: initial?.url ?? "",
    args: (initial?.args ?? []).join(" "),
  });

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label>Name</Label>
        <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </div>
      <div className="space-y-1.5">
        <Label>Transport</Label>
        <Select value={form.transport} onChange={(e) => setForm({ ...form, transport: e.target.value })}>
          <option value="stdio">stdio</option>
          <option value="sse">sse</option>
          <option value="http">http</option>
        </Select>
      </div>
      {form.transport === "stdio" ? (
        <>
          <div className="space-y-1.5">
            <Label>Command</Label>
            <Input
              value={form.command}
              onChange={(e) => setForm({ ...form, command: e.target.value })}
              placeholder="npx"
            />
          </div>
          <div className="space-y-1.5">
            <Label>Args (space separated)</Label>
            <Input
              value={form.args}
              onChange={(e) => setForm({ ...form, args: e.target.value })}
              placeholder="-y some-package"
            />
          </div>
        </>
      ) : (
        <div className="space-y-1.5">
          <Label>URL</Label>
          <Input
            value={form.url}
            onChange={(e) => setForm({ ...form, url: e.target.value })}
            placeholder="http://localhost:3001/sse"
          />
        </div>
      )}
      <Button
        className="w-full"
        onClick={() =>
          onSubmit({
            name: form.name,
            transport: form.transport,
            command: form.command,
            url: form.url,
            args: form.args.split(" ").filter(Boolean),
            env: initial?.env ?? {},
            headers: initial?.headers ?? {},
          })
        }
      >
        Save
      </Button>
    </div>
  );
}
