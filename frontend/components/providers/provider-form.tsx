"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { providerCreate, type ProviderCreate } from "@/lib/schemas";
import { Input, Label } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

function deriveEnvVar(name: string): string {
  return name.trim().replace(/\s+/g, "-") + "-API-KEY";
}

export function ProviderForm({
  initial,
  onSubmit,
}: {
  initial?: Partial<ProviderCreate>;
  onSubmit: (values: ProviderCreate) => void;
}) {
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<ProviderCreate>({
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

  const name = watch("name");
  const envVar = watch("env_var");
  // Auto-fill env_var from the name until the user edits it manually.
  React.useEffect(() => {
    if (!envVar) {
      setValue("env_var", deriveEnvVar(name || ""), { shouldValidate: false });
    }
  }, [name, envVar, setValue]);

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-1.5">
        <Label>Key (slug)</Label>
        <Input {...register("key")} placeholder="openai" className="font-mono text-xs" />
        <p className="text-xs text-muted-foreground">Unique id, e.g. openai</p>
        {errors.key && <p className="text-xs text-destructive">{errors.key.message}</p>}
      </div>
      <div className="space-y-1.5">
        <Label>Name</Label>
        <Input {...register("name")} placeholder="OpenAI" />
        {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
      </div>
      <div className="space-y-1.5">
        <Label>Base URL</Label>
        <Input
          {...register("base_url")}
          className="font-mono text-xs"
          placeholder="https://api.openai.com/v1"
        />
        {errors.base_url && <p className="text-xs text-destructive">{errors.base_url.message}</p>}
      </div>
      <div className="space-y-1.5">
        <Label>API Key</Label>
        <Input
          type="password"
          autoComplete="off"
          {...register("api_key")}
          className="font-mono text-xs"
          placeholder="sk-..."
        />
        <p className="text-xs text-muted-foreground">
          Stored directly in the database. Leave empty to fall back to the env var below.
        </p>
        {errors.api_key && <p className="text-xs text-destructive">{errors.api_key.message}</p>}
      </div>
      <div className="space-y-1.5">
        <Label>Env Var (auto)</Label>
        <Input
          {...register("env_var")}
          className="font-mono text-xs"
          placeholder="OpenAI-API-KEY"
        />
        <p className="text-xs text-muted-foreground">
          Fallback when API Key is empty (e.g. set in .env).
        </p>
      </div>
      <label className="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
        <input
          type="checkbox"
          {...register("is_default")}
          className="h-4 w-4 rounded border-border bg-transparent accent-primary"
        />
        Default provider
      </label>
      <Button type="submit" className="w-full">
        Save
      </Button>
    </form>
  );
}
