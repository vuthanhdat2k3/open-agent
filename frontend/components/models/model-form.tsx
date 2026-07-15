"use client";

import * as React from "react";
import type { ModelCreate } from "@/lib/schemas";
import type { Provider } from "@/types";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";

export function ModelForm({
  initial,
  providers,
  onSubmit,
}: {
  initial?: Partial<ModelCreate>;
  providers: Provider[];
  onSubmit: (values: ModelCreate) => void;
}) {
  const [form, setForm] = React.useState<ModelCreate>({
    provider_id: initial?.provider_id ?? "",
    name: initial?.name ?? "",
    display_name: initial?.display_name ?? "",
    tier: (initial?.tier as ModelCreate["tier"]) ?? "balanced",
    context_window: initial?.context_window ?? 8192,
    input_cost_per_1k: initial?.input_cost_per_1k ?? 0,
    output_cost_per_1k: initial?.output_cost_per_1k ?? 0,
    active: initial?.active ?? true,
  });

  // Default to the first provider when none is chosen yet.
  React.useEffect(() => {
    if (!form.provider_id && providers[0]) {
      setForm((f) => ({ ...f, provider_id: providers[0].id }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providers]);

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label>Provider</Label>
        <Select value={form.provider_id} onChange={(e) => setForm({ ...form, provider_id: e.target.value })}>
          {providers.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label>Name (API id)</Label>
        <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      </div>
      <div className="space-y-1.5">
        <Label>Display name</Label>
        <Input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
      </div>
      <div className="space-y-1.5">
        <Label>Tier</Label>
        <Select value={form.tier} onChange={(e) => setForm({ ...form, tier: e.target.value as ModelCreate["tier"] })}>
          <option value="frontier">frontier</option>
          <option value="balanced">balanced</option>
          <option value="economy">economy</option>
        </Select>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1.5">
          <Label>Context window</Label>
          <Input
            type="number"
            value={form.context_window}
            onChange={(e) => setForm({ ...form, context_window: +e.target.value })}
          />
        </div>
        <div className="space-y-1.5">
          <Label>Active</Label>
          <Select value={String(form.active)} onChange={(e) => setForm({ ...form, active: e.target.value === "true" })}>
            <option value="true">yes</option>
            <option value="false">no</option>
          </Select>
        </div>
      </div>
      <Button className="w-full" onClick={() => onSubmit(form)}>
        Save
      </Button>
    </div>
  );
}
