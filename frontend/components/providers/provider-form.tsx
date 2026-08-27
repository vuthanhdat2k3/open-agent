import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { providerCreate, type ProviderCreate } from "@/lib/schemas";
import { Form } from "@/components/ui/form";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";

function deriveEnvVar(name: string): string {
  return name.trim().replace(/\s+/g, "-") + "-API-KEY";
}

export function ProviderForm({ initial, onSubmit }: { initial?: Partial<ProviderCreate>; onSubmit: (values: ProviderCreate) => void | Promise<void> }) {
    const { locale, tx } = useTranslation();
  const form = useForm<ProviderCreate>({
    resolver: zodResolver(providerCreate),
    defaultValues: {
      key: initial?.key ?? "",
      name: initial?.name ?? "",
      base_url: initial?.base_url ?? "",
      api_key: initial?.api_key ?? "",
      env_var: initial?.env_var ?? "",
      is_default: initial?.is_default ?? false,
    },
  });
  const { register, handleSubmit, watch, setValue, formState: { errors, isSubmitting } } = form;
  const name = watch("name");
  const envVar = watch("env_var");

  React.useEffect(() => {
    if (!envVar) setValue("env_var", deriveEnvVar(name || ""), { shouldValidate: false });
  }, [name, envVar, setValue]);

  return (
    <Form {...form}>
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div className="space-y-2"><Label htmlFor="provider-key">{tx("Key (slug)", "Key (slug)")}</Label><Input id="provider-key" {...register("key")} placeholder={tx("openai", "openai")} className="font-mono text-xs" /><p className="text-sm text-muted-foreground">{tx("Unique id, e.g. openai", "Unique id, e.g. openai")}</p>{errors.key && <p role="alert" className="text-sm text-destructive">{errors.key.message}</p>}</div>
        <div className="space-y-2"><Label htmlFor="provider-name">{tx("Tên", "Name")}</Label><Input id="provider-name" {...register("name")} placeholder={tx("OpenAI", "OpenAI")} />{errors.name && <p role="alert" className="text-sm text-destructive">{errors.name.message}</p>}</div>
        <div className="space-y-2"><Label htmlFor="provider-base-url">{tx("Base URL", "Base URL")}</Label><Input id="provider-base-url" {...register("base_url")} className="font-mono text-xs" placeholder={tx("https://api.openai.com/v1", "https://api.openai.com/v1")} />{errors.base_url && <p role="alert" className="text-sm text-destructive">{errors.base_url.message}</p>}</div>
        <div className="space-y-2"><Label htmlFor="provider-api-key">{tx("API Key", "API Key")}</Label><Input id="provider-api-key" type="password" autoComplete="off" {...register("api_key")} className="font-mono text-xs" placeholder={tx("sk-…", "sk-…")} /><p className="text-sm leading-relaxed text-muted-foreground">{tx("Stored encrypted at rest. Leave empty to keep the existing key or fall back to the env var below.", "Stored encrypted at rest. Leave empty to keep the existing key or fall back to the env var below.")}</p>{errors.api_key && <p role="alert" className="text-sm text-destructive">{errors.api_key.message}</p>}</div>
        <div className="space-y-2"><Label htmlFor="provider-env-var">{tx("Env Var (auto)", "Env Var (auto)")}</Label><Input id="provider-env-var" {...register("env_var")} className="font-mono text-xs" placeholder={tx("OpenAI-API-KEY", "OpenAI-API-KEY")} /><p className="text-sm leading-relaxed text-muted-foreground">{tx("Fallback when API Key is empty (e.g. set in .env).", "Fallback when API Key is empty (e.g. set in .env).")}</p></div>
        <label htmlFor="provider-default" className="flex min-h-11 cursor-pointer items-center gap-3 text-sm text-muted-foreground"><input id="provider-default" type="checkbox" {...register("is_default")} className="h-4 w-4 rounded border-border accent-primary" />{tx("Default provider", "Default provider")}</label>
        <Button type="submit" className="w-full" loading={isSubmitting}>{tx("Lưu", "Save")}</Button>
      </form>
    </Form>
  );
}
