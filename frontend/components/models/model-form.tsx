"use client";

import * as React from "react";
import type { ModelCreate } from "@/lib/schemas";
import type { Provider } from "@/types";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { useTranslation } from "@/lib/i18n";

export function ModelForm({ initial, providers, onSubmit }: { initial?: Partial<ModelCreate>; providers: Provider[]; onSubmit: (values: ModelCreate) => void }) {
    const { locale, tx } = useTranslation();
  const [form, setForm] = React.useState<ModelCreate>({ provider_id: initial?.provider_id ?? "", name: initial?.name ?? "", display_name: initial?.display_name ?? "", tier: (initial?.tier as ModelCreate["tier"]) ?? "balanced", context_window: initial?.context_window ?? 8192, input_cost_per_1k: initial?.input_cost_per_1k ?? 0, output_cost_per_1k: initial?.output_cost_per_1k ?? 0, enabled: initial?.enabled ?? initial?.active ?? true });

  React.useEffect(() => {
    if (!form.provider_id && providers[0]) setForm((current) => ({ ...current, provider_id: providers[0].id }));
    // The default provider is intentionally selected only when the form is empty.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providers]);

  return (
    <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); onSubmit(form); }}>
      <div className="space-y-2"><Label htmlFor="model-provider">{tx("Provider", "Provider")}</Label><Select id="model-provider" value={form.provider_id} onChange={(event) => setForm({ ...form, provider_id: event.target.value })}>{providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name}</option>)}</Select></div>
      <div className="space-y-2"><Label htmlFor="model-name">{tx("Name (API id)", "Name (API id)")}</Label><Input id="model-name" name="name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required /></div>
      <div className="space-y-2"><Label htmlFor="model-display-name">{tx("Display name", "Display name")}</Label><Input id="model-display-name" name="display_name" value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} required /></div>
      <div className="space-y-2"><Label htmlFor="model-tier">{tx("Tier", "Tier")}</Label><Select id="model-tier" value={form.tier} onChange={(event) => setForm({ ...form, tier: event.target.value as ModelCreate["tier"] })}><option value="frontier">{tx("frontier", "frontier")}</option><option value="balanced">{tx("balanced", "balanced")}</option><option value="economy">{tx("economy", "economy")}</option></Select></div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2"><div className="space-y-2"><Label htmlFor="model-context">{tx("Context window", "Context window")}</Label><Input id="model-context" name="context_window" type="number" min="1" value={form.context_window} onChange={(event) => setForm({ ...form, context_window: +event.target.value })} /></div><div className="space-y-2"><Label htmlFor="model-enabled">{tx("Enabled", "Enabled")}</Label><Select id="model-enabled" value={String(form.enabled)} onChange={(event) => setForm({ ...form, enabled: event.target.value === "true" })}><option value="true">{tx("yes", "yes")}</option><option value="false">{tx("no", "no")}</option></Select></div></div>
      <Button type="submit" className="w-full">{tx("Lưu", "Save")}</Button>
    </form>
  );
}
