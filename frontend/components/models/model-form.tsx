"use client";

import * as React from "react";
import type { ModelCreate } from "@/lib/schemas";
import type { Provider } from "@/types";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";

export function ModelForm({ initial, providers, onSubmit }: { initial?: Partial<ModelCreate>; providers: Provider[]; onSubmit: (values: ModelCreate) => void }) {
  const [form, setForm] = React.useState<ModelCreate>({ provider_id: initial?.provider_id ?? "", name: initial?.name ?? "", display_name: initial?.display_name ?? "", tier: (initial?.tier as ModelCreate["tier"]) ?? "balanced", context_window: initial?.context_window ?? 8192, input_cost_per_1k: initial?.input_cost_per_1k ?? 0, output_cost_per_1k: initial?.output_cost_per_1k ?? 0, active: initial?.active ?? true });

  React.useEffect(() => {
    if (!form.provider_id && providers[0]) setForm((current) => ({ ...current, provider_id: providers[0].id }));
    // The default provider is intentionally selected only when the form is empty.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providers]);

  return (
    <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); onSubmit(form); }}>
      <div className="space-y-2"><Label htmlFor="model-provider">Provider</Label><Select id="model-provider" value={form.provider_id} onChange={(event) => setForm({ ...form, provider_id: event.target.value })}>{providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}</Select></div>
      <div className="space-y-2"><Label htmlFor="model-name">Name (API id)</Label><Input id="model-name" name="name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required /></div>
      <div className="space-y-2"><Label htmlFor="model-display-name">Display name</Label><Input id="model-display-name" name="display_name" value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} required /></div>
      <div className="space-y-2"><Label htmlFor="model-tier">Tier</Label><Select id="model-tier" value={form.tier} onChange={(event) => setForm({ ...form, tier: event.target.value as ModelCreate["tier"] })}><option value="frontier">frontier</option><option value="balanced">balanced</option><option value="economy">economy</option></Select></div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2"><div className="space-y-2"><Label htmlFor="model-context">Context window</Label><Input id="model-context" name="context_window" type="number" min="1" value={form.context_window} onChange={(event) => setForm({ ...form, context_window: +event.target.value })} /></div><div className="space-y-2"><Label htmlFor="model-active">Active</Label><Select id="model-active" value={String(form.active)} onChange={(event) => setForm({ ...form, active: event.target.value === "true" })}><option value="true">yes</option><option value="false">no</option></Select></div></div>
      <Button type="submit" className="w-full">Save</Button>
    </form>
  );
}
