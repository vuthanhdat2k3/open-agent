/**
 * NodeConfigForm — Dynamic field renderer for workflow graph nodes.
 * Accurately merges saved DB parameters, definition defaults, and resolves conditional field visibility.
 */
"use client";

import * as React from "react";
import { useNodeDefinitions, useNodeOptions, useToolOptions } from "@/hooks";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Plus, Trash2 } from "lucide-react";
import { useTranslation } from "@/lib/i18n";
import type { GraphNode, NodeDefinition, NodeField } from "@/types";

interface NodeConfigFormProps {
  node: GraphNode;
  onUpdate: (patch: Partial<GraphNode>) => void;
}

/** True when a field's display rules match the current parameters or fallback defaults. */
function isFieldVisible(
  field: NodeField,
  parameters: Record<string, any>,
  definition?: NodeDefinition
) {
  const display = field.display;
  if (!display) return true;
  if (display.show) {
    for (const [key, values] of Object.entries(display.show)) {
      const fieldDef = definition?.fields.find((f) => f.name === key);
      const val = parameters[key] ?? fieldDef?.default ?? definition?.default_parameters?.[key];
      if (!values.includes(val)) return false;
    }
  }
  if (display.hide) {
    for (const [key, values] of Object.entries(display.hide)) {
      const fieldDef = definition?.fields.find((f) => f.name === key);
      const val = parameters[key] ?? fieldDef?.default ?? definition?.default_parameters?.[key];
      if (values.includes(val)) return false;
    }
  }
  return true;
}

/** Keep legacy scheduler values (for example, "7:30") valid for a time input. */
function normalizeTimeValue(value: unknown, fallback: unknown): string {
  const raw = String(value ?? fallback ?? "");
  const match = /^(\d{1,2}):(\d{2})$/.exec(raw);
  if (!match) return raw;
  return `${match[1].padStart(2, "0")}:${match[2]}`;
}

function FieldInput({
  field,
  value,
  options,
  onValue,
}: {
  field: NodeField;
  value: any;
  options?: Array<{ name: string; value: string; description?: string }>;
  onValue: (value: any) => void;
}) {
  const { t } = useTranslation();
  const fieldOptions = field.options ?? options ?? [];
  switch (field.type) {
    case "textarea":
      return (
        <Textarea
          className="text-xs min-h-[80px]"
          value={value ?? field.default ?? ""}
          onChange={(e) => onValue(e.target.value)}
          placeholder={field.placeholder}
          rows={field.type_options?.rows ?? 4}
        />
      );
    case "number":
      return (
        <Input
          className="text-xs"
          type="number"
          value={value ?? field.default ?? ""}
          onChange={(e) => onValue(e.target.value === "" ? undefined : Number(e.target.value))}
          placeholder={field.placeholder}
          min={field.type_options?.minValue}
          max={field.type_options?.maxValue}
          step={field.type_options?.step ?? (field.type_options?.numberPrecision ? 10 ** -field.type_options.numberPrecision : 1)}
        />
      );
    case "time":
      return (
        <Input
          className="text-xs"
          type="time"
          value={normalizeTimeValue(value, field.default)}
          onChange={(e) => onValue(e.target.value)}
          step={field.type_options?.step ?? 60}
          aria-label={field.label}
        />
      );
    case "date":
      return (
        <Input
          className="text-xs"
          type="date"
          value={value ?? field.default ?? ""}
          onChange={(e) => onValue(e.target.value)}
          aria-label={field.label}
        />
      );
    case "boolean":
      return (
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={Boolean(value ?? field.default)}
            onChange={(e) => onValue(e.target.checked)}
            className="h-4 w-4 rounded border-border"
          />
          <span className="text-xs text-muted-foreground">{field.label}</span>
        </label>
      );
    case "options":
      return (
        <Select
          className="text-xs w-full"
          value={value ?? field.default ?? ""}
          onChange={(e) => onValue(e.target.value)}
        >
          {fieldOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.name}
            </option>
          ))}
        </Select>
      );
    case "multiOptions": {
      const current: string[] = Array.isArray(value) ? value : field.default ?? [];
      return (
        <div className="flex flex-wrap gap-1.5">
          {fieldOptions.map((o) => {
            const active = current.includes(o.value);
            return (
              <button
                key={o.value}
                type="button"
                onClick={() =>
                  onValue(active ? current.filter((v) => v !== o.value) : [...current, o.value])
                }
                className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                  active
                    ? "border-primary/50 bg-primary/15 text-primary"
                    : "border-border/70 bg-muted/40 text-muted-foreground hover:text-foreground"
                }`}
              >
                {o.name}
              </button>
            );
          })}
        </div>
      );
    }
    case "json":
      return (
        <Textarea
          className="text-xs font-mono min-h-[100px]"
          value={JSON.stringify(value ?? field.default ?? {}, null, 2)}
          onChange={(e) => {
            try {
              onValue(JSON.parse(e.target.value));
            } catch {
              // keep last valid value; typing in progress
            }
          }}
          placeholder={field.placeholder || "{}"}
        />
      );
    case "fixedCollection": {
      const rows: any[] = Array.isArray(value) ? value : [];
      return (
        <div className="space-y-2">
          {rows.map((row, idx) => (
            <div key={idx} className="rounded-lg border border-border/60 bg-muted/20 p-2 space-y-2">
              {field.type_options?.subfields ? (
                (field.type_options.subfields as NodeField[]).map((sub) => (
                  <SubField
                    key={sub.name}
                    field={sub}
                    value={row?.[sub.name]}
                    onValue={(v) => {
                      const next = rows.map((r, i) => (i === idx ? { ...r, [sub.name]: v } : r));
                      onValue(next);
                    }}
                  />
                ))
              ) : (
                <>
                  {fieldOptions.map((o) => (
                    <SubField
                      key={o.value}
                      field={{ name: o.value, label: o.name, type: "string", default: "" } as NodeField}
                      value={row?.[o.value]}
                      onValue={(v) => {
                        const next = rows.map((r, i) => (i === idx ? { ...r, [o.value]: v } : r));
                        onValue(next);
                      }}
                    />
                  ))}
                </>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full gap-1 text-destructive border-destructive/40"
                onClick={() => onValue(rows.filter((_, i) => i !== idx))}
              >
                <Trash2 className="h-3 w-3" /> {t("pages.workflows.removeRow", "Remove")}
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="w-full gap-1"
            onClick={() => onValue([...rows, {}])}
          >
            <Plus className="h-3 w-3" /> {t("pages.workflows.addRow", "Add row")}
          </Button>
        </div>
      );
    }
    case "collection": {
      const current: Record<string, any> = (value ?? field.default ?? {}) as Record<string, any>;
      const subfields: NodeField[] = (field.type_options?.subfields as NodeField[]) ?? [];
      return (
        <div className="space-y-2">
          {subfields.map((sub) => (
            <SubField
              key={sub.name}
              field={sub}
              value={current[sub.name]}
              onValue={(v) => onValue({ ...current, [sub.name]: v })}
            />
          ))}
        </div>
      );
    }
    default:
      return (
        <Input
          className="text-xs"
          value={value ?? field.default ?? ""}
          onChange={(e) => onValue(e.target.value)}
          placeholder={field.placeholder}
        />
      );
  }
}

function SubField({
  field,
  value,
  onValue,
}: {
  field: NodeField;
  value: any;
  onValue: (v: any) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-1">
      <Label className="text-[11px] font-medium text-muted-foreground">
        {t(`pages.workflows.nodeField.${field.name}`, field.label)}
      </Label>
      <FieldInput field={field} value={value} onValue={onValue} />
    </div>
  );
}

export function NodeConfigForm({ node, onUpdate }: NodeConfigFormProps) {
  const { t } = useTranslation();
  const [showAdvanced, setShowAdvanced] = React.useState(false);
  const definitions = useNodeDefinitions();
  const toolOptions = useToolOptions();
  const [modelOptions, setModelOptions] = React.useState<Array<{ name: string; value: string }>>([]);
  const [agentOptions, setAgentOptions] = React.useState<Array<{ name: string; value: string }>>([]);
  const [workflowOptions, setWorkflowOptions] = React.useState<Array<{ name: string; value: string }>>([]);
  const [connectionOptions, setConnectionOptions] = React.useState<Array<{ name: string; value: string }>>([]);
  const [userOptions, setUserOptions] = React.useState<Array<{ name: string; value: string }>>([]);

  const models = useNodeOptions("models");
  const agents = useNodeOptions("agents");
  const workflows = useNodeOptions("workflows");
  const connections = useNodeOptions("connections");
  const users = useNodeOptions("users");

  React.useEffect(() => {
    setModelOptions(models.data ?? []);
  }, [models.data]);
  React.useEffect(() => {
    setAgentOptions(agents.data ?? []);
  }, [agents.data]);
  React.useEffect(() => {
    setWorkflowOptions(workflows.data ?? []);
  }, [workflows.data]);
  React.useEffect(() => {
    setConnectionOptions(connections.data ?? []);
  }, [connections.data]);
  React.useEffect(() => {
    setUserOptions(users.data ?? []);
  }, [users.data]);

  React.useEffect(() => {
    setShowAdvanced(false);
  }, [node.id]);

  const definition: NodeDefinition | undefined = definitions.data?.[node.kind];
  if (!definition) return null;

  // Accurately extract all saved parameters from node (parameters, config, or top-level props)
  // and overlay onto definition defaults.
  const selectedAgentId = node.agent_id || (node.parameters as any)?.agent_id || (node.config as any)?.agent_id;
  const selectedAgent = selectedAgentId ? (agents.data as any[])?.find(a => a.value === selectedAgentId) : null;
  const agentTemplateDefaults = selectedAgent ? {
    system_prompt: selectedAgent.system_prompt,
    model_id: selectedAgent.model_id,
    tools: selectedAgent.tools,
  } : {};

  const rootParams: Record<string, any> = {};
  if (selectedAgentId) rootParams.agent_id = selectedAgentId;
  if ((node as any).tool) rootParams.tool = (node as any).tool;
  if ((node as any).system_prompt) rootParams.system_prompt = (node as any).system_prompt;
  if ((node as any).model_id) rootParams.model_id = (node as any).model_id;
  if ((node as any).tools) rootParams.tools = (node as any).tools;

  const parameters: Record<string, any> = {
    ...(definition.default_parameters ?? {}),
    ...agentTemplateDefaults,
    ...rootParams,
    ...(node.config ?? {}),
    ...(node.parameters ?? {}),
  };

  const setParam = (name: string, value: any) => {
    const next = { ...parameters, [name]: value };
    const patch: Partial<GraphNode> = {
      parameters: next,
      config: next,
    };
    if (name === "agent_id") {
      patch.agent_id = value;
      const found = (agents.data as any[])?.find((a) => a.value === value);
      if (found) {
        if (found.system_prompt && !next.system_prompt) {
          next.system_prompt = found.system_prompt;
        }
        if (found.model_id && !next.model_id) {
          next.model_id = found.model_id;
        }
        if (found.tools && (!next.tools || next.tools.length === 0)) {
          next.tools = found.tools;
        }
      }
    }
    if (name === "merge_mode") patch.merge_mode = value;
    onUpdate(patch);
  };

  const loadOptions = (field: NodeField): Array<{ name: string; value: string; description?: string }> => {
    switch (field.load_options_from) {
      case "tools":
        return toolOptions.data ?? [];
      case "models":
        return modelOptions;
      case "agents":
        return agentOptions;
      case "workflows":
        return workflowOptions.filter((o) => o.value !== node.id);
      case "connections":
        return connectionOptions;
      case "users":
        return userOptions;
      default:
        return field.options ?? [];
    }
  };

  return (
    <div className="space-y-4">
      {definition.fields
        .filter((f) => !f.internal && !f.advanced && isFieldVisible(f, parameters, definition))
        .map((field) => (
          <div key={field.name} className="space-y-1.5">
            <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/80">
              {t(`pages.workflows.nodeField.${field.name}`, field.label)}
              {field.required && <span className="text-destructive"> *</span>}
            </Label>
            <FieldInput
              field={field}
              value={parameters[field.name]}
              options={loadOptions(field)}
              onValue={(v) => setParam(field.name, v)}
            />
            {field.description && (
              <p className="text-[11px] text-muted-foreground/80 leading-relaxed">{field.description}</p>
            )}
          </div>
        ))}
      {definition.fields.some((f) => f.advanced) && (
        <>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="w-full justify-between text-xs text-muted-foreground"
            onClick={() => setShowAdvanced((value) => !value)}
          >
            {showAdvanced
              ? t("pages.workflows.hideAdvancedSettings", "Hide advanced settings")
              : t("pages.workflows.showAdvancedSettings", "Show advanced settings")}
            <span aria-hidden="true">{showAdvanced ? "−" : "+"}</span>
          </Button>
          {showAdvanced && definition.fields
            .filter((f) => !f.internal && f.advanced && isFieldVisible(f, parameters, definition))
            .map((field) => (
              <div key={field.name} className="space-y-1.5">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {t(`pages.workflows.nodeField.${field.name}`, field.label)}
                  {field.required && <span className="text-destructive"> *</span>}
                </Label>
                <FieldInput
                  field={field}
                  value={parameters[field.name]}
                  options={loadOptions(field)}
                  onValue={(v) => setParam(field.name, v)}
                />
                {field.description && (
                  <p className="text-[11px] text-muted-foreground/80 leading-relaxed">{field.description}</p>
                )}
              </div>
            ))}
        </>
      )}
    </div>
  );
}
